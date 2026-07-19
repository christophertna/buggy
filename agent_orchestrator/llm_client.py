"""
agent_orchestrator/llm_client.py

Thin wrapper around the OpenAI API. Knows nothing about MySQL or the
Harness — it only turns a task + tool schema into a tool-call decision.
"""
from openai import OpenAI

from config.settings import LLM

_client = OpenAI(api_key=LLM.api_key)


def decide_tool_call(task_description: str, tool_schemas: list[dict]) -> dict:
    """
    Sends the task to the LLM along with the available MCP tool schemas
    (already translated to OpenAI function-calling format by
    tools/registry.py) and returns the chosen tool call, if any.

    Returns a dict like:
        {"tool_name": "sql_write", "arguments": {...}}
    or:
        {"tool_name": None, "arguments": None, "message": "..."}
    """
    response = _client.chat.completions.create(
        model=LLM.model,
        temperature=LLM.temperature,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an agent operating inside a Harness. You may only "
                    "act through the provided tools. Prefer sql_read to "
                    "inspect data before issuing sql_write. Never attempt to "
                    "bypass validation errors by rewriting a query to look "
                    "different — fix the underlying issue instead."
                ),
            },
            {"role": "user", "content": task_description},
        ],
        tools=tool_schemas,
        tool_choice="auto",
    )

    choice = response.choices[0].message

    if not choice.tool_calls:
        return {"tool_name": None, "arguments": None, "message": choice.content}

    call = choice.tool_calls[0]
    import json as _json

    return {
        "tool_name": call.function.name,
        "arguments": _json.loads(call.function.arguments),
        "message": choice.content,
    }
