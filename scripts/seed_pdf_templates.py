"""
scripts/seed_pdf_templates.py

One-time (or repeatable) seeding script: scans PDF_TEMPLATE_ROOT for files
named "<attribute_value>_<template_name>.pdf" (e.g. "CA_intakeform.pdf")
and inserts/updates a matching row in pdf_templates for each one.

This does NOT upload file contents into MySQL — it only writes the relative
path string. The actual PDF bytes stay on disk and are read at request time
by tools/get_pdf_template.py. Re-running this script is safe: it upserts on
the (attribute_key, attribute_value) unique key, so re-running after adding
new files won't duplicate existing rows.

NOTE on Harness scope: this script calls db.execute_write() directly rather
than going through mcp_server/validators.py::validate_write. That's
intentional — CONSTITUTION.md 1.1 governs writes made BY THE AGENT LOOP at
runtime; this is a human-run, one-off admin/setup script, run manually from
a terminal, never invoked by main.py or the orchestrator. If you ever wire
this into an automated pipeline that runs unattended, route it through
validate_write like everything else.

Usage (from project root, venv active):
    python -m scripts.seed_pdf_templates
    python -m scripts.seed_pdf_templates --attribute-key state
    python -m scripts.seed_pdf_templates --dry-run
"""
import argparse
from pathlib import Path

from config.settings import DOC_AUTOMATION
from mcp_server.db_connector import db

UPSERT_SQL = """
    INSERT INTO pdf_templates (template_name, attribute_key, attribute_value, template_path)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        template_name = VALUES(template_name),
        template_path = VALUES(template_path),
        is_active = TRUE
"""


def discover_templates(root: Path) -> list[dict]:
    """
    Parses filenames like 'CA_intakeform.pdf' into
    {attribute_value: 'CA', template_name: 'intakeform', relative_path: '...'}.
    Adjust the split logic here if your naming convention differs.
    """
    discovered = []
    for pdf_path in sorted(root.rglob("*.pdf")):
        stem = pdf_path.stem  # filename without .pdf
        if "_" not in stem:
            print(f"[skip] '{pdf_path.name}' doesn't match '<attribute>_<name>.pdf' — skipping.")
            continue
        attribute_value, _, template_name = stem.partition("_")
        relative_path = pdf_path.relative_to(root).as_posix()
        discovered.append({
            "attribute_value": attribute_value,
            "template_name": template_name,
            "relative_path": relative_path,
        })
    return discovered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--attribute-key",
        default=DOC_AUTOMATION.template_attribute,
        help="attribute_key to assign to every discovered row (default: from .env DOC_TEMPLATE_ATTRIBUTE)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be inserted without touching the database",
    )
    args = parser.parse_args()

    root = Path(DOC_AUTOMATION.template_root)
    if not root.is_dir():
        raise SystemExit(f"PDF_TEMPLATE_ROOT '{root}' does not exist or is not a directory.")

    templates = discover_templates(root)
    if not templates:
        print(f"No .pdf files found under {root}.")
        return

    print(f"Found {len(templates)} template(s) under {root}:")
    for t in templates:
        print(f"  attribute_key='{args.attribute_key}' attribute_value='{t['attribute_value']}' "
              f"template_name='{t['template_name']}' path='{t['relative_path']}'")

    if args.dry_run:
        print("\n--dry-run set, nothing written to the database.")
        return

    for t in templates:
        db.execute_write(
            UPSERT_SQL,
            (t["template_name"], args.attribute_key, t["attribute_value"], t["relative_path"]),
        )
    print(f"\nUpserted {len(templates)} row(s) into pdf_templates.")


if __name__ == "__main__":
    main()