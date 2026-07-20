"""
tools/get_pdf_template.py

Tool: get_pdf_template_from_mysql
Read-only lookup of a PDF template. The MySQL row only stores a relative
PATH to the template file (not the binary) — the row is resolved against
PDF_TEMPLATE_ROOT and the file is read from disk. A missing DB row and a
missing file on disk both collapse to NOT_FOUND: either way, there's
nothing to fill, and retrying an identical lookup can't change that.

Path-traversal guard: template_path is untrusted input the moment it comes
out of the database (someone could seed a malicious row). We resolve it
against template_root and reject anything that escapes that directory,
mirroring the filesystem-write safety already applied to output paths
(CONSTITUTION.md 1.5b) — this is the read-side equivalent.
"""
from pathlib import Path

from mcp_server.db_connector import db
from mcp_server.validators import validate_read_only
from config.settings import DOC_AUTOMATION

TEMPLATE_QUERY = """
    SELECT id, template_name, template_path
    FROM pdf_templates
    WHERE attribute_key = %s AND attribute_value = %s
    LIMIT 1
"""


def _resolve_template_path(relative_path: str) -> Path | None:
    """Returns the resolved absolute path, or None if it escapes template_root."""
    root = Path(DOC_AUTOMATION.template_root).resolve()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents and candidate != root:
        return None
    return candidate


def get_pdf_template_from_mysql(attribute_key: str, attribute_value: str) -> dict:
    validation = validate_read_only(TEMPLATE_QUERY)
    if not validation.is_allowed:
        return {"status": "BLOCKED_BY_HARNESS", "reason": validation.reason}

    try:
        rows = db.execute_read(TEMPLATE_QUERY, (attribute_key, attribute_value))
    except Exception as exc:
        return {"status": "FAILURE", "error": str(exc)}

    if not rows:
        return {
            "status": "NOT_FOUND",
            "error": f"No template row found for {attribute_key}='{attribute_value}'.",
        }

    row = rows[0]
    resolved_path = _resolve_template_path(row["template_path"])

    if resolved_path is None:
        # Data integrity / tampering concern, not a normal miss — worth its
        # own message even though the terminal status is the same as NOT_FOUND.
        return {
            "status": "NOT_FOUND",
            "error": (
                f"template_path '{row['template_path']}' for {attribute_key}="
                f"'{attribute_value}' resolves outside PDF_TEMPLATE_ROOT; refusing to read it."
            ),
        }

    if not resolved_path.is_file():
        return {
            "status": "NOT_FOUND",
            "error": f"Template row exists but file is missing on disk: {resolved_path}",
        }

    try:
        template_blob = resolved_path.read_bytes()
    except Exception as exc:
        return {"status": "FAILURE", "error": f"Could not read template file: {exc}"}

    return {
        "status": "SUCCESS",
        "template_name": row["template_name"],
        "template_blob": template_blob,  # bytes, same contract as before
    }