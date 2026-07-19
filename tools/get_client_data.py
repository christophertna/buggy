"""
tools/get_client_data.py

Tool: get_client_data_from_supabase
Read-only lookup of a client's profile from Supabase (Postgres). This is one
of the 2 "distinct tools" for the Document Automation module, kept
separate from get_pdf_template.py so each can be independently validated,
logged, and (later) exposed to an LLM-driven task if needed.

Status contract:
  SUCCESS           -> client data returned
  NOT_FOUND         -> query succeeded, no matching client (terminal, NOT a
                        Circuit Breaker failure — retrying an exact-match
                        query won't change the result)
  BLOCKED_BY_HARNESS-> a non-read statement was attempted (should never
                        happen given the hardcoded query below; defense in depth)
  FAILURE           -> connection/query error (Circuit Breaker-eligible,
                        i.e. worth retrying)
"""
from mcp_server.supabase_connector import supabase_db
from mcp_server.validators import validate_read_only

# NOTE: adjust column names / table name to match your actual Supabase schema.
# This query intentionally selects the DOC_AUTOMATION.template_attribute
# column (default "state") alongside the profile fields needed for PDF filling.

# ============== !!! TO BE MODIFIED !!! =========================
CLIENT_QUERY = """
    SELECT
        id,
        full_name,
        address_line1,
        city,
        state,
        zip_code,
        date_of_birth
    FROM clients
    WHERE full_name = %s
    LIMIT 1
"""


def get_client_data_from_supabase(client_name: str) -> dict:
    validation = validate_read_only(CLIENT_QUERY)
    if not validation.is_allowed:
        return {"status": "BLOCKED_BY_HARNESS", "reason": validation.reason}

    try:
        rows = supabase_db.execute_read(CLIENT_QUERY, (client_name,))
    except Exception as exc:
        return {"status": "FAILURE", "error": str(exc)}

    if not rows:
        return {
            "status": "NOT_FOUND",
            "error": f"No client record found for full_name='{client_name}'.",
        }

    return {"status": "SUCCESS", "client": rows[0]}