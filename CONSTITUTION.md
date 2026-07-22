# CONSTITUTION.md
### Project Governing Rules — "Harness & Loop" Philosophy

This document is law for this codebase. Any code, prompt, or tool that violates
these rules is a bug, regardless of whether it "works." The **Harness** is the
set of hard constraints that keep the agent safe and bounded. The **Loop** is
the persistent execution engine that drives the agent toward task completion.
The Harness always wins when it conflicts with the Loop's desire to keep going.

---

## 1. The Harness (Safety Constraints)

### 1.1 Write Validation (Non-Negotiable)
Any operation that mutates the database (`INSERT`, `UPDATE`, `DELETE`,
`REPLACE`, `ALTER`, `DROP`, `TRUNCATE`, `CREATE`, or any DDL/DML with a side
effect) MUST pass through the validation gate in
`mcp_server/validators.py::validate_write` before it reaches the database
connector. There are no exceptions, including for "trusted" internal tasks.

A write is only valid if ALL of the following hold:
- It is expressed as a parameterized query. String-interpolated SQL is
  rejected outright, no matter the source.
- It does not touch a table listed in `PROTECTED_TABLES` (config/settings.py)
  unless an explicit `allow_protected=True` flag is passed by a human-reviewed
  workflow, not by the LLM itself.
- Destructive statements (`DROP`, `TRUNCATE`, unscoped `DELETE`/`UPDATE`
  without a `WHERE` clause) are always rejected. There is no override for
  unscoped destructive statements — the agent must be forced to add a scope.
- The estimated row impact (via `EXPLAIN` where feasible) is below
  `MAX_ROWS_AFFECTED` (default: 500). Larger changes require the task to be
  split or explicitly confirmed out-of-band.

Read-only operations (`SELECT`, `SHOW`, `EXPLAIN`) bypass write validation but
still pass through the connector's query allowlist/sanitizer.

### 1.2 Circuit Breaker (Non-Negotiable)
Every loop (the outer task loop in `main.py`, and any inner retry loop inside
a tool or workflow) MUST be wrapped by `agent_orchestrator/circuit_breaker.py`.

- **Max retries: 3** per task attempt (`CircuitBreaker.MAX_RETRIES = 3`). This
  number is a constitutional constant, not a tunable default — changing it
  requires editing this document, not just the config.
- On the 3rd consecutive failure of the same task, the circuit **OPENS**: the
  task is marked `FAILED_CIRCUIT_OPEN`, the loop stops retrying it, the
  failure is logged to `history.log` with full context, and control returns
  to the outer loop to move to the next task (or halt, if configured to
  halt-on-failure).
- A circuit breaker never retries silently. Every retry increments a visible
  counter and is logged before the retry occurs, not after.
- There is no infinite loop anywhere in this codebase. If you cannot bound a
  loop with a circuit breaker, timeout, or max-iteration count, do not write
  it.

### 1.3 No Silent Failures
Every tool call result MUST report an explicit exit status
(`SUCCESS`, `FAILURE`, `RETRY`, `BLOCKED_BY_HARNESS`). `main.py` must check
this status before deciding to continue, retry, or halt. Swallowing an
exception without logging and re-raising a typed result is a Harness
violation.

### 1.4 Least Privilege
The MySQL credentials used by `mcp_server/db_connector.py` should map to a
database user with the minimum grants required (read/write only, no
`SUPER`/`GRANT OPTION`/`DROP` at the account level where avoidable). The
application-level `validators.py` gate is a second layer of defense, not a
substitute for DB-level privilege limits.

### 1.5a Read-Only Source Boundaries (Multi-Database Rule)
Some tools exist purely to *read* from a system of record that this project
does not own or mutate (e.g. `get_client_data_from_supabase`,
`get_pdf_template_from_mysql`). The enforcement mechanism differs by source,
and that's fine as long as each is genuinely load-bearing:
- `get_pdf_template_from_mysql` talks raw SQL to a direct connection, so it
  is gated in application code by `mcp_server/validators.py::validate_read_only`,
  and its connector exposes no write/commit method.
- `get_client_data_from_supabase` talks to Supabase's REST API (PostgREST)
  via the publishable/anon key, using a query builder rather than SQL
  strings. There is no SQL-string validator to apply here — the actual
  boundary is the Row Level Security policy on the `clients` table in
  Supabase itself, which must grant SELECT-only to the anon role. That RLS
  policy IS the Harness boundary for this tool; a missing or overly
  permissive policy is a Harness violation even though no application code
  changed.
If a future task genuinely needs to write to one of these source systems,
that is a new constitutional decision (Section 3), not a quiet extension of
an existing read-only tool or a quiet loosening of an RLS policy.

### 1.5b Filesystem Writes Outside the Database
Tools that write generated artifacts to disk (e.g. filled PDFs) are not
"database writes" under Section 1.1, but they are still Harness-governed:
- Output must be confined to a configured output directory
  (`DOCUMENT_OUTPUT_DIR`), never a path derived directly from untrusted
  input without sanitization.
- Any identifier used to build a filename (client name, task id, etc.) MUST
  be sanitized against path traversal before touching the filesystem.
- Distinguish "not found" (a valid, deterministic result — retrying with the
  same input can't change it) from "connection/transient failure" (worth
  retrying under the Circuit Breaker). Conflating the two either wastes
  retries or silently gives up too early.

### 1.5 Auditability
Every tool invocation, its arguments, its validation outcome, and its result
must be logged to `history.log` in an append-only fashion. Logs are never
deleted or rewritten by the agent itself.

---

## 2. The Loop (Persistence Constraints)

### 2.1 State Is External, Not In-Memory
Task state lives in `tasks.json` (input queue) and `history.log`
(append-only output/audit trail). The process can crash and resume without
losing track of what has and hasn't been attempted.

### 2.2 Idempotency
Tasks should be designed so that re-running a task that already partially
succeeded does not cause duplicate side effects. Where this isn't naturally
true, the task must carry a unique idempotency key that write-tools can check
against before applying a mutation.

### 2.3 One Task, One Outcome
Each iteration of the outer `while` loop in `main.py` processes exactly one
task to a terminal state (`SUCCESS`, `FAILED_CIRCUIT_OPEN`, or `SKIPPED`)
before moving to the next. The loop does not batch multiple tasks into a
single unchecked pass.

### 2.4 Graceful Degradation
If the MCP server or the LLM API is unreachable, this is a `FAILURE` exit
status subject to the same Circuit Breaker as any other failure — not a
crash of the outer process.

---

## 3. Amendment Process
Changes to Section 1 (Harness) require a deliberate, reviewed edit to this
file plus a corresponding code change — never a silent behavioral drift.
Changes to Section 2 (Loop) are more flexible but should not weaken any
guarantee in Section 1.
