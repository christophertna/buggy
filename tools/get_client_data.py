"""
tools/get_client_data.py

Tool: get_client_data_from_supabase
Read-only lookup of a client's profile via the Supabase REST API
(PostgREST), authenticated with the publishable (anon) key.

Safety note: there is no SQL-string validator gating this tool anymore
(compare tools/get_pdf_template.py, which still validates raw SQL against
MySQL). That's intentional: this tool can't express
anything beyond what the PostgREST query-builder supports, and what the
publishable key is allowed to read/write is enforced by Row Level Security
policies on the `clients` table in Supabase itself (CONSTITUTION.md 1.5a).
Make sure that table has an RLS policy granting SELECT-only access to the
anon role for the columns this tool needs, that policy is the actual
Harness boundary here, not application code.

Status contract (unchanged from the previous Postgres-direct version):
  SUCCESS   -> client data returned
  NOT_FOUND -> query succeeded, no matching client (terminal, not
               Circuit-Breaker-eligible — retrying an exact-match filter
               with the same input can't change the result)
  FAILURE   -> network/API/auth error (Circuit-Breaker-eligible)
"""
from mcp_server.supabase_connector import supabase_db

# NOTE: adjust table/column names to match your actual Supabase schema.
CLIENT_TABLE = "clients"
CLIENT_COLUMNS = "id, full_name, address_line1, city, state, zip_code, date_of_birth"


def get_client_data_from_supabase(client_name: str) -> dict:
    try:
        rows = supabase_db.select(
            CLIENT_TABLE, CLIENT_COLUMNS, {"full_name": client_name}
        )
    except Exception as exc:
        return {"status": "FAILURE", "error": str(exc)}

    if not rows:
        return {
            "status": "NOT_FOUND",
            "error": f"No client record found for full_name='{client_name}'.",
        }

    return {"status": "SUCCESS", "client": rows[0]}