"""
mcp_server/server.py

The local MCP server. Exposes two tools over stdio using the official MCP
Python SDK:
  - sql_read  : arbitrary SELECT/SHOW/EXPLAIN
  - sql_write : mutating statement, gated by mcp_server/validators.py

Run standalone for debugging:
    python -m mcp_server.server

In production the agent_orchestrator spawns this as a subprocess via the
MCP stdio client and talks to it over stdin/stdout.
"""
import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_server.db_connector import db
from mcp_server.validators import validate_write
from tools.get_client_data import get_client_data_from_supabase
from tools.get_pdf_template import get_pdf_template_from_mysql

server = Server("local-mysql-harness")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="sql_read",
            description="Execute a read-only SQL statement (SELECT/SHOW/EXPLAIN) against the local MySQL DB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                    "params": {
                        "type": "array",
                        "items": {"type": ["string", "number", "boolean", "null"]},
                        "default": [],
                    },
                },
                "required": ["sql"],
            },
        ),
        Tool(
            name="sql_write",
            description=(
                "Execute a mutating SQL statement (INSERT/UPDATE/DELETE). "
                "Must be parameterized. Passes through the Harness validator "
                "before execution; may return BLOCKED_* status instead of running."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                    "params": {
                        "type": "array",
                        "items": {"type": ["string", "number", "boolean", "null"]},
                        "default": [],
                    },
                    "allow_protected": {"type": "boolean", "default": False},
                },
                "required": ["sql"],
            },
        ),
        Tool(
            name="get_client_data_from_supabase",
            description="Read-only lookup of a client's profile from Supabase (Postgres) by full name.",
            inputSchema={
                "type": "object",
                "properties": {"client_name": {"type": "string"}},
                "required": ["client_name"],
            },
        ),
        Tool(
            name="get_pdf_template_from_mysql",
            description=(
                "Read-only lookup of a PDF template from the local MySQL asset DB, "
                "selected by a deterministic attribute (e.g. attribute_key='state')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "attribute_key": {"type": "string"},
                    "attribute_value": {"type": "string"},
                },
                "required": ["attribute_key", "attribute_value"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "sql_read":
        return await _handle_sql_read(arguments)
    if name == "sql_write":
        return await _handle_sql_write(arguments)
    if name == "get_client_data_from_supabase":
        result = get_client_data_from_supabase(arguments["client_name"])
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    if name == "get_pdf_template_from_mysql":
        result = get_pdf_template_from_mysql(
            arguments["attribute_key"], arguments["attribute_value"]
        )
        # template_blob is bytes — not JSON-serializable as-is; base64 it
        # for the MCP text-content contract. Callers using the direct
        # tools/get_pdf_template.py import get raw bytes instead (preferred
        # for this project's deterministic workflow).
        if result.get("status") == "SUCCESS" and isinstance(result.get("template_blob"), bytes):
            import base64
            result = {**result, "template_blob_b64": base64.b64encode(result.pop("template_blob")).decode()}
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    return [TextContent(type="text", text=json.dumps({
        "status": "FAILURE",
        "error": f"Unknown tool '{name}'",
    }))]


async def _handle_sql_read(arguments: dict) -> list[TextContent]:
    sql = arguments["sql"]
    params = tuple(arguments.get("params", []))
    try:
        rows = db.execute_read(sql, params)
        payload = {"status": "SUCCESS", "rows": rows, "row_count": len(rows)}
    except Exception as exc:
        payload = {"status": "FAILURE", "error": str(exc)}
    return [TextContent(type="text", text=json.dumps(payload, default=str))]


async def _handle_sql_write(arguments: dict) -> list[TextContent]:
    sql = arguments["sql"]
    params = tuple(arguments.get("params", []))
    allow_protected = arguments.get("allow_protected", False)

    estimated_rows = db.estimate_rows_affected(sql, params)
    result = validate_write(
        sql,
        params=params,
        estimated_rows_affected=estimated_rows,
        allow_protected=allow_protected,
    )

    if not result.is_allowed:
        payload = {
            "status": "BLOCKED_BY_HARNESS",
            "outcome": result.outcome.value,
            "reason": result.reason,
        }
        return [TextContent(type="text", text=json.dumps(payload))]

    try:
        affected = db.execute_write(sql, params)
        payload = {"status": "SUCCESS", "rows_affected": affected}
    except Exception as exc:
        payload = {"status": "FAILURE", "error": str(exc)}
    return [TextContent(type="text", text=json.dumps(payload, default=str))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())