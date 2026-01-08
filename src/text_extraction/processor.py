"""
Two-Pass OCR Processor
======================

Implements the two-pass OCR processing strategy extracted from service/main.py.

The processor routes pages to appropriate extraction methods based on
PDF classification results and quality preferences.

Usage:
    processor = TwoPassProcessor(
        primary_backend=LangdockBackend(),
        fallback_backend=TesseractBackend()
    )
    result = processor.extract(pdf_path, quality="balanced")
"""

from pathlib import Path
from typing import Optional, List

import fitz  # PyMuPDF

from text_extraction import PDFTypeDetector, PDFClassificationResult
from text_extraction.backends.base import (
    BaseOCRBackend,
    PageOCRResult,
    ExtractionMethod,
)
from text_extraction.models import (
    Quality,
    ProcessorConfig,
    ExtractionResult,
)


class TwoPassProcessor:
    """Two-pass OCR processor for PDF text extraction with fallback support."""

    def __init__(
        self,
        primary_backend: Optional[BaseOCRBackend] = None,
        fallback_backend: Optional[BaseOCRBackend] = None,
        config: Optional[ProcessorConfig] = None,
    ):
        """
        Initialize the TwoPassProcessor.

        Args:
            primary_backend: Primary OCR backend (e.g., LangdockBackend)
            fallback_backend: Fallback OCR backend (e.g., TesseractBackend)
            config: Processor configuration
        """
        self.primary_backend = primary_backend
        self.fallback_backend = fallback_backend
        self.config = config or ProcessorConfig()
        self.detector = PDFTypeDetector()

    def extract(
        self,
        pdf_path: Path,
        quality: str = "balanced",
    ) -> ExtractionResult:
        """
        Extract text from a PDF file using the two-pass strategy.

        Args:
            pdf_path: Path to the PDF file
            quality: Extraction quality ("fast", "balanced", "accurate")

        Returns:
            ExtractionResult with extracted text and metadata
        """
        import time

        start_time = time.time()
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            return ExtractionResult(
                success=False,
                file_name=pdf_path.name,
                pdf_type="unknown",
                total_pages=0,
                text="",
                word_count=0,
                confidence=0.0,
                processing_time_ms=0.0,
                extraction_method="none",
                error=f"File not found: {pdf_path}",
            )

        # Classify PDF first
        classification = self.detector.classify_pdf(pdf_path)

        # Open document
        doc = fitz.open(pdf_path)
        try:
            # Process all pages
            page_results = self._process_pages(
                doc=doc,
                pdf_path=pdf_path,
                classification=classification,
                quality=quality,
            )

            # Build full text with optional page markers
            text_parts = self._build_text_parts(page_results)
            full_text = "\n\n".join(text_parts)
            word_count = len(full_text.split())

            # Determine extraction method
            extraction_method = self._determine_extraction_method(
                classification=classification,
                page_results=page_results,
            )

            processing_time = (time.time() - start_time) * 1000

            return ExtractionResult(
                success=True,
                file_name=pdf_path.name,
                pdf_type=classification.pdf_type.value,
                total_pages=classification.total_pages,
                text=full_text,
                word_count=word_count,
                confidence=classification.confidence,
                processing_time_ms=processing_time,
                extraction_method=extraction_method,
                pages=page_results,
                metadata={
                    "quality": quality,
                    "text_pages": classification.text_pages,
                    "image_pages": classification.image_pages,
                    "hybrid_pages": classification.hybrid_pages,
                },
            )

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            return ExtractionResult(
                success=False,
                file_name=pdf_path.name,
                pdf_type=classification.pdf_type.value,
                total_pages=classification.total_pages,
                text="",
                word_count=0,
                confidence=0.0,
                processing_time_ms=processing_time,
                extraction_method="error",
                error=str(e),
            )
        finally:
            doc.close()

    def _process_pages(
        self,
        doc: fitz.Document,
        pdf_path: Path,
        classification: PDFClassificationResult,
        quality: str,
    ) -> List[PageOCRResult]:
        """
        Process all pages of the document.

        Args:
            doc: PyMuPDF document object
            pdf_path: Path to PDF file
            classification: PDF classification result
            quality: Extraction quality preference

        Returns:
            List of PageOCRResult for each page
        """
        import time

        results: List[PageOCRResult] = []

        for page_num in range(len(doc)):
            page_start = time.time()
            page = doc[page_num]
            page_number = page_num + 1  # 1-indexed

            # Determine if this page needs OCR
            needs_ocr = self._page_needs_ocr(
                page_number=page_number,
                classification=classification,
                quality=quality,
            )

            # Extract text
            text, method, backend_name = self._extract_page_text(
                page=page,
                pdf_path=pdf_path,
                page_number=page_number,
                needs_ocr=needs_ocr,
            )

            page_time = (time.time() - page_start) * 1000

            results.append(
                PageOCRResult(
                    page_number=page_number,
                    text=text,
                    confidence=1.0 if method == ExtractionMethod.DIRECT else 0.9,
                    method=method,
                    word_count=len(text.split()) if text else 0,
                    processing_time_ms=page_time,
                )
            )

        return results

    def _page_needs_ocr(
        self,
        page_number: int,
        classification: PDFClassificationResult,
        quality: str,
    ) -> bool:
        """
        Determine if a page needs OCR based on classification and quality.

        Args:
            page_number: 1-indexed page number
            classification: PDF classification result
            quality: Extraction quality preference

        Returns:
            True if the page should be processed with OCR
        """
        if quality == "fast":
            return False

        # Always OCR image pages for balanced and accurate quality
        if page_number in classification.image_pages:
            return True

        # For accurate quality, also OCR hybrid pages
        if quality == "accurate" and page_number in classification.hybrid_pages:
            return True

        return False

    def _extract_page_text(
        self,
        page: fitz.Page,
        pdf_path: Path,
        page_number: int,
        needs_ocr: bool,
    ) -> tuple[str, ExtractionMethod, str]:
        """
        Extract text from a single page.

        Args:
            page: PyMuPDF page object
            pdf_path: Path to PDF file
            page_number: 1-indexed page number
            needs_ocr: Whether to use OCR for this page

        Returns:
            Tuple of (text, method, backend_name)
        """
        if needs_ocr and self.primary_backend:
            text, method, backend_name = self._extract_with_ocr(
                pdf_path=pdf_path,
                page_number=page_number,
            )
            if text.strip():
                return text, method, backend_name

        # Direct extraction fallback
        text = page.get_text()
        return text, ExtractionMethod.DIRECT, "direct"

    def _extract_with_ocr(
        self,
        pdf_path: Path,
        page_number: int,
    ) -> tuple[str, ExtractionMethod, str]:
        """
        Extract text using OCR with fallback support.

        Args:
            pdf_path: Path to PDF file
            page_number: 1-indexed page number

        Returns:
            Tuple of (text, method, backend_name)
        """
        # Try primary backend
        if self.primary_backend and self.primary_backend.is_available():
            try:
                result = self.primary_backend.extract_text(
                    pdf_path, page_number=page_number
                )
                if result.text.strip():
                    return result.text, result.method, self.primary_backend.name
            except Exception as e:
                print(
                    f"OCR ({self.primary_backend.name}) failed for "
                    f"page {page_number}: {e}"
                )

        # Fallback to secondary backend
        if (
            self.config.fallback_on_error
            and self.fallback_backend
            and self.fallback_backend.is_available()
        ):
            try:
                result = self.fallback_backend.extract_text(
                    pdf_path, page_number=page_number
                )
                if result.text.strip():
                    return result.text, result.method, self.fallback_backend.name
            except Exception as e:
                print(
                    f"Fallback OCR ({self.fallback_backend.name}) failed for "
                    f"page {page_number}: {e}"
                )

        return "", ExtractionMethod.DIRECT, "none"

    def _build_text_parts(
        self,
        page_results: List[PageOCRResult],
    ) -> List[str]:
        """
        Build text parts from page results with optional markers.

        Args:
            page_results: List of page OCR results

        Returns:
            List of formatted text strings
        """
        text_parts: List[str] = []

        for result in page_results:
            if not result.text.strip():
                continue

            if self.config.include_page_markers:
                if result.method == ExtractionMethod.DIRECT:
                    marker = f"--- Page {result.page_number} ---"
                else:
                    backend_info = result.method.value
                    marker = f"--- Page {result.page_number} (OCR: {backend_info}) ---"
                text_parts.append(f"{marker}\n{result.text}")
            else:
                text_parts.append(result.text)

        return text_parts

    def _determine_extraction_method(
        self,
        classification: PDFClassificationResult,
        page_results: List[PageOCRResult],
    ) -> str:
        """
        Determine the overall extraction method used.

        Args:
            classification: PDF classification result
            page_results: List of page results

        Returns:
            String describing the extraction method
        """
        used_ocr = any(
            r.method != ExtractionMethod.DIRECT for r in page_results
        )

        if used_ocr:
            # Find which backends were used
            backends_used = set()
            for r in page_results:
                if r.method != ExtractionMethod.DIRECT:
                    backends_used.add(r.method.value)

            if backends_used:
                backend_str = ", ".join(sorted(backends_used))
                return f"hybrid (direct + {backend_str})"

        # No OCR used
        from text_extraction import PDFType

        if classification.pdf_type == PDFType.PURE_IMAGE:
            if self.primary_backend:
                return f"direct (no OCR backend available)"
            return "direct"

        return "direct"
