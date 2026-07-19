"""
tools/get_pdf_template.py

Tool: get_pdf_template_from_mysql
Read-only lookup of a PDF template binary from the local MySQL asset
database, selected by a deterministic attribute (e.g. attribute_key="state",
attribute_value="CA"). See sql/pdf_templates_schema.sql for the expected
table shape.

Status contract mirrors tools/get_client_data.py:
  SUCCESS / NOT_FOUND / BLOCKED_BY_HARNESS / FAILURE
"""
from mcp_server.db_connector import db
from mcp_server.validators import validate_read_only

# ============== !!! TO BE MODIFIED !!! =========================
TEMPLATE_QUERY = """
    SELECT id, template_name, template_blob
    FROM pdf_templates
    WHERE attribute_key = %s AND attribute_value = %s
    LIMIT 1
"""


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
            "error": f"No template found for {attribute_key}='{attribute_value}'.",
        }

    row = rows[0]
    return {
        "status": "SUCCESS",
        "template_name": row["template_name"],
        "template_blob": row["template_blob"],  # bytes (LONGBLOB)
    }