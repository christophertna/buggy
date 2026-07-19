"""
tools/sql_read.py

Direct-callable version of the read tool, independent of the MCP transport.
Useful for unit tests and for workflows that want to call the tool in-process
rather than through the MCP stdio client. Mirrors the JSON contract used by
mcp_server/server.py so both paths behave identically.
"""
from mcp_server.db_connector import db


def sql_read(sql: str, params: tuple | dict | None = None) -> dict:
    try:
        rows = db.execute_read(sql, params or ())
        return {"status": "SUCCESS", "rows": rows, "row_count": len(rows)}
    except Exception as exc:
        return {"status": "FAILURE", "error": str(exc)}
