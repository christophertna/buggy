"""
tools/registry.py

Declares tool schemas in OpenAI function-calling format. These names must
match the MCP tool names exposed by mcp_server/server.py exactly, since
agent_orchestrator/orchestrator.py forwards the LLM's chosen tool_name
straight through to session.call_tool().

Keeping this declaration separate from mcp_server/server.py is deliberate:
the orchestrator/LLM side should only see what its allowed to see, and this
file is the place to trim or rephrase descriptions for prompting purposes
without touching the actual server implementation.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "sql_read",
            "description": "Run a read-only SQL query (SELECT/SHOW/EXPLAIN) against the local MySQL database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "Parameterized SQL SELECT/SHOW/EXPLAIN statement."},
                    "params": {
                        "type": "array",
                        "items": {"type": ["string", "number", "boolean", "null"]},
                        "description": "Positional parameters for the query placeholders.",
                    },
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sql_write",
            "description": (
                "Run a mutating SQL statement (INSERT/UPDATE/DELETE). Must be "
                "parameterized with placeholders and params, never with "
                "string-interpolated literals. May be rejected by the Harness "
                "validator (status=BLOCKED_BY_HARNESS) if it is destructive, "
                "unscoped, touches a protected table, or affects too many rows."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "Parameterized SQL mutation statement."},
                    "params": {
                        "type": "array",
                        "items": {"type": ["string", "number", "boolean", "null"]},
                        "description": "Positional parameters for the query placeholders.",
                    },
                    "allow_protected": {
                        "type": "boolean",
                        "description": "Only set True if a human has explicitly authorized touching a protected table.",
                    },
                },
                "required": ["sql"],
            },
        },
    },
    # Document Automation tools
    # NOTE: the document_automation workflow calls these directly as plain
    # Python functions (tools/get_client_data.py, tools/get_pdf_template.py)
    # rather than through this LLM tool-calling path, per the deterministic
    # pipeline design. These schemas exist so the same tools can be reused
    # by an LLM-driven task later without redefining them.
    {
        "type": "function",
        "function": {
            "name": "get_client_data_from_supabase",
            "description": "Read-only lookup of a client's profile from Supabase (Postgres) by full name.",
            "parameters": {
                "type": "object",
                "properties": {"client_name": {"type": "string"}},
                "required": ["client_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pdf_template_from_mysql",
            "description": (
                "Read-only lookup of a PDF template from the local MySQL asset DB, "
                "selected by a deterministic attribute (e.g. attribute_key='state')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "attribute_key": {"type": "string"},
                    "attribute_value": {"type": "string"},
                },
                "required": ["attribute_key", "attribute_value"],
            },
        },
    },
]
