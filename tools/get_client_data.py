"""
tools/get_client_data.py

Tool: get_client_data_from_supabase
READ-ONLY lookup of an applicant's profile via the Supabase REST API
(PostgREST), authenticated with the publishable (anon) key.

Safety note: there is no SQL-string validator gating this tool (compare
tools/get_pdf_template.py, which validates raw SQL against MySQL). This
tool can't express anything beyond what the PostgREST query-builder
supports; what the publishable key is allowed to read is enforced by 
RLS policies on the table in Supabase itself (CONSTITUTION.md 1.5a). 
Confirm that table has a SELECT-only policy for the anon role.

Status contract:
  SUCCESS   -> applicant data returned
  NOT_FOUND -> query succeeded, no matching applicant (terminal, not
               Circuit-Breaker-eligible)
  FAILURE   -> network/API/auth error (Circuit-Breaker-eligible)
"""
from mcp_server.supabase_connector import supabase_db

CLIENT_TABLE = "applicants"
CLIENT_COLUMNS = (
    "id, user_id, full_name, first_name, last_name, birth_date, "
    "address, mailing_address, city, state, country, "
    "phone_number, email, minor, main_contact"
)


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
            "error": f"No applicant record found for full_name='{client_name}'.",
        }

    return {"status": "SUCCESS", "client": rows[0]}