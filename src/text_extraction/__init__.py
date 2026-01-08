"""
Text Extraction Service
=======================

A standalone text extraction library for PDF and image files with intelligent OCR routing.

Features:
- PDF Type Detection (PURE_TEXT, PURE_IMAGE, HYBRID)
- Two-Pass OCR Strategy for scanned documents
- Multi-backend support (LLM OCR, Tesseract)
- Structured JSON output with confidence scores

Basic Usage:
    from text_extraction import extract_text, PDFTypeDetector

    # Simple extraction
    result = extract_text("document.pdf")
    print(result.text)

    # PDF classification only
    detector = PDFTypeDetector()
    classification = detector.classify_pdf("document.pdf")
    print(classification.pdf_type)  # PURE_TEXT, PURE_IMAGE, or HYBRID

Advanced Usage:
    from text_extraction import TextExtractor
    from text_extraction.backends import LangdockBackend, TesseractBackend

    # Configure with specific backend
    extractor = TextExtractor(
        backend=LangdockBackend(api_key="..."),
        fallback=TesseractBackend()
    )
    result = extractor.extract("document.pdf", quality="accurate")
"""

__version__ = "0.1.0"
__author__ = "Unfuture"

from .detector import PDFType, PDFTypeDetector, PDFClassificationResult, PageAnalysis
from .models import Quality, ProcessorConfig, ExtractionResult
from .processor import TwoPassProcessor
from .router import ContentRouter, RoutingDecision, RoutingStrategy, CostEstimate

__all__ = [
    # Version
    "__version__",
    # PDF Detection
    "PDFType",
    "PDFTypeDetector",
    "PDFClassificationResult",
    "PageAnalysis",
    # Routing
    "ContentRouter",
    "RoutingDecision",
    "RoutingStrategy",
    "CostEstimate",
    # Processing
    "TwoPassProcessor",
    "ProcessorConfig",
    "ExtractionResult",
    "Quality",
]
