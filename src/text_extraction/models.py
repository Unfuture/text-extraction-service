"""
Data Models for Text Extraction
================================

Shared data models for the text extraction service.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

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
    pages: List[PageOCRResult] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Get concatenated text from all pages."""
        return self.text
