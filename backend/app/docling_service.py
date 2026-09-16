"""Document text extraction.

Prefers Docling for high-quality parsing/OCR when available and enabled,
otherwise falls back to python-docx (.docx) and pypdf (.pdf), then plain text.
"""
import io
import os
from typing import Optional

from .config import settings

_docling_converter = None
_docling_tried = False


def _get_docling():
    global _docling_converter, _docling_tried
    if not settings.use_docling:
        return None
    if _docling_tried:
        return _docling_converter
    _docling_tried = True
    try:
        from docling.document_converter import DocumentConverter  # type: ignore

        _docling_converter = DocumentConverter()
    except Exception:
        _docling_converter = None
    return _docling_converter


def _extract_with_docling(path: str) -> Optional[str]:
    conv = _get_docling()
    if conv is None:
        return None
    try:
        result = conv.convert(path)
        return result.document.export_to_markdown()
    except Exception:
        return None


def _extract_docx(data: bytes) -> str:
    try:
        import docx  # python-docx

        document = docx.Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append("\t".join(cell.text for cell in row.cells))
        return "\n".join(parts).strip()
    except Exception as e:  # noqa: BLE001
        return f"[docx extraction failed: {e}]"


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as e:  # noqa: BLE001
        return f"[pdf extraction failed: {e}]"


def extract_text(filename: str, data: bytes) -> str:
    """Extract text from an uploaded file (bytes)."""
    ext = os.path.splitext(filename)[1].lower()

    # .docx extracts perfectly (and fast) with python-docx - no need for Docling.
    if ext == ".docx":
        return _extract_docx(data)

    # Use Docling for formats that genuinely benefit from OCR / layout parsing.
    if settings.use_docling and ext in (".pdf", ".pptx", ".png", ".jpg", ".jpeg", ".tiff"):
        tmp_dir = os.path.join(settings.data_dir, "uploads")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, f"_tmp_{os.getpid()}{ext}")
        try:
            with open(tmp_path, "wb") as f:
                f.write(data)
            text = _extract_with_docling(tmp_path)
            if text:
                return text
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if ext == ".docx":
        return _extract_docx(data)
    if ext == ".pdf":
        return _extract_pdf(data)
    # plain text / markdown / everything else
    try:
        return data.decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001
        return ""
