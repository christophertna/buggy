"""
mcp_server/supabase_connector.py

Read-only connector to Supabase client data via the REST API (PostgREST),
authenticated with the publishable (anon) API key rather than a direct
Postgres connection/password. This is a deliberate architecture change:
access control now lives in Supabase's Row Level Security policies on the
`clients` table, not in application code: see CONSTITUTION.md 1.5a.

There is no raw-SQL execution method here, by design: PostgREST's query
builder only exposes the operations its client library supports (select,
eq, filter, etc.), which is itself a safety property, there is no string
of SQL for anything to inject into. If a policy on `clients` ever allows
more than SELECT to the anon/publishable role, that is a Supabase-side
config problem to fix at the RLS layer, not something this class can
compensate for.
"""
from supabase import Client, create_client

from config.settings import SUPABASE


class SupabaseConnector:
    def __init__(self):
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            if not SUPABASE.url or not SUPABASE.api_key:
                raise RuntimeError(
                    "SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY are not set — check your .env."
                )
            self._client = create_client(SUPABASE.url, SUPABASE.api_key)
        return self._client

    def select(self, table: str, columns: str, filters: dict) -> list[dict]:
        """
        Read-only SELECT via PostgREST.
          table:   table name, e.g. "clients"
          columns: comma-separated column list, e.g. "id, full_name, state"
          filters: dict of column -> exact-match value (equality only for
                    now; extend with .ilike()/.gte()/etc. here if a workflow
                    needs richer filtering later)
        What this key can actually see is enforced by RLS on the table,
        not by anything in this method.
        """
        client = self._get_client()
        query = client.table(table).select(columns)
        for column, value in filters.items():
            query = query.eq(column, value)
        response = query.execute()
        return response.data or []


supabase_db = SupabaseConnector()