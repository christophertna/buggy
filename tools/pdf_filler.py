"""
tools/pdf_filler.py

Maps Supabase client-data columns onto PDF AcroForm field names (per
config/field_map.json) and fills the template using pypdf. PDF templates 
are fillable AcroForm PDFs, not flat/scanned.
"""
import io

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject


class PDFFillError(Exception):
    """Raised on any failure to map or fill fields — treated as terminal,
    non-retryable by the workflow (a malformed template/mapping won't fix
    itself on retry)."""


def fill_pdf_template(template_blob: bytes, field_map: dict, client_data: dict) -> bytes:
    """
    field_map: {"<supabase_column>": "<pdf_acroform_field_name>", ...}
    client_data: the dict returned by get_client_data_from_supabase()["client"]
    """
    try:
        reader = PdfReader(io.BytesIO(template_blob))
    except Exception as exc:
        raise PDFFillError(f"Could not read template PDF: {exc}") from exc

    if "/AcroForm" not in reader.trailer.get("/Root", {}):
        raise PDFFillError("Template has no AcroForm fields to fill.")

    writer = PdfWriter()
    writer.append(reader)

    field_values = {}
    for supabase_col, pdf_field in field_map.items():
        value = client_data.get(supabase_col)
        if value is not None:
            field_values[pdf_field] = str(value)

    try:
        for page in writer.pages:
            writer.update_page_form_field_values(page, field_values)
    except Exception as exc:
        raise PDFFillError(f"Failed to write field values: {exc}") from exc

    # Force viewers to render the values we just set rather than relying on
    # cached appearance streams from the blank template.
    root = writer._root_object
    if "/AcroForm" in root:
        root["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()