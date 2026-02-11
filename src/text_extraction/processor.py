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

import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

from text_extraction import PDFClassificationResult, PDFTypeDetector
from text_extraction.backends.base import (
    BaseOCRBackend,
    ExtractionMethod,
    PageOCRResult,
)
from text_extraction.models import (
    BackendStatus,
    ExtractionResult,
    PageError,
    ProcessorConfig,
)


class TwoPassProcessor:
    """Two-pass OCR processor for PDF text extraction with fallback support."""

    def __init__(
        self,
        primary_backend: BaseOCRBackend | None = None,
        fallback_backend: BaseOCRBackend | None = None,
        config: ProcessorConfig | None = None,
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
        model: str | None = None,
    ) -> ExtractionResult:
        """
        Extract text from a PDF file using the two-pass strategy.

        Args:
            pdf_path: Path to the PDF file
            quality: Extraction quality ("fast", "balanced", "accurate")
            model: Optional model override for OCR backend

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

        # Build backend status
        backend_status = self._build_backend_status()

        # Open document
        doc = fitz.open(pdf_path)
        try:
            # Process all pages
            page_results, page_errors = self._process_pages(
                doc=doc,
                pdf_path=pdf_path,
                classification=classification,
                quality=quality,
                model=model,
            )

            # Update backend status with page counts
            ocr_pages = [
                r for r in page_results
                if self._page_needs_ocr(r.page_number, classification, quality)
            ]
            backend_status.attempted_pages = len(ocr_pages)
            backend_status.failed_pages = len(page_errors)
            backend_status.successful_pages = (
                backend_status.attempted_pages - backend_status.failed_pages
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
                backend_status=backend_status,
                page_errors=page_errors,
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
        model: str | None = None,
    ) -> tuple[list[PageOCRResult], list[PageError]]:
        """
        Process all pages of the document.

        Args:
            doc: PyMuPDF document object
            pdf_path: Path to PDF file
            classification: PDF classification result
            quality: Extraction quality preference
            model: Optional model override for OCR backend

        Returns:
            Tuple of (page results, page errors)
        """
        import time

        results: list[PageOCRResult] = []
        page_errors: list[PageError] = []

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
            text, method, backend_name, error = self._extract_page_text(
                page=page,
                pdf_path=pdf_path,
                page_number=page_number,
                needs_ocr=needs_ocr,
                model=model,
            )

            if error and needs_ocr:
                page_errors.append(
                    PageError(
                        page_number=page_number,
                        backend=backend_name,
                        error=error,
                    )
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

        return results, page_errors

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
        model: str | None = None,
    ) -> tuple[str, ExtractionMethod, str, str | None]:
        """
        Extract text from a single page.

        Args:
            page: PyMuPDF page object
            pdf_path: Path to PDF file
            page_number: 1-indexed page number
            needs_ocr: Whether to use OCR for this page
            model: Optional model override for OCR backend

        Returns:
            Tuple of (text, method, backend_name, error_message)
        """
        if needs_ocr and self.primary_backend:
            text, method, backend_name, error = self._extract_with_ocr(
                pdf_path=pdf_path,
                page_number=page_number,
                model=model,
            )
            if text.strip():
                return text, method, backend_name, None
            # OCR failed or returned empty — fall through to direct with error
            direct_text = page.get_text()
            return direct_text, ExtractionMethod.DIRECT, "direct", error

        # Direct extraction (no OCR needed or no backend)
        text = page.get_text()
        return text, ExtractionMethod.DIRECT, "direct", None

    def _extract_with_ocr(
        self,
        pdf_path: Path,
        page_number: int,
        model: str | None = None,
    ) -> tuple[str, ExtractionMethod, str, str | None]:
        """
        Extract text using OCR with fallback support.

        Args:
            pdf_path: Path to PDF file
            page_number: 1-indexed page number
            model: Optional model override for OCR backend

        Returns:
            Tuple of (text, method, backend_name, error_message)
        """
        primary_error = "backend unavailable"

        # Try primary backend
        if self.primary_backend and self.primary_backend.is_available():
            try:
                result = self.primary_backend.extract_text(
                    pdf_path, page_number=page_number, model=model
                )
                if result.text.strip():
                    return result.text, result.method, self.primary_backend.name, None
                primary_error = "empty response from primary backend"
            except Exception as e:
                err_str = str(e)
                retryable = "RetryableError" in type(e).__name__ or (
                    hasattr(e, "__cause__")
                    and "Retryable" in type(e.__cause__).__name__
                )
                if retryable:
                    logger.warning(
                        "OCR (%s) failed for page %d after all retries: %s",
                        self.primary_backend.name,
                        page_number,
                        err_str,
                    )
                else:
                    logger.warning(
                        "OCR (%s) failed for page %d: %s",
                        self.primary_backend.name,
                        page_number,
                        err_str,
                    )
                primary_error = err_str

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
                    return result.text, result.method, self.fallback_backend.name, None
            except Exception as e:
                logger.warning(
                    "Fallback OCR (%s) failed for page %d: %s",
                    self.fallback_backend.name,
                    page_number,
                    e,
                )
                return "", ExtractionMethod.DIRECT, "none", str(e)

        return "", ExtractionMethod.DIRECT, "none", primary_error

    def _build_backend_status(self) -> BackendStatus:
        """Build a BackendStatus from current processor configuration."""
        return BackendStatus(
            primary_backend=self.primary_backend.name if self.primary_backend else "none",
            primary_available=(
                self.primary_backend.is_available() if self.primary_backend else False
            ),
            fallback_backend=(
                self.fallback_backend.name if self.fallback_backend else None
            ),
            fallback_available=(
                self.fallback_backend.is_available() if self.fallback_backend else False
            ),
        )

    def _build_text_parts(
        self,
        page_results: list[PageOCRResult],
    ) -> list[str]:
        """
        Build text parts from page results with optional markers.

        Args:
            page_results: List of page OCR results

        Returns:
            List of formatted text strings
        """
        text_parts: list[str] = []

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
        page_results: list[PageOCRResult],
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
                return "direct (no OCR backend available)"
            return "direct"

        return "direct"
