"""
Unit Tests for ContentRouter
============================

Tests for the ContentRouter class that determines page routing
for PDF text extraction.

Coverage Target: >90%
"""

import pytest
from pathlib import Path

from text_extraction import PDFType, PDFClassificationResult
from text_extraction.router import (
    ContentRouter,
    RoutingDecision,
    RoutingStrategy,
    CostEstimate,
)
from text_extraction.backends.base import BaseOCRBackend, OCRResult, ExtractionMethod


# =============================================================================
# Mock Backend for Testing
# =============================================================================


class MockOCRBackend(BaseOCRBackend):
    """Mock OCR backend for testing."""

    def __init__(self, name: str = "MockOCR", available: bool = True):
        super().__init__(name)
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def extract_text(self, file_path: Path, page_number: int = None, **kwargs) -> OCRResult:
        return OCRResult(text="Mock text", method=ExtractionMethod.LLM_OCR)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_available_backend():
    """Create an available mock backend."""
    return MockOCRBackend(name="AvailableBackend", available=True)


@pytest.fixture
def mock_unavailable_backend():
    """Create an unavailable mock backend."""
    return MockOCRBackend(name="UnavailableBackend", available=False)


@pytest.fixture
def text_classification():
    """Create a PURE_TEXT classification result."""
    return PDFClassificationResult(
        pdf_type=PDFType.PURE_TEXT,
        total_pages=3,
        text_pages=[1, 2, 3],
        image_pages=[],
        hybrid_pages=[],
        confidence=0.95,
    )


@pytest.fixture
def image_classification():
    """Create a PURE_IMAGE classification result."""
    return PDFClassificationResult(
        pdf_type=PDFType.PURE_IMAGE,
        total_pages=2,
        text_pages=[],
        image_pages=[1, 2],
        hybrid_pages=[],
        confidence=0.90,
    )


@pytest.fixture
def hybrid_classification():
    """Create a HYBRID classification result."""
    return PDFClassificationResult(
        pdf_type=PDFType.HYBRID,
        total_pages=4,
        text_pages=[1, 3],
        image_pages=[2],
        hybrid_pages=[4],
        confidence=0.85,
    )


@pytest.fixture
def unknown_classification():
    """Create an UNKNOWN classification result."""
    return PDFClassificationResult(
        pdf_type=PDFType.UNKNOWN,
        total_pages=1,
        text_pages=[],
        image_pages=[],
        hybrid_pages=[],
        confidence=0.0,
    )


# =============================================================================
# RoutingStrategy Enum Tests
# =============================================================================


@pytest.mark.unit
class TestRoutingStrategy:
    """RTR-001: Tests for RoutingStrategy enum."""

    def test_direct_only_value(self):
        """RTR-001a: DIRECT_ONLY has correct value."""
        assert RoutingStrategy.DIRECT_ONLY.value == "direct_only"

    def test_ocr_all_value(self):
        """RTR-001b: OCR_ALL has correct value."""
        assert RoutingStrategy.OCR_ALL.value == "ocr_all"

    def test_ocr_selective_value(self):
        """RTR-001c: OCR_SELECTIVE has correct value."""
        assert RoutingStrategy.OCR_SELECTIVE.value == "ocr_selective"

    def test_all_strategies_exist(self):
        """RTR-001d: All expected strategies exist."""
        strategies = [s.value for s in RoutingStrategy]
        assert "direct_only" in strategies
        assert "ocr_all" in strategies
        assert "ocr_selective" in strategies
        assert len(strategies) == 3


# =============================================================================
# CostEstimate Dataclass Tests
# =============================================================================


@pytest.mark.unit
class TestCostEstimate:
    """RTR-002: Tests for CostEstimate dataclass."""

    def test_default_values(self):
        """RTR-002a: Default values are correct."""
        estimate = CostEstimate(ocr_cost_eur=0.05)
        assert estimate.ocr_cost_eur == 0.05
        assert estimate.direct_cost_eur == 0.0
        assert estimate.total_cost_eur == 0.05

    def test_total_cost_calculation(self):
        """RTR-002b: Total cost is calculated correctly."""
        estimate = CostEstimate(
            ocr_cost_eur=0.05,
            direct_cost_eur=0.01,
        )
        assert estimate.total_cost_eur == pytest.approx(0.06)

    def test_time_calculation(self):
        """RTR-002c: Total time is calculated correctly."""
        estimate = CostEstimate(
            ocr_cost_eur=0.05,
            ocr_time_seconds=10.0,
            direct_time_seconds=1.0,
        )
        assert estimate.total_time_seconds == 11.0

    def test_zero_cost(self):
        """RTR-002d: Zero cost produces correct totals."""
        estimate = CostEstimate(ocr_cost_eur=0.0)
        assert estimate.total_cost_eur == 0.0
        assert estimate.total_time_seconds == 0.0

    def test_large_values(self):
        """RTR-002e: Large values are handled correctly."""
        estimate = CostEstimate(
            ocr_cost_eur=1000.0,
            ocr_time_seconds=3600.0,
        )
        assert estimate.total_cost_eur == 1000.0
        assert estimate.total_time_seconds == 3600.0


# =============================================================================
# RoutingDecision Dataclass Tests
# =============================================================================


@pytest.mark.unit
class TestRoutingDecision:
    """RTR-003: Tests for RoutingDecision dataclass."""

    def test_required_fields(self):
        """RTR-003a: Required fields work correctly."""
        decision = RoutingDecision(
            pdf_type=PDFType.PURE_TEXT,
            strategy=RoutingStrategy.DIRECT_ONLY,
            direct_pages=[1, 2, 3],
            ocr_pages=[],
            estimated_cost=0.0,
            estimated_time_seconds=0.3,
        )
        assert decision.pdf_type == PDFType.PURE_TEXT
        assert decision.strategy == RoutingStrategy.DIRECT_ONLY
        assert decision.direct_pages == [1, 2, 3]
        assert decision.ocr_pages == []

    def test_default_quality(self):
        """RTR-003b: Default quality is 'balanced'."""
        decision = RoutingDecision(
            pdf_type=PDFType.PURE_TEXT,
            strategy=RoutingStrategy.DIRECT_ONLY,
            direct_pages=[1],
            ocr_pages=[],
            estimated_cost=0.0,
            estimated_time_seconds=0.1,
        )
        assert decision.quality == "balanced"

    def test_reasoning_field(self):
        """RTR-003c: Reasoning field can be set."""
        decision = RoutingDecision(
            pdf_type=PDFType.HYBRID,
            strategy=RoutingStrategy.OCR_SELECTIVE,
            direct_pages=[1, 3],
            ocr_pages=[2, 4],
            estimated_cost=0.01,
            estimated_time_seconds=6.2,
            reasoning="Test reasoning",
        )
        assert decision.reasoning == "Test reasoning"

    def test_total_pages_field(self):
        """RTR-003d: Total pages field can be set."""
        decision = RoutingDecision(
            pdf_type=PDFType.HYBRID,
            strategy=RoutingStrategy.OCR_SELECTIVE,
            direct_pages=[1, 3],
            ocr_pages=[2, 4],
            estimated_cost=0.01,
            estimated_time_seconds=6.2,
            total_pages=4,
        )
        assert decision.total_pages == 4


# =============================================================================
# ContentRouter Initialization Tests
# =============================================================================


@pytest.mark.unit
class TestContentRouterInit:
    """RTR-004: Tests for ContentRouter initialization."""

    def test_init_no_backends(self):
        """RTR-004a: Init without backends works."""
        router = ContentRouter()
        assert router.primary_backend is None
        assert router.fallback_backend is None

    def test_init_with_primary_backend(self, mock_available_backend):
        """RTR-004b: Init with primary backend works."""
        router = ContentRouter(primary_backend=mock_available_backend)
        assert router.primary_backend == mock_available_backend
        assert router.fallback_backend is None

    def test_init_with_both_backends(self, mock_available_backend):
        """RTR-004c: Init with both backends works."""
        fallback = MockOCRBackend(name="Fallback")
        router = ContentRouter(
            primary_backend=mock_available_backend,
            fallback_backend=fallback,
        )
        assert router.primary_backend == mock_available_backend
        assert router.fallback_backend == fallback

    def test_default_cost_values(self):
        """RTR-004d: Default cost values are correct."""
        router = ContentRouter()
        assert router.cost_per_ocr_page == ContentRouter.DEFAULT_COST_PER_OCR_PAGE
        assert router.time_per_ocr_page == ContentRouter.DEFAULT_TIME_PER_OCR_PAGE
        assert router.time_per_direct_page == ContentRouter.DEFAULT_TIME_PER_DIRECT_PAGE

    def test_custom_cost_values(self):
        """RTR-004e: Custom cost values are respected."""
        router = ContentRouter(
            cost_per_ocr_page=0.01,
            time_per_ocr_page=5.0,
            time_per_direct_page=0.2,
        )
        assert router.cost_per_ocr_page == 0.01
        assert router.time_per_ocr_page == 5.0
        assert router.time_per_direct_page == 0.2


# =============================================================================
# ContentRouter.has_ocr_backend() Tests
# =============================================================================


@pytest.mark.unit
class TestHasOCRBackend:
    """RTR-005: Tests for has_ocr_backend() method."""

    def test_no_backends_returns_false(self):
        """RTR-005a: No backends returns False."""
        router = ContentRouter()
        assert router.has_ocr_backend() is False

    def test_available_primary_returns_true(self, mock_available_backend):
        """RTR-005b: Available primary backend returns True."""
        router = ContentRouter(primary_backend=mock_available_backend)
        assert router.has_ocr_backend() is True

    def test_unavailable_primary_returns_false(self, mock_unavailable_backend):
        """RTR-005c: Unavailable primary backend returns False."""
        router = ContentRouter(primary_backend=mock_unavailable_backend)
        assert router.has_ocr_backend() is False

    def test_unavailable_primary_available_fallback(
        self, mock_unavailable_backend, mock_available_backend
    ):
        """RTR-005d: Unavailable primary + available fallback returns True."""
        router = ContentRouter(
            primary_backend=mock_unavailable_backend,
            fallback_backend=mock_available_backend,
        )
        assert router.has_ocr_backend() is True

    def test_both_unavailable_returns_false(self, mock_unavailable_backend):
        """RTR-005e: Both unavailable returns False."""
        fallback = MockOCRBackend(name="Fallback", available=False)
        router = ContentRouter(
            primary_backend=mock_unavailable_backend,
            fallback_backend=fallback,
        )
        assert router.has_ocr_backend() is False


# =============================================================================
# ContentRouter._determine_strategy() Tests
# =============================================================================


@pytest.mark.unit
class TestDetermineStrategy:
    """RTR-006: Tests for _determine_strategy() method."""

    def test_fast_quality_pure_text_returns_direct(self):
        """RTR-006a: Fast quality with PURE_TEXT returns DIRECT_ONLY."""
        router = ContentRouter()
        strategy = router._determine_strategy(PDFType.PURE_TEXT, "fast")
        assert strategy == RoutingStrategy.DIRECT_ONLY

    def test_fast_quality_pure_image_returns_direct(self):
        """RTR-006b: Fast quality with PURE_IMAGE returns DIRECT_ONLY."""
        router = ContentRouter()
        strategy = router._determine_strategy(PDFType.PURE_IMAGE, "fast")
        assert strategy == RoutingStrategy.DIRECT_ONLY

    def test_fast_quality_hybrid_returns_direct(self):
        """RTR-006c: Fast quality with HYBRID returns DIRECT_ONLY."""
        router = ContentRouter()
        strategy = router._determine_strategy(PDFType.HYBRID, "fast")
        assert strategy == RoutingStrategy.DIRECT_ONLY

    def test_balanced_quality_pure_text_returns_direct(self):
        """RTR-006d: Balanced quality with PURE_TEXT returns DIRECT_ONLY."""
        router = ContentRouter()
        strategy = router._determine_strategy(PDFType.PURE_TEXT, "balanced")
        assert strategy == RoutingStrategy.DIRECT_ONLY

    def test_balanced_quality_pure_image_returns_ocr_all(self):
        """RTR-006e: Balanced quality with PURE_IMAGE returns OCR_ALL."""
        router = ContentRouter()
        strategy = router._determine_strategy(PDFType.PURE_IMAGE, "balanced")
        assert strategy == RoutingStrategy.OCR_ALL

    def test_balanced_quality_hybrid_returns_ocr_selective(self):
        """RTR-006f: Balanced quality with HYBRID returns OCR_SELECTIVE."""
        router = ContentRouter()
        strategy = router._determine_strategy(PDFType.HYBRID, "balanced")
        assert strategy == RoutingStrategy.OCR_SELECTIVE

    def test_accurate_quality_pure_image_returns_ocr_all(self):
        """RTR-006g: Accurate quality with PURE_IMAGE returns OCR_ALL."""
        router = ContentRouter()
        strategy = router._determine_strategy(PDFType.PURE_IMAGE, "accurate")
        assert strategy == RoutingStrategy.OCR_ALL

    def test_accurate_quality_hybrid_returns_ocr_selective(self):
        """RTR-006h: Accurate quality with HYBRID returns OCR_SELECTIVE."""
        router = ContentRouter()
        strategy = router._determine_strategy(PDFType.HYBRID, "accurate")
        assert strategy == RoutingStrategy.OCR_SELECTIVE

    def test_unknown_pdf_type_returns_direct(self):
        """RTR-006i: UNKNOWN PDF type returns DIRECT_ONLY."""
        router = ContentRouter()
        for quality in ("fast", "balanced", "accurate"):
            strategy = router._determine_strategy(PDFType.UNKNOWN, quality)
            assert strategy == RoutingStrategy.DIRECT_ONLY


# =============================================================================
# ContentRouter._select_pages() Tests
# =============================================================================


@pytest.mark.unit
class TestSelectPages:
    """RTR-007: Tests for _select_pages() method."""

    def test_direct_only_all_pages_direct(self, text_classification):
        """RTR-007a: DIRECT_ONLY puts all pages in direct."""
        router = ContentRouter()
        direct, ocr = router._select_pages(
            text_classification, RoutingStrategy.DIRECT_ONLY, "fast"
        )
        assert direct == [1, 2, 3]
        assert ocr == []

    def test_ocr_all_all_pages_ocr(self, image_classification):
        """RTR-007b: OCR_ALL puts all pages in OCR."""
        router = ContentRouter()
        direct, ocr = router._select_pages(
            image_classification, RoutingStrategy.OCR_ALL, "balanced"
        )
        assert direct == []
        assert ocr == [1, 2]

    def test_ocr_selective_balanced_hybrid_direct(self, hybrid_classification):
        """RTR-007c: OCR_SELECTIVE balanced puts hybrid pages in direct."""
        router = ContentRouter()
        direct, ocr = router._select_pages(
            hybrid_classification, RoutingStrategy.OCR_SELECTIVE, "balanced"
        )
        # Balanced: text + hybrid pages direct, image pages OCR
        assert 1 in direct and 3 in direct  # text pages
        assert 4 in direct  # hybrid page (balanced)
        assert 2 in ocr  # image page

    def test_ocr_selective_accurate_hybrid_ocr(self, hybrid_classification):
        """RTR-007d: OCR_SELECTIVE accurate puts hybrid pages in OCR."""
        router = ContentRouter()
        direct, ocr = router._select_pages(
            hybrid_classification, RoutingStrategy.OCR_SELECTIVE, "accurate"
        )
        # Accurate: text pages direct, image + hybrid pages OCR
        assert 1 in direct and 3 in direct  # text pages
        assert 2 in ocr  # image page
        assert 4 in ocr  # hybrid page (accurate)

    def test_pages_are_sorted(self, hybrid_classification):
        """RTR-007e: Returned page lists are sorted."""
        router = ContentRouter()
        direct, ocr = router._select_pages(
            hybrid_classification, RoutingStrategy.OCR_SELECTIVE, "balanced"
        )
        assert direct == sorted(direct)
        assert ocr == sorted(ocr)

    def test_empty_classification(self):
        """RTR-007f: Empty classification is handled."""
        classification = PDFClassificationResult(
            pdf_type=PDFType.UNKNOWN,
            total_pages=0,
            text_pages=[],
            image_pages=[],
            hybrid_pages=[],
        )
        router = ContentRouter()
        direct, ocr = router._select_pages(
            classification, RoutingStrategy.DIRECT_ONLY, "fast"
        )
        assert direct == []
        assert ocr == []


# =============================================================================
# ContentRouter.estimate_cost() Tests
# =============================================================================


@pytest.mark.unit
class TestEstimateCost:
    """RTR-008: Tests for estimate_cost() method."""

    def test_zero_pages(self):
        """RTR-008a: Zero pages returns zero cost."""
        router = ContentRouter()
        estimate = router.estimate_cost(ocr_page_count=0, direct_page_count=0)
        assert estimate.total_cost_eur == 0.0
        assert estimate.total_time_seconds == 0.0

    def test_ocr_only(self):
        """RTR-008b: OCR only calculates correctly."""
        router = ContentRouter(cost_per_ocr_page=0.01, time_per_ocr_page=2.0)
        estimate = router.estimate_cost(ocr_page_count=5, direct_page_count=0)
        assert estimate.ocr_cost_eur == 0.05
        assert estimate.ocr_time_seconds == 10.0
        assert estimate.total_cost_eur == 0.05

    def test_direct_only(self):
        """RTR-008c: Direct only has zero cost."""
        router = ContentRouter(time_per_direct_page=0.1)
        estimate = router.estimate_cost(ocr_page_count=0, direct_page_count=10)
        assert estimate.direct_cost_eur == 0.0
        assert estimate.direct_time_seconds == 1.0
        assert estimate.total_cost_eur == 0.0

    def test_mixed_pages(self):
        """RTR-008d: Mixed pages calculate correctly."""
        router = ContentRouter(
            cost_per_ocr_page=0.01,
            time_per_ocr_page=2.0,
            time_per_direct_page=0.1,
        )
        estimate = router.estimate_cost(ocr_page_count=3, direct_page_count=5)
        assert estimate.ocr_cost_eur == 0.03
        assert estimate.ocr_time_seconds == 6.0
        assert estimate.direct_time_seconds == 0.5
        assert estimate.total_time_seconds == pytest.approx(6.5)

    def test_large_page_count(self):
        """RTR-008e: Large page counts work correctly."""
        router = ContentRouter(cost_per_ocr_page=0.005)
        estimate = router.estimate_cost(ocr_page_count=1000, direct_page_count=0)
        assert estimate.ocr_cost_eur == 5.0


# =============================================================================
# ContentRouter.route() Tests - PURE_TEXT
# =============================================================================


@pytest.mark.unit
class TestRoutePureText:
    """RTR-009: Tests for route() with PURE_TEXT PDFs."""

    def test_fast_quality(self, mock_available_backend, text_classification):
        """RTR-009a: Fast quality with PURE_TEXT uses direct."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(text_classification, quality="fast")

        assert decision.pdf_type == PDFType.PURE_TEXT
        assert decision.strategy == RoutingStrategy.DIRECT_ONLY
        assert decision.direct_pages == [1, 2, 3]
        assert decision.ocr_pages == []
        assert decision.estimated_cost == 0.0

    def test_balanced_quality(self, mock_available_backend, text_classification):
        """RTR-009b: Balanced quality with PURE_TEXT uses direct."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(text_classification, quality="balanced")

        assert decision.strategy == RoutingStrategy.DIRECT_ONLY
        assert decision.ocr_pages == []

    def test_accurate_quality(self, mock_available_backend, text_classification):
        """RTR-009c: Accurate quality with PURE_TEXT uses direct."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(text_classification, quality="accurate")

        assert decision.strategy == RoutingStrategy.DIRECT_ONLY
        assert decision.ocr_pages == []


# =============================================================================
# ContentRouter.route() Tests - PURE_IMAGE
# =============================================================================


@pytest.mark.unit
class TestRoutePureImage:
    """RTR-010: Tests for route() with PURE_IMAGE PDFs."""

    def test_fast_quality(self, mock_available_backend, image_classification):
        """RTR-010a: Fast quality with PURE_IMAGE uses direct."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(image_classification, quality="fast")

        assert decision.strategy == RoutingStrategy.DIRECT_ONLY
        assert decision.direct_pages == [1, 2]
        assert decision.ocr_pages == []

    def test_balanced_quality(self, mock_available_backend, image_classification):
        """RTR-010b: Balanced quality with PURE_IMAGE uses OCR."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(image_classification, quality="balanced")

        assert decision.strategy == RoutingStrategy.OCR_ALL
        assert decision.direct_pages == []
        assert decision.ocr_pages == [1, 2]

    def test_accurate_quality(self, mock_available_backend, image_classification):
        """RTR-010c: Accurate quality with PURE_IMAGE uses OCR."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(image_classification, quality="accurate")

        assert decision.strategy == RoutingStrategy.OCR_ALL
        assert decision.ocr_pages == [1, 2]


# =============================================================================
# ContentRouter.route() Tests - HYBRID
# =============================================================================


@pytest.mark.unit
class TestRouteHybrid:
    """RTR-011: Tests for route() with HYBRID PDFs."""

    def test_fast_quality(self, mock_available_backend, hybrid_classification):
        """RTR-011a: Fast quality with HYBRID uses direct."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(hybrid_classification, quality="fast")

        assert decision.strategy == RoutingStrategy.DIRECT_ONLY
        assert len(decision.direct_pages) == 4
        assert decision.ocr_pages == []

    def test_balanced_quality(self, mock_available_backend, hybrid_classification):
        """RTR-011b: Balanced quality with HYBRID uses selective OCR."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(hybrid_classification, quality="balanced")

        assert decision.strategy == RoutingStrategy.OCR_SELECTIVE
        # Image page (2) gets OCR
        assert 2 in decision.ocr_pages
        # Text pages (1, 3) and hybrid page (4) get direct
        assert 1 in decision.direct_pages
        assert 3 in decision.direct_pages
        assert 4 in decision.direct_pages

    def test_accurate_quality(self, mock_available_backend, hybrid_classification):
        """RTR-011c: Accurate quality with HYBRID uses selective OCR for more pages."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(hybrid_classification, quality="accurate")

        assert decision.strategy == RoutingStrategy.OCR_SELECTIVE
        # Image page (2) and hybrid page (4) get OCR
        assert 2 in decision.ocr_pages
        assert 4 in decision.ocr_pages
        # Text pages (1, 3) get direct
        assert 1 in decision.direct_pages
        assert 3 in decision.direct_pages


# =============================================================================
# ContentRouter.route() Edge Cases
# =============================================================================


@pytest.mark.unit
class TestRouteEdgeCases:
    """RTR-012: Edge case tests for route() method."""

    def test_no_ocr_backend_forces_direct(self, image_classification):
        """RTR-012a: No OCR backend forces DIRECT_ONLY."""
        router = ContentRouter()  # No backend
        decision = router.route(image_classification, quality="balanced")

        # Should be forced to DIRECT_ONLY
        assert decision.strategy == RoutingStrategy.DIRECT_ONLY
        assert decision.ocr_pages == []

    def test_unavailable_backend_forces_direct(
        self, mock_unavailable_backend, image_classification
    ):
        """RTR-012b: Unavailable backend forces DIRECT_ONLY."""
        router = ContentRouter(primary_backend=mock_unavailable_backend)
        decision = router.route(image_classification, quality="balanced")

        assert decision.strategy == RoutingStrategy.DIRECT_ONLY

    def test_invalid_quality_defaults_to_balanced(
        self, mock_available_backend, image_classification
    ):
        """RTR-012c: Invalid quality defaults to balanced."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(image_classification, quality="invalid")

        assert decision.quality == "balanced"
        assert decision.strategy == RoutingStrategy.OCR_ALL

    def test_unknown_pdf_type(self, mock_available_backend, unknown_classification):
        """RTR-012d: UNKNOWN PDF type uses DIRECT_ONLY."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(unknown_classification, quality="balanced")

        assert decision.strategy == RoutingStrategy.DIRECT_ONLY

    def test_reasoning_populated(self, mock_available_backend, hybrid_classification):
        """RTR-012e: Reasoning field is populated."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(hybrid_classification, quality="balanced")

        assert decision.reasoning != ""
        assert "hybrid" in decision.reasoning.lower()

    def test_total_pages_populated(self, mock_available_backend, hybrid_classification):
        """RTR-012f: Total pages field is populated."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(hybrid_classification, quality="balanced")

        assert decision.total_pages == 4

    def test_empty_string_quality(self, mock_available_backend, image_classification):
        """RTR-012g: Empty string quality defaults to balanced."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(image_classification, quality="")

        assert decision.quality == "balanced"


# =============================================================================
# ContentRouter Cost Estimation in route() Tests
# =============================================================================


@pytest.mark.unit
class TestRouteCostEstimation:
    """RTR-013: Tests for cost estimation within route()."""

    def test_zero_cost_for_direct_only(self, mock_available_backend, text_classification):
        """RTR-013a: Direct only has zero cost."""
        router = ContentRouter(primary_backend=mock_available_backend)
        decision = router.route(text_classification, quality="fast")

        assert decision.estimated_cost == 0.0

    def test_cost_calculated_for_ocr(self, mock_available_backend, image_classification):
        """RTR-013b: OCR cost is calculated."""
        router = ContentRouter(
            primary_backend=mock_available_backend,
            cost_per_ocr_page=0.01,
        )
        decision = router.route(image_classification, quality="balanced")

        # 2 pages * 0.01 EUR = 0.02 EUR
        assert decision.estimated_cost == 0.02

    def test_time_calculated(self, mock_available_backend, hybrid_classification):
        """RTR-013c: Time is calculated."""
        router = ContentRouter(
            primary_backend=mock_available_backend,
            time_per_ocr_page=2.0,
            time_per_direct_page=0.1,
        )
        decision = router.route(hybrid_classification, quality="balanced")

        # 1 OCR page (2) * 2.0s + 3 direct pages * 0.1s = 2.3s
        assert decision.estimated_time_seconds == pytest.approx(2.3, rel=0.1)

    def test_accurate_quality_cost_higher(self, mock_available_backend, hybrid_classification):
        """RTR-013d: Accurate quality has higher cost for hybrid."""
        router = ContentRouter(
            primary_backend=mock_available_backend,
            cost_per_ocr_page=0.01,
        )

        balanced_decision = router.route(hybrid_classification, quality="balanced")
        accurate_decision = router.route(hybrid_classification, quality="accurate")

        # Accurate OCRs more pages (image + hybrid vs just image)
        assert accurate_decision.estimated_cost > balanced_decision.estimated_cost


# =============================================================================
# ContentRouter._generate_reasoning() Tests
# =============================================================================


@pytest.mark.unit
class TestGenerateReasoning:
    """RTR-014: Tests for _generate_reasoning() method."""

    def test_reasoning_contains_pdf_type(self, mock_available_backend):
        """RTR-014a: Reasoning contains PDF type."""
        router = ContentRouter(primary_backend=mock_available_backend)
        reasoning = router._generate_reasoning(
            PDFType.PURE_TEXT, "balanced", RoutingStrategy.DIRECT_ONLY, [1, 2], []
        )
        assert "pure_text" in reasoning.lower()

    def test_reasoning_contains_quality(self, mock_available_backend):
        """RTR-014b: Reasoning contains quality."""
        router = ContentRouter(primary_backend=mock_available_backend)
        reasoning = router._generate_reasoning(
            PDFType.HYBRID, "accurate", RoutingStrategy.OCR_SELECTIVE, [1], [2]
        )
        assert "accurate" in reasoning.lower()

    def test_reasoning_contains_strategy(self, mock_available_backend):
        """RTR-014c: Reasoning contains strategy."""
        router = ContentRouter(primary_backend=mock_available_backend)
        reasoning = router._generate_reasoning(
            PDFType.PURE_IMAGE, "balanced", RoutingStrategy.OCR_ALL, [], [1, 2]
        )
        assert "ocr_all" in reasoning.lower()

    def test_reasoning_for_many_pages_shows_count(self):
        """RTR-014d: Many pages shows count instead of list."""
        router = ContentRouter()
        reasoning = router._generate_reasoning(
            PDFType.PURE_TEXT,
            "fast",
            RoutingStrategy.DIRECT_ONLY,
            list(range(1, 101)),  # 100 pages
            [],
        )
        assert "100 pages" in reasoning

    def test_reasoning_no_ocr_required(self):
        """RTR-014e: No OCR shows appropriate message."""
        router = ContentRouter()
        reasoning = router._generate_reasoning(
            PDFType.PURE_TEXT, "fast", RoutingStrategy.DIRECT_ONLY, [1, 2], []
        )
        assert "No OCR required" in reasoning
