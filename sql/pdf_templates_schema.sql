-- sql/pdf_templates_schema.sql
--
-- Reference schema for the local MySQL "PDF template asset" table used by
-- tools/get_pdf_template.py. Not auto-applied by any script in this repo —
-- run it manually against your local MySQL 9.2 instance, or fold it into
-- your own migration tool.
--
-- Templates are selected by (attribute_key, attribute_value), e.g.
-- ('state', 'CA') — matching CONFIG.DOC_AUTOMATION.template_attribute and
-- the corresponding client column in Supabase.

-- ============= !!! TO BE MODIFIED !!! =========================
CREATE TABLE IF NOT EXISTS pdf_templates (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    template_name   VARCHAR(255)   NOT NULL,
    attribute_key   VARCHAR(64)    NOT NULL,   -- e.g. 'state'
    attribute_value VARCHAR(64)    NOT NULL,   -- e.g. 'CA'
    template_path   VARCHAR(500)   NOT NULL,   -- relative to PDF_TEMPLATE_ROOT, e.g. 'forms/ca_intake.pdf'
    is_active       BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_attribute_lookup (attribute_key, attribute_value)
);

-- template_path is stored RELATIVE and resolved against PDF_TEMPLATE_ROOT
-- at read time (tools/get_pdf_template.py) — never store an absolute path
-- or one containing '..' segments; the loader rejects both.
--
-- INSERT INTO pdf_templates (template_name, attribute_key, attribute_value, template_path)
-- VALUES ('California Intake Form', 'state', 'CA', 'forms/ca_intake.pdf');

-- Example seed (replace template_blob via application code — LOAD_FILE
-- requires FILE privilege and a path visible to the MySQL server process,
-- which is usually not what you want for a local dev DB):
--
-- INSERT INTO pdf_templates (template_name, attribute_key, attribute_value, template_blob)
-- VALUES ('California Intake Form', 'state', 'CA', <binary data>);