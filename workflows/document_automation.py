"""
workflows/document_automation.py

Deterministic Document Automation pipeline: NO LLM call per step, by
explicit design decision. For each client name in CLIENTS_INPUT_FILE:

    1. get_client_data_from_supabase(name)
    2. get_pdf_template_from_mysql(template_attribute, client[template_attribute])
    3. fill_pdf_template(template_blob, field_map, client_data)
    4. write finalized PDF to DOCUMENT_OUTPUT_DIR

Harness compliance:
  - Both DB tools are read-only-gated (validators.validate_read_only);
    this pipeline never writes to Supabase or MySQL.
  - Every client is wrapped in its own CircuitBreaker (CONSTITUTION.md 1.2).
    Only FAILURE (connection/query errors) count against retries. NOT_FOUND
    and PDF-fill errors are terminal on first occurrence, retrying an
    identical lookup or an identical malformed mapping cannot succeed.
  - Every client's outcome is appended to history.log (CONSTITUTION.md 1.5).
  - One client failing does NOT halt the batch, matching main.py's
    "one task, one outcome" Loop philosophy (CONSTITUTION.md 2.3). If you
    want halt-on-first-failure semantics, set halt_on_failure=True in
    run_batch().
  - Client names are sanitized before touching the filesystem to prevent
    path traversal via a malicious/malformed input line.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from agent_orchestrator.circuit_breaker import CircuitBreaker
from config.settings import DOC_AUTOMATION, PATHS
from tools.get_client_data import get_client_data_from_supabase
from tools.get_pdf_template import get_pdf_template_from_mysql
from tools.pdf_filler import PDFFillError, fill_pdf_template

HISTORY_LOG = Path(PATHS.history_log)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_\-]+")

# Statuses that should NOT be retried by the Circuit Breaker — retrying them
# with identical inputs cannot produce a different outcome.
_TERMINAL_NO_RETRY = {"NOT_FOUND", "BLOCKED_BY_HARNESS"}


def _load_field_map() -> dict:
    path = Path(DOC_AUTOMATION.field_map_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Field map not found at {path}. See config/field_map.json for the expected format."
        )
    return json.loads(path.read_text())


def _load_client_names() -> list[str]:
    path = Path(DOC_AUTOMATION.clients_input_file)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def _safe_filename(name: str) -> str:
    """Prevents path traversal / injection via client names before writing to disk."""
    cleaned = _SAFE_NAME.sub("_", name).strip("_")
    return cleaned or "unnamed_client"


def _log(client_name: str, result: dict) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workflow": "document_automation",
        "client_name": client_name,
        **result,
    }
    with HISTORY_LOG.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def process_client(client_name: str, field_map: dict) -> dict:
    """Runs one client to a terminal state. Returns a result dict with a 'status' key."""
    breaker = CircuitBreaker(task_id=f"document_automation:{client_name}")

    while not breaker.is_open:
        client_result = get_client_data_from_supabase(client_name)
        if client_result["status"] in _TERMINAL_NO_RETRY:
            return client_result
        if client_result["status"] != "SUCCESS":
            breaker.record_failure(client_result.get("error", "unknown"))
            if breaker.is_open:
                return {"status": "FAILED_CIRCUIT_OPEN", **client_result, **breaker.status_snapshot()}
            continue  # transient failure, retry

        client_data = client_result["client"]
        attribute_value = client_data.get(DOC_AUTOMATION.template_attribute)
        if not attribute_value:
            return {
                "status": "FAILURE",
                "error": (
                    f"Client '{client_name}' has no value for attribute "
                    f"'{DOC_AUTOMATION.template_attribute}' — cannot select a template."
                ),
            }

        template_result = get_pdf_template_from_mysql(
            DOC_AUTOMATION.template_attribute, str(attribute_value)
        )
        if template_result["status"] in _TERMINAL_NO_RETRY:
            return template_result
        if template_result["status"] != "SUCCESS":
            breaker.record_failure(template_result.get("error", "unknown"))
            if breaker.is_open:
                return {"status": "FAILED_CIRCUIT_OPEN", **template_result, **breaker.status_snapshot()}
            continue  # transient failure, retry

        try:
            filled_pdf_bytes = fill_pdf_template(
                template_result["template_blob"], field_map, client_data
            )
        except PDFFillError as exc:
            # Mapping/template-format problems are terminal, not connection
            # issues — no Circuit Breaker retry burns cycles on the same bug.
            return {"status": "FAILURE", "error": str(exc)}

        output_dir = Path(DOC_AUTOMATION.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = output_dir / f"{_safe_filename(client_name)}_{timestamp}.pdf"
        out_path.write_bytes(filled_pdf_bytes)

        breaker.record_success()
        return {
            "status": "SUCCESS",
            "output_path": str(out_path),
            "template_name": template_result.get("template_name"),
        }

    return {"status": "FAILED_CIRCUIT_OPEN", **breaker.status_snapshot()}


def run_batch(halt_on_failure: bool = False) -> list[dict]:
    field_map = _load_field_map()
    client_names = _load_client_names()
    print(f"[DocumentAutomation] {len(client_names)} client(s) to process.")

    results = []
    for name in client_names:
        print(f"[DocumentAutomation] Processing '{name}'...")
        result = process_client(name, field_map)
        _log(name, result)
        results.append({"client_name": name, **result})
        print(f"[DocumentAutomation] '{name}' -> {result['status']}")

        if halt_on_failure and result["status"] not in ("SUCCESS",):
            print(f"[DocumentAutomation] halt_on_failure=True, stopping after '{name}'.")
            break

    succeeded = sum(1 for r in results if r["status"] == "SUCCESS")
    print(f"[DocumentAutomation] Done: {succeeded}/{len(results)} succeeded.")
    return results


if __name__ == "__main__":
    run_batch()