"""
tools/sql_write.py

Direct-callable version of the write tool. Same Harness contract as
mcp_server/server.py::_handle_sql_write — validate_write() is always called
first, and a BLOCKED_BY_HARNESS status short-circuits before touching the DB.
"""
from mcp_server.db_connector import db
from mcp_server.validators import validate_write


def sql_write(
    sql: str,
    params: tuple | dict | None = None,
    allow_protected: bool = False,
) -> dict:
    params = params or ()
    estimated_rows = db.estimate_rows_affected(sql, params)

    result = validate_write(
        sql,
        params=params,
        estimated_rows_affected=estimated_rows,
        allow_protected=allow_protected,
    )

    if not result.is_allowed:
        return {
            "status": "BLOCKED_BY_HARNESS",
            "outcome": result.outcome.value,
            "reason": result.reason,
        }

    try:
        affected = db.execute_write(sql, params)
        return {"status": "SUCCESS", "rows_affected": affected}
    except Exception as exc:
        return {"status": "FAILURE", "error": str(exc)}
