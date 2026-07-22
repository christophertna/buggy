"""
scripts/inspect_supabase.py

Diagnostic tool, NOT part of the runtime agent loop. Queries the
'applicants' table through the exact same client/key the agent uses at
runtime, and reports what actually comes back. This is the most honest
way to check whether reality matches what tools/get_client_data.py
expects, since it shows you the agent's-eye view (through RLS), not the
dashboard's authenticated, policy-bypassing view.

Usage (from project root, venv active):
    python -m scripts.inspect_supabase
"""
from config.settings import DOC_AUTOMATION, SUPABASE
from mcp_server.supabase_connector import supabase_db

CLIENT_TABLE = "applicants"
EXPECTED_COLUMNS = {
    "user_id", "full_name", "first_name", "last_name", "birth_date",
    "address", "mailing_address", "city", "state", "country",
    "phone_number", "email", "minor", "main_contact",
}


def main():
    print(f"Supabase URL: {SUPABASE.url or '(not set — check .env)'}")
    print(f"Publishable key set: {'yes' if SUPABASE.api_key else 'no — check .env'}")
    print()

    if not SUPABASE.url or not SUPABASE.api_key:
        print("Stop here and fill in .env first — nothing else will work without these.")
        return

    try:
        client = supabase_db._get_client()
    except Exception as exc:
        print(f"Could not create Supabase client: {exc}")
        return

    print(f"Querying '{CLIENT_TABLE}' (select *, limit 3) via the publishable key...")
    try:
        response = client.table(CLIENT_TABLE).select("*").limit(3).execute()
    except Exception as exc:
        print(f"Query failed: {exc}")
        print(
            "Likely causes: table name is wrong (is it really called 'applicants'?), "
            "or the table/schema doesn't exist yet."
        )
        return

    rows = response.data or []

    if not rows:
        print("Query succeeded but returned 0 rows.")
        print(
            "This means EITHER the table is empty, OR Row Level Security is silently "
            "filtering everything out for the anon/publishable role. Both look identical "
            "from here — check Supabase Dashboard -> Table Editor -> applicants to see if "
            "rows actually exist, and Authentication -> Policies to confirm an anon "
            "SELECT policy is attached."
        )
        return

    actual_columns = set(rows[0].keys())
    print(f"Got {len(rows)} row(s). Columns visible to this key:")
    print(sorted(actual_columns))
    print()
    print("Sample row (first result):")
    print(rows[0])

    missing = EXPECTED_COLUMNS - actual_columns
    if missing:
        print()
        print(f"MISMATCH: tools/get_client_data.py expects these columns, not present: {sorted(missing)}")
        print("Either add them to the table, or edit CLIENT_COLUMNS in tools/get_client_data.py to match reality.")

    template_attr = DOC_AUTOMATION.template_attribute
    if template_attr not in actual_columns:
        print()
        print(
            f"MISMATCH: DOC_TEMPLATE_ATTRIBUTE='{template_attr}' (from .env) is not a "
            f"visible column — document_automation.py needs this value on every client "
            f"record to pick the right PDF template."
        )
    else:
        print()
        print(f"OK: template-selection attribute '{template_attr}' is present.")


if __name__ == "__main__":
    main()