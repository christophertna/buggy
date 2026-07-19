"""
agent_orchestrator/orchestrator.py

The Harness's execution core for a single task. Owns the connection to the
MCP server (via stdio client) and drives: LLM decides tool -> MCP executes ->
exit status checked -> CircuitBreaker updated. This module is what main.py's
outer Loop calls once per task.
"""
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_orchestrator.circuit_breaker import CircuitBreaker, CircuitState
from agent_orchestrator.llm_client import decide_tool_call
from tools.registry import TOOL_SCHEMAS

MCP_SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=["-m", "mcp_server.server"],
)


class TaskExecutionResult:
    def __init__(self, status: str, detail: dict):
        self.status = status  # SUCCESS | FAILURE | BLOCKED_BY_HARNESS | FAILED_CIRCUIT_OPEN
        self.detail = detail

    def to_dict(self) -> dict:
        return {"status": self.status, "detail": self.detail}


async def run_task(task: dict) -> TaskExecutionResult:
    """
    Runs a single task to a terminal state, honoring the Circuit Breaker
    (CONSTITUTION.md Section 1.2). Retries happen INSIDE this function so
    main.py's outer loop always gets back exactly one terminal result.
    """
    task_id = task["id"]
    description = task["description"]
    breaker = CircuitBreaker(task_id=task_id)

    async with AsyncExitStack() as stack:
        read_stream, write_stream = await stack.enter_async_context(
            stdio_client(MCP_SERVER_PARAMS)
        )
        session: ClientSession = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        while not breaker.is_open:
            decision = decide_tool_call(description, TOOL_SCHEMAS)

            if decision["tool_name"] is None:
                # LLM decided no tool call is needed / task can't proceed.
                return TaskExecutionResult(
                    status="SUCCESS",
                    detail={"note": "No tool call required.", "message": decision.get("message")},
                )

            try:
                mcp_result = await session.call_tool(
                    decision["tool_name"], decision["arguments"]
                )
                payload = _parse_tool_result(mcp_result)
            except Exception as exc:
                breaker.record_failure(str(exc))
                if breaker.is_open:
                    return TaskExecutionResult(
                        status="FAILED_CIRCUIT_OPEN",
                        detail={"error": str(exc), **breaker.status_snapshot()},
                    )
                continue  # retry, breaker still closed

            status = payload.get("status")

            if status == "SUCCESS":
                breaker.record_success()
                return TaskExecutionResult(status="SUCCESS", detail=payload)

            if status == "BLOCKED_BY_HARNESS":
                # Harness rejections are terminal, NOT retried — retrying the
                # same disallowed write would just burn attempts pointlessly.
                # See CONSTITUTION.md 1.1: the Harness always wins.
                return TaskExecutionResult(status="BLOCKED_BY_HARNESS", detail=payload)

            # status == "FAILURE" (or unknown) -> count against the breaker
            breaker.record_failure(payload.get("error", "unknown failure"))
            if breaker.is_open:
                return TaskExecutionResult(
                    status="FAILED_CIRCUIT_OPEN",
                    detail={**payload, **breaker.status_snapshot()},
                )
            # loop again -> retry, breaker still CLOSED

    # Defensive fallback; should not be reachable.
    return TaskExecutionResult(status="FAILED_CIRCUIT_OPEN", detail=breaker.status_snapshot())


def _parse_tool_result(mcp_result) -> dict:
    import json

    text_blocks = [c.text for c in mcp_result.content if hasattr(c, "text")]
    if not text_blocks:
        return {"status": "FAILURE", "error": "Empty MCP tool result."}
    try:
        return json.loads(text_blocks[0])
    except json.JSONDecodeError:
        return {"status": "FAILURE", "error": f"Non-JSON tool result: {text_blocks[0]}"}
