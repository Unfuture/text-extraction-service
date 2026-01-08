"""
OCR Backends
============

Multiple OCR backend implementations for text extraction.

Available Backends:
- LangdockBackend: LLM-based OCR (Claude, GPT-4o) via Langdock API
- TesseractBackend: Local Tesseract OCR (offline, free)

Usage:
    from text_extraction.backends import LangdockBackend, TesseractBackend

    # LLM-based OCR (best quality)
    langdock = LangdockBackend(api_key="...", model="claude-sonnet-4-5")
    if langdock.is_available():
        result = langdock.extract_text(Path("scan.pdf"), page_number=1)

    # Local fallback (free, offline)
    tesseract = TesseractBackend(lang="deu+eng")
    if tesseract.is_available():
        result = tesseract.extract_text(Path("scan.pdf"), page_number=1)
"""

from .base import (
    BaseOCRBackend,
    OCRResult,
    PageOCRResult,
    DocumentOCRResult,
    ExtractionMethod,
)
from .langdock import LangdockBackend
from .tesseract import TesseractBackend

__all__ = [
    "BaseOCRBackend",
    "OCRResult",
    "PageOCRResult",
    "DocumentOCRResult",
    "ExtractionMethod",
    "LangdockBackend",
    "TesseractBackend",
]
