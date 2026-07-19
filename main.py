"""
main.py

The Loop.

Reads pending tasks from tasks.json, executes each one via the Harness-gated
orchestrator (which owns the MCP tool call + Circuit Breaker), checks the
exit status, and appends a structured record to history.log. State lives on
disk (CONSTITUTION.md 2.1) so the process can be killed and resumed without
losing track of progress.
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from agent_orchestrator.orchestrator import run_task
from config.settings import PATHS

TASKS_FILE = Path(PATHS.tasks_file)
HISTORY_LOG = Path(PATHS.history_log)

TERMINAL_STATUSES = {"SUCCESS", "FAILED_CIRCUIT_OPEN", "BLOCKED_BY_HARNESS", "SKIPPED"}


def load_tasks() -> list[dict]:
    if not TASKS_FILE.exists():
        TASKS_FILE.write_text("[]")
        return []
    return json.loads(TASKS_FILE.read_text())


def save_tasks(tasks: list[dict]) -> None:
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


def log_result(task: dict, result_dict: dict) -> None:
    """Append-only audit trail — CONSTITUTION.md 1.5 and 2.1."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task.get("id"),
        "description": task.get("description"),
        **result_dict,
    }
    with HISTORY_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


async def process_one_task(task: dict) -> dict:
    """
    Runs a single task to a terminal state. All retry logic and the Circuit
    Breaker live inside orchestrator.run_task — by the time we get a result
    here, it is final and safe to log + persist.
    """
    try:
        result = await run_task(task)
        return result.to_dict()
    except Exception as exc:
        # Anything escaping run_task is itself a Harness violation (Section
        # 1.3: no silent failures) — surface it loudly rather than crash-loop.
        return {"status": "FAILURE", "detail": {"unhandled_error": str(exc)}}


async def main_loop(halt_on_failure: bool = False) -> None:
    tasks = load_tasks()
    pending = [t for t in tasks if t.get("status") not in TERMINAL_STATUSES]

    print(f"[Loop] {len(pending)} pending task(s) out of {len(tasks)} total.")

    while pending:
        task = pending.pop(0)
        print(f"[Loop] Executing task '{task.get('id')}': {task.get('description')}")

        result_dict = await process_one_task(task)
        status = result_dict["status"]

        task["status"] = status
        task["last_result"] = result_dict.get("detail")
        save_tasks(tasks)  # persist after every task, not just at the end
        log_result(task, result_dict)

        print(f"[Loop] Task '{task.get('id')}' finished with status={status}")

        if status in ("FAILED_CIRCUIT_OPEN", "FAILURE") and halt_on_failure:
            print("[Loop] halt_on_failure=True and a task failed terminally. Stopping.")
            break

    print("[Loop] No more pending tasks. Exiting.")


if __name__ == "__main__":
    asyncio.run(main_loop(halt_on_failure=False))
