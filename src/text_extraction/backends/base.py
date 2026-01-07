"""
Base OCR Backend
================

Abstract base class for OCR backend implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
from enum import Enum


class ExtractionMethod(Enum):
    """Method used to extract text."""
    DIRECT = "direct"           # Native PDF text extraction
    LLM_OCR = "llm_ocr"        # LLM-based OCR (Claude, GPT, etc.)
    TESSERACT = "tesseract"    # Local Tesseract OCR
    CLOUD_VISION = "cloud_vision"  # Google Cloud Vision


@dataclass
class OCRResult:
    """Result from OCR extraction."""
    text: str
    confidence: float = 1.0
    method: ExtractionMethod = ExtractionMethod.DIRECT
    page_number: Optional[int] = None
    word_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Calculate word count if not provided."""
        if self.word_count == 0 and self.text:
            self.word_count = len(self.text.split())


@dataclass
class PageOCRResult:
    """OCR result for a single page."""
    page_number: int
    text: str
    confidence: float
    method: ExtractionMethod
    word_count: int = 0
    processing_time_ms: float = 0.0


@dataclass
class DocumentOCRResult:
    """Complete OCR result for a document."""
    success: bool
    file_name: str
    pages: List[PageOCRResult]
    total_pages: int
    total_word_count: int = 0
    processing_time_ms: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Concatenate text from all pages."""
        return "\n\n".join(page.text for page in self.pages if page.text)


class BaseOCRBackend(ABC):
    """
    Abstract base class for OCR backends.

    All OCR backends must implement:
    - extract_text(): Extract text from a single page/image
    - is_available(): Check if the backend is available

    Optional overrides:
    - extract_document(): Process multi-page documents
    - get_supported_formats(): Return supported file formats
    """

    def __init__(self, name: str = "BaseOCR"):
        """
        Initialize backend.

        Args:
            name: Human-readable name for the backend
        """
        self.name = name

    @abstractmethod
    def extract_text(
        self,
        file_path: Path,
        page_number: Optional[int] = None,
        **kwargs
    ) -> OCRResult:
        """
        Extract text from a file or specific page.

        Args:
            file_path: Path to PDF or image file
            page_number: Specific page to extract (1-indexed), None for all
            **kwargs: Backend-specific options

        Returns:
            OCRResult with extracted text and metadata
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this backend is available and configured.

        Returns:
            True if backend can be used, False otherwise
        """
        pass

    def extract_document(
        self,
        file_path: Path,
        pages: Optional[List[int]] = None,
        **kwargs
    ) -> DocumentOCRResult:
        """
        Extract text from entire document or specific pages.

        Default implementation calls extract_text() for each page.
        Backends may override for optimized batch processing.

        Args:
            file_path: Path to document
            pages: List of page numbers (1-indexed), None for all
            **kwargs: Backend-specific options

        Returns:
            DocumentOCRResult with all page results
        """
        import time
        start_time = time.time()

        results: List[PageOCRResult] = []
        total_word_count = 0

        try:
            # Determine pages to process
            if pages is None:
                # Get page count from file
                pages = self._get_page_numbers(file_path)

            for page_num in pages:
                page_start = time.time()
                result = self.extract_text(file_path, page_number=page_num, **kwargs)
                page_time = (time.time() - page_start) * 1000

                page_result = PageOCRResult(
                    page_number=page_num,
                    text=result.text,
                    confidence=result.confidence,
                    method=result.method,
                    word_count=result.word_count,
                    processing_time_ms=page_time
                )
                results.append(page_result)
                total_word_count += result.word_count

            total_time = (time.time() - start_time) * 1000

            return DocumentOCRResult(
                success=True,
                file_name=file_path.name,
                pages=results,
                total_pages=len(results),
                total_word_count=total_word_count,
                processing_time_ms=total_time,
                metadata={"backend": self.name}
            )

        except Exception as e:
            return DocumentOCRResult(
                success=False,
                file_name=file_path.name,
                pages=[],
                total_pages=0,
                error=str(e),
                processing_time_ms=(time.time() - start_time) * 1000
            )

    def _get_page_numbers(self, file_path: Path) -> List[int]:
        """Get list of page numbers for a document."""
        try:
            import fitz
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()
            return list(range(1, page_count + 1))
        except Exception:
            # For images, return single page
            return [1]

    def get_supported_formats(self) -> List[str]:
        """
        Return list of supported file formats.

        Returns:
            List of file extensions (e.g., ['.pdf', '.png', '.jpg'])
        """
        return ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp']

    def __repr__(self) -> str:
        available = "available" if self.is_available() else "unavailable"
        return f"{self.__class__.__name__}(name='{self.name}', {available})"
