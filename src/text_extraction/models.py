"""
Data Models for Text Extraction
================================

Shared data models for the text extraction service.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from text_extraction.backends.base import PageOCRResult


class Quality(Enum):
    """Extraction quality preference."""

    FAST = "fast"  # Direct extraction only, no OCR
    BALANCED = "balanced"  # OCR for image pages only
    ACCURATE = "accurate"  # OCR verification for all pages


@dataclass
class ProcessorConfig:
    """Configuration for TwoPassProcessor."""

    text_threshold: int = 10
    enable_two_pass: bool = True
    confidence_threshold: float = 0.8
    fallback_on_error: bool = True
    include_page_markers: bool = True


@dataclass
class BackendStatus:
    """Status of OCR backends used during extraction."""

    primary_backend: str
    primary_available: bool
    fallback_backend: str | None = None
    fallback_available: bool = False
    attempted_pages: int = 0
    successful_pages: int = 0
    failed_pages: int = 0


@dataclass
class PageError:
    """Error from a specific page during OCR extraction."""

    page_number: int
    backend: str
    error: str


@dataclass
class ExtractionResult:
    """Result from the TwoPassProcessor extraction."""

    success: bool
    file_name: str
    pdf_type: str
    total_pages: int
    text: str
    word_count: int
    confidence: float
    processing_time_ms: float
    extraction_method: str
    pages: list[PageOCRResult] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    backend_status: BackendStatus | None = None
    page_errors: list[PageError] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Get concatenated text from all pages."""
        return self.text
