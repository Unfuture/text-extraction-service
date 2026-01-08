"""
Content Router for PDF Text Extraction
======================================

Routes PDF pages to appropriate extraction methods based on
classification results and quality preferences.

Usage:
    from text_extraction import ContentRouter, PDFTypeDetector

    detector = PDFTypeDetector()
    router = ContentRouter()

    classification = detector.classify_pdf("document.pdf")
    decision = router.route(classification, quality="balanced")

    print(f"Direct pages: {decision.direct_pages}")
    print(f"OCR pages: {decision.ocr_pages}")
    print(f"Estimated cost: EUR {decision.estimated_cost:.3f}")

Routing Matrix:
    | PDF Type    | fast        | balanced       | accurate        |
    |-------------|-------------|----------------|-----------------|
    | PURE_TEXT   | Direct all  | Direct all     | Direct all      |
    | PURE_IMAGE  | Direct all  | OCR all        | OCR all         |
    | HYBRID      | Direct all  | OCR image pgs  | OCR img+hybrid  |
"""

from dataclasses import dataclass
from enum import Enum

from text_extraction.backends.base import BaseOCRBackend
from text_extraction.detector import PDFClassificationResult, PDFType


class RoutingStrategy(Enum):
    """Routing strategy for PDF extraction."""
    DIRECT_ONLY = "direct_only"       # No OCR, direct extraction only
    OCR_ALL = "ocr_all"               # OCR for all pages
    OCR_SELECTIVE = "ocr_selective"   # OCR for specific pages only


@dataclass
class CostEstimate:
    """Cost and time estimation for extraction operations."""
    ocr_cost_eur: float
    direct_cost_eur: float = 0.0
    total_cost_eur: float = 0.0
    ocr_time_seconds: float = 0.0
    direct_time_seconds: float = 0.0
    total_time_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Calculate totals after initialization."""
        self.total_cost_eur = self.ocr_cost_eur + self.direct_cost_eur
        self.total_time_seconds = self.ocr_time_seconds + self.direct_time_seconds


@dataclass
class RoutingDecision:
    """Routing decision from ContentRouter.route()."""
    pdf_type: PDFType
    strategy: RoutingStrategy
    direct_pages: list[int]           # Pages for direct extraction (1-indexed)
    ocr_pages: list[int]              # Pages for OCR (1-indexed)
    estimated_cost: float             # Estimated cost in EUR
    estimated_time_seconds: float     # Estimated processing time

    # Optional metadata
    quality: str = "balanced"
    total_pages: int = 0
    reasoning: str = ""               # Human-readable explanation


class ContentRouter:
    """
    Routes PDF pages to appropriate extraction methods.

    Determines which pages should use direct text extraction vs OCR
    based on PDF classification and quality preference.

    Attributes:
        primary_backend: Primary OCR backend (optional)
        fallback_backend: Fallback OCR backend (optional)
        cost_per_ocr_page: Cost per page for LLM OCR (default: 0.005 EUR)
        time_per_ocr_page: Time per OCR page in seconds (default: 3.0)
        time_per_direct_page: Time per direct extraction in seconds (default: 0.1)
    """

    # Default cost assumptions (Claude Sonnet via Langdock)
    DEFAULT_COST_PER_OCR_PAGE = 0.005  # EUR per page
    DEFAULT_TIME_PER_OCR_PAGE = 3.0     # seconds
    DEFAULT_TIME_PER_DIRECT_PAGE = 0.1  # seconds

    def __init__(
        self,
        primary_backend: BaseOCRBackend | None = None,
        fallback_backend: BaseOCRBackend | None = None,
        cost_per_ocr_page: float = DEFAULT_COST_PER_OCR_PAGE,
        time_per_ocr_page: float = DEFAULT_TIME_PER_OCR_PAGE,
        time_per_direct_page: float = DEFAULT_TIME_PER_DIRECT_PAGE,
    ) -> None:
        """
        Initialize ContentRouter.

        Args:
            primary_backend: Primary OCR backend for image pages
            fallback_backend: Fallback OCR backend if primary fails
            cost_per_ocr_page: Cost per OCR page in EUR
            time_per_ocr_page: Estimated time per OCR page in seconds
            time_per_direct_page: Estimated time per direct extraction in seconds
        """
        self.primary_backend = primary_backend
        self.fallback_backend = fallback_backend
        self.cost_per_ocr_page = cost_per_ocr_page
        self.time_per_ocr_page = time_per_ocr_page
        self.time_per_direct_page = time_per_direct_page

    def route(
        self,
        classification: PDFClassificationResult,
        quality: str = "balanced",
    ) -> RoutingDecision:
        """
        Determine routing strategy for a classified PDF.

        Args:
            classification: PDFClassificationResult from detector
            quality: "fast", "balanced", or "accurate"

        Returns:
            RoutingDecision with pages to extract directly vs. with OCR
        """
        # Validate and normalize quality parameter
        if quality not in ("fast", "balanced", "accurate"):
            quality = "balanced"

        # Determine strategy based on PDF type and quality
        strategy = self._determine_strategy(classification.pdf_type, quality)

        # If no OCR backend available, force direct only
        if strategy != RoutingStrategy.DIRECT_ONLY and not self.has_ocr_backend():
            strategy = RoutingStrategy.DIRECT_ONLY

        # Select pages for each extraction method
        direct_pages, ocr_pages = self._select_pages(
            classification, strategy, quality
        )

        # Estimate cost and time
        estimate = self.estimate_cost(
            ocr_page_count=len(ocr_pages),
            direct_page_count=len(direct_pages),
        )

        # Generate reasoning
        reasoning = self._generate_reasoning(
            classification.pdf_type, quality, strategy, direct_pages, ocr_pages
        )

        return RoutingDecision(
            pdf_type=classification.pdf_type,
            strategy=strategy,
            direct_pages=direct_pages,
            ocr_pages=ocr_pages,
            estimated_cost=estimate.total_cost_eur,
            estimated_time_seconds=estimate.total_time_seconds,
            quality=quality,
            total_pages=classification.total_pages,
            reasoning=reasoning,
        )

    def estimate_cost(
        self,
        ocr_page_count: int,
        direct_page_count: int = 0,
    ) -> CostEstimate:
        """
        Estimate cost and time for extraction operations.

        Args:
            ocr_page_count: Number of pages requiring OCR
            direct_page_count: Number of pages for direct extraction

        Returns:
            CostEstimate with cost and time predictions
        """
        ocr_cost = ocr_page_count * self.cost_per_ocr_page
        ocr_time = ocr_page_count * self.time_per_ocr_page
        direct_time = direct_page_count * self.time_per_direct_page

        return CostEstimate(
            ocr_cost_eur=ocr_cost,
            direct_cost_eur=0.0,  # Direct extraction is free
            ocr_time_seconds=ocr_time,
            direct_time_seconds=direct_time,
        )

    def has_ocr_backend(self) -> bool:
        """
        Check if any OCR backend is available.

        Returns:
            True if at least one backend is available
        """
        if self.primary_backend and self.primary_backend.is_available():
            return True
        if self.fallback_backend and self.fallback_backend.is_available():
            return True
        return False

    def _determine_strategy(
        self,
        pdf_type: PDFType,
        quality: str,
    ) -> RoutingStrategy:
        """
        Map PDF type + quality to routing strategy.

        Strategy Matrix:
        | PDF Type    | fast        | balanced       | accurate        |
        |-------------|-------------|----------------|-----------------|
        | PURE_TEXT   | DIRECT_ONLY | DIRECT_ONLY    | DIRECT_ONLY     |
        | PURE_IMAGE  | DIRECT_ONLY | OCR_ALL        | OCR_ALL         |
        | HYBRID      | DIRECT_ONLY | OCR_SELECTIVE  | OCR_SELECTIVE   |
        | UNKNOWN     | DIRECT_ONLY | DIRECT_ONLY    | DIRECT_ONLY     |
        """
        # Fast quality: always direct only (no OCR regardless of PDF type)
        if quality == "fast":
            return RoutingStrategy.DIRECT_ONLY

        # PURE_TEXT: always direct (text is already extractable)
        if pdf_type == PDFType.PURE_TEXT:
            return RoutingStrategy.DIRECT_ONLY

        # PURE_IMAGE: OCR all pages (for balanced/accurate)
        if pdf_type == PDFType.PURE_IMAGE:
            return RoutingStrategy.OCR_ALL

        # HYBRID: selective OCR based on page type
        if pdf_type == PDFType.HYBRID:
            return RoutingStrategy.OCR_SELECTIVE

        # UNKNOWN: fallback to direct only
        return RoutingStrategy.DIRECT_ONLY

    def _select_pages(
        self,
        classification: PDFClassificationResult,
        strategy: RoutingStrategy,
        quality: str,
    ) -> tuple[list[int], list[int]]:
        """
        Select which pages go to direct extraction vs. OCR.

        Args:
            classification: PDF classification result
            strategy: Determined routing strategy
            quality: Quality preference

        Returns:
            Tuple of (direct_pages, ocr_pages) - both 1-indexed
        """
        all_pages = list(range(1, classification.total_pages + 1))

        if strategy == RoutingStrategy.DIRECT_ONLY:
            return all_pages, []

        if strategy == RoutingStrategy.OCR_ALL:
            return [], all_pages

        # OCR_SELECTIVE: route based on page type
        direct_pages = list(classification.text_pages)
        ocr_pages = list(classification.image_pages)

        # For accurate quality, also OCR hybrid pages
        if quality == "accurate":
            ocr_pages.extend(classification.hybrid_pages)
        else:
            # For balanced quality, treat hybrid pages as direct
            direct_pages.extend(classification.hybrid_pages)

        return sorted(direct_pages), sorted(ocr_pages)

    def _generate_reasoning(
        self,
        pdf_type: PDFType,
        quality: str,
        strategy: RoutingStrategy,
        direct_pages: list[int],
        ocr_pages: list[int],
    ) -> str:
        """
        Generate human-readable reasoning for the routing decision.

        Args:
            pdf_type: Classified PDF type
            quality: Quality preference
            strategy: Selected routing strategy
            direct_pages: Pages for direct extraction
            ocr_pages: Pages for OCR

        Returns:
            Human-readable explanation string
        """
        parts = []

        parts.append(f"PDF type: {pdf_type.value}")
        parts.append(f"Quality: {quality}")
        parts.append(f"Strategy: {strategy.value}")

        if direct_pages:
            if len(direct_pages) <= 5:
                parts.append(f"Direct extraction: pages {direct_pages}")
            else:
                parts.append(f"Direct extraction: {len(direct_pages)} pages")

        if ocr_pages:
            if len(ocr_pages) <= 5:
                parts.append(f"OCR extraction: pages {ocr_pages}")
            else:
                parts.append(f"OCR extraction: {len(ocr_pages)} pages")

        if not ocr_pages:
            parts.append("No OCR required")
        elif not self.has_ocr_backend():
            parts.append("(OCR backend unavailable, using direct only)")

        return " | ".join(parts)
