"""
PDF Type Detector - Issue #4 Phase 0
=====================================

Block-Type Based PDF Classification using PyMuPDF's native block detection.

This module provides precise PDF classification (Pure Text, Pure Image, Hybrid)
based on PyMuPDF's block['type'] property, which is more reliable than
line-counting heuristics.

Motivation:
- Hybrid PDFs are currently treated as Pure Image (expensive OCR for all pages)
- Block-type detection enables page-by-page routing for Hybrid PDFs
- Cost savings: ~€3,600/year at 60K invoices (30% Hybrid PDFs)

Usage:
    from pdf_type_detector import PDFTypeDetector, PDFType

    detector = PDFTypeDetector()
    result = detector.classify_pdf("invoice.pdf")

    if result.pdf_type == PDFType.HYBRID:
        # Route pages individually
        for page_num in result.image_pages:
            process_with_ocr(page_num)
        for page_num in result.text_pages:
            process_normal(page_num)

Author: Claude Code (Issue #4 Phase 0)
Date: 2025-10-24
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from enum import Enum
import logging
import fitz  # PyMuPDF

# Configure logging
logger = logging.getLogger(__name__)


class PDFType(Enum):
    """PDF classification based on content structure."""
    PURE_TEXT = "pure_text"    # All pages have readable text blocks
    PURE_IMAGE = "pure_image"  # All pages are scanned/image-based
    HYBRID = "hybrid"          # Mixed: some text pages, some image pages
    UNKNOWN = "unknown"        # Classification failed or empty PDF


@dataclass
class PageAnalysis:
    """Analysis result for a single page."""
    page_number: int  # 1-indexed
    text_blocks: int
    image_blocks: int
    total_blocks: int
    is_text_dominant: bool  # True if text_blocks > image_blocks
    is_image_dominant: bool  # True if image_blocks > text_blocks
    has_mixed_content: bool  # True if both text and image blocks present


@dataclass
class PDFClassificationResult:
    """Complete PDF classification result."""
    pdf_type: PDFType
    total_pages: int
    text_pages: List[int] = field(default_factory=list)   # Pages with text
    image_pages: List[int] = field(default_factory=list)  # Pages with images
    hybrid_pages: List[int] = field(default_factory=list) # Pages with both

    # Statistics
    total_text_blocks: int = 0
    total_image_blocks: int = 0
    page_analyses: List[PageAnalysis] = field(default_factory=list)

    # Confidence score (0.0-1.0)
    confidence: float = 1.0

    def __str__(self) -> str:
        """Human-readable representation."""
        return (
            f"PDFType: {self.pdf_type.value}\n"
            f"Pages: {self.total_pages} "
            f"(Text: {len(self.text_pages)}, "
            f"Image: {len(self.image_pages)}, "
            f"Hybrid: {len(self.hybrid_pages)})\n"
            f"Blocks: {self.total_text_blocks} text, "
            f"{self.total_image_blocks} image\n"
            f"Confidence: {self.confidence:.2f}"
        )


class PDFTypeDetector:
    """
    PDF Type Detector using PyMuPDF block['type'] detection.

    Classification Logic:
    - Page-level: Count text blocks (type=0) vs image blocks (type=1)
    - PDF-level: Classify based on page composition

    Thresholds:
    - text_block_threshold: Minimum text blocks to consider page "text"
    - image_block_threshold: Minimum image blocks to consider page "image"
    """

    def __init__(
        self,
        text_block_threshold: int = 2,
        image_block_threshold: int = 1
    ):
        """
        Initialize PDF Type Detector.

        Args:
            text_block_threshold: Min text blocks for "text page" (default: 2)
            image_block_threshold: Min image blocks for "image page" (default: 1)
        """
        self.text_block_threshold = text_block_threshold
        self.image_block_threshold = image_block_threshold

        logger.info(
            f"PDFTypeDetector initialized: "
            f"text_threshold={text_block_threshold}, "
            f"image_threshold={image_block_threshold}"
        )

    def analyze_page(
        self,
        page: fitz.Page,
        page_number: int
    ) -> PageAnalysis:
        """
        Analyze a single page using block['type'] detection.

        Args:
            page: PyMuPDF page object
            page_number: Page number (1-indexed)

        Returns:
            PageAnalysis with block counts and classification
        """
        text_blocks = 0
        image_blocks = 0

        # Get page blocks in dict format
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            block_type = block.get("type", -1)

            if block_type == 0:  # Text block
                text_blocks += 1
            elif block_type == 1:  # Image block
                image_blocks += 1

        total_blocks = text_blocks + image_blocks

        # Classify page
        is_text_dominant = text_blocks >= self.text_block_threshold
        is_image_dominant = image_blocks >= self.image_block_threshold
        has_mixed_content = is_text_dominant and is_image_dominant

        return PageAnalysis(
            page_number=page_number,
            text_blocks=text_blocks,
            image_blocks=image_blocks,
            total_blocks=total_blocks,
            is_text_dominant=is_text_dominant,
            is_image_dominant=is_image_dominant,
            has_mixed_content=has_mixed_content
        )

    def classify_pdf(self, pdf_path: Path | str) -> PDFClassificationResult:
        """
        Classify PDF type using block-type detection.

        Args:
            pdf_path: Path to PDF file

        Returns:
            PDFClassificationResult with classification and statistics

        Raises:
            FileNotFoundError: If PDF doesn't exist
            Exception: If PDF cannot be opened or processed
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Classifying PDF: {pdf_path.name}")

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            if total_pages == 0:
                logger.warning(f"Empty PDF: {pdf_path.name}")
                doc.close()
                return PDFClassificationResult(
                    pdf_type=PDFType.UNKNOWN,
                    total_pages=0,
                    confidence=0.0
                )

            # Analyze each page
            page_analyses = []
            text_pages = []
            image_pages = []
            hybrid_pages = []
            total_text_blocks = 0
            total_image_blocks = 0

            for page_num in range(total_pages):
                page = doc[page_num]
                analysis = self.analyze_page(page, page_num + 1)

                page_analyses.append(analysis)
                total_text_blocks += analysis.text_blocks
                total_image_blocks += analysis.image_blocks

                # Categorize page
                if analysis.has_mixed_content:
                    hybrid_pages.append(page_num + 1)
                elif analysis.is_text_dominant:
                    text_pages.append(page_num + 1)
                elif analysis.is_image_dominant:
                    image_pages.append(page_num + 1)
                else:
                    # Page has insufficient blocks - treat as image (scanned)
                    image_pages.append(page_num + 1)

            doc.close()

            # Classify PDF based on page composition
            pdf_type = self._classify_pdf_type(
                total_pages=total_pages,
                text_page_count=len(text_pages),
                image_page_count=len(image_pages),
                hybrid_page_count=len(hybrid_pages)
            )

            # Calculate confidence
            confidence = self._calculate_confidence(
                total_text_blocks=total_text_blocks,
                total_image_blocks=total_image_blocks,
                total_pages=total_pages
            )

            result = PDFClassificationResult(
                pdf_type=pdf_type,
                total_pages=total_pages,
                text_pages=text_pages,
                image_pages=image_pages,
                hybrid_pages=hybrid_pages,
                total_text_blocks=total_text_blocks,
                total_image_blocks=total_image_blocks,
                page_analyses=page_analyses,
                confidence=confidence
            )

            logger.info(
                f"PDF classified: {pdf_path.name} → {pdf_type.value} "
                f"({len(text_pages)} text, {len(image_pages)} image, "
                f"{len(hybrid_pages)} hybrid pages)"
            )

            return result

        except Exception as e:
            logger.error(f"Error classifying PDF {pdf_path.name}: {e}")
            raise

    def _classify_pdf_type(
        self,
        total_pages: int,
        text_page_count: int,
        image_page_count: int,
        hybrid_page_count: int
    ) -> PDFType:
        """
        Classify PDF type based on page composition.

        Logic:
        - PURE_TEXT: All pages are text-dominant
        - PURE_IMAGE: All pages are image-dominant
        - HYBRID: Mixed pages
        """
        if text_page_count == total_pages:
            return PDFType.PURE_TEXT

        if image_page_count == total_pages:
            return PDFType.PURE_IMAGE

        # Any mix of page types = HYBRID
        return PDFType.HYBRID

    def _calculate_confidence(
        self,
        total_text_blocks: int,
        total_image_blocks: int,
        total_pages: int
    ) -> float:
        """
        Calculate classification confidence score.

        High confidence: Clear dominance of one block type
        Low confidence: Roughly equal text/image blocks
        """
        if total_pages == 0:
            return 0.0

        total_blocks = total_text_blocks + total_image_blocks

        if total_blocks == 0:
            return 0.5  # No blocks found - uncertain

        # Calculate ratio of dominant type
        max_blocks = max(total_text_blocks, total_image_blocks)
        confidence = max_blocks / total_blocks

        return confidence


# Helper function for quick classification
def classify_pdf(pdf_path: Path | str) -> PDFClassificationResult:
    """
    Quick helper to classify a PDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        PDFClassificationResult
    """
    detector = PDFTypeDetector()
    return detector.classify_pdf(pdf_path)


if __name__ == "__main__":
    # Quick test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_type_detector.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    result = classify_pdf(pdf_path)
    print(result)
