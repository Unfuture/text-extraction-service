"""
OCR Backends
============

Multiple OCR backend implementations for text extraction.

Available Backends:
- LangdockBackend: LLM-based OCR (Claude, GPT-4o) via Langdock API
- TesseractBackend: Local Tesseract OCR (offline, free)
- CloudVisionBackend: Google Cloud Vision API (optional)

Usage:
    from text_extraction.backends import LangdockBackend, TesseractBackend

    # LLM-based OCR (best quality)
    langdock = LangdockBackend(
        api_key="...",
        model="claude-sonnet-4-5"
    )

    # Local fallback (free, offline)
    tesseract = TesseractBackend(lang="deu")
"""

from .base import BaseOCRBackend, OCRResult

__all__ = [
    "BaseOCRBackend",
    "OCRResult",
]
