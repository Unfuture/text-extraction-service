"""
Unit Tests for TwoPassProcessor
================================

Tests for the TwoPassProcessor class that handles PDF text extraction
with intelligent OCR routing.
"""

from pathlib import Path

import pytest

from text_extraction import (
    ExtractionResult,
    ProcessorConfig,
    Quality,
    TwoPassProcessor,
)
from text_extraction.backends.base import (
    BaseOCRBackend,
    ExtractionMethod,
    OCRResult,
)

# =============================================================================
# Mock Backend Fixtures
# =============================================================================


class MockOCRBackend(BaseOCRBackend):
    """Mock OCR backend for testing."""

    def __init__(
        self,
        name: str = "MockOCR",
        available: bool = True,
        return_text: str = "Mock OCR Text",
        should_fail: bool = False,
    ):
        super().__init__(name)
        self._available = available
        self._return_text = return_text
        self._should_fail = should_fail
        self.extract_calls = []  # Track calls for verification

    def is_available(self) -> bool:
        return self._available

    def extract_text(
        self,
        file_path: Path,
        page_number: int | None = None,
        **kwargs,
    ) -> OCRResult:
        self.extract_calls.append((file_path, page_number))

        if self._should_fail:
            raise RuntimeError("Mock OCR failure")

        return OCRResult(
            text=self._return_text,
            confidence=0.95,
            method=ExtractionMethod.LLM_OCR,
            page_number=page_number,
        )


@pytest.fixture
def mock_primary_backend():
    """Create a mock primary OCR backend."""
    return MockOCRBackend(
        name="MockPrimary",
        available=True,
        return_text="Primary OCR extracted text",
    )


@pytest.fixture
def mock_fallback_backend():
    """Create a mock fallback OCR backend."""
    return MockOCRBackend(
        name="MockFallback",
        available=True,
        return_text="Fallback OCR extracted text",
    )


@pytest.fixture
def mock_failing_backend():
    """Create a mock backend that always fails."""
    return MockOCRBackend(
        name="MockFailing",
        available=True,
        should_fail=True,
    )


@pytest.fixture
def mock_unavailable_backend():
    """Create a mock backend that is unavailable."""
    return MockOCRBackend(
        name="MockUnavailable",
        available=False,
    )


# =============================================================================
# ProcessorConfig Tests
# =============================================================================


@pytest.mark.unit
class TestProcessorConfig:
    """Tests for ProcessorConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ProcessorConfig()

        assert config.text_threshold == 10
        assert config.enable_two_pass is True
        assert config.confidence_threshold == 0.8
        assert config.fallback_on_error is True
        assert config.include_page_markers is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ProcessorConfig(
            text_threshold=20,
            enable_two_pass=False,
            confidence_threshold=0.9,
            fallback_on_error=False,
            include_page_markers=False,
        )

        assert config.text_threshold == 20
        assert config.enable_two_pass is False
        assert config.confidence_threshold == 0.9
        assert config.fallback_on_error is False
        assert config.include_page_markers is False


# =============================================================================
# TwoPassProcessor Initialization Tests
# =============================================================================


@pytest.mark.unit
class TestTwoPassProcessorInit:
    """Tests for TwoPassProcessor initialization."""

    def test_init_with_no_backends(self):
        """Test initialization without any backends."""
        processor = TwoPassProcessor()

        assert processor.primary_backend is None
        assert processor.fallback_backend is None
        assert processor.config is not None

    def test_init_with_primary_backend(self, mock_primary_backend):
        """Test initialization with primary backend only."""
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        assert processor.primary_backend == mock_primary_backend
        assert processor.fallback_backend is None

    def test_init_with_both_backends(
        self, mock_primary_backend, mock_fallback_backend
    ):
        """Test initialization with both backends."""
        processor = TwoPassProcessor(
            primary_backend=mock_primary_backend,
            fallback_backend=mock_fallback_backend,
        )

        assert processor.primary_backend == mock_primary_backend
        assert processor.fallback_backend == mock_fallback_backend

    def test_init_with_custom_config(self, mock_primary_backend):
        """Test initialization with custom config."""
        config = ProcessorConfig(fallback_on_error=False)
        processor = TwoPassProcessor(
            primary_backend=mock_primary_backend,
            config=config,
        )

        assert processor.config.fallback_on_error is False


# =============================================================================
# TwoPassProcessor Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestTwoPassProcessorExtract:
    """Tests for TwoPassProcessor.extract() method."""

    def test_extract_nonexistent_file(self, mock_primary_backend):
        """Test extraction with nonexistent file."""
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)
        result = processor.extract(Path("/nonexistent/file.pdf"))

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_extract_text_pdf_fast_quality(
        self, mock_primary_backend, create_text_pdf
    ):
        """Test extraction of text PDF with fast quality (no OCR)."""
        pdf_path = create_text_pdf("text.pdf", "Hello World")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        result = processor.extract(pdf_path, quality="fast")

        assert result.success is True
        assert result.pdf_type == "pure_text"
        assert result.extraction_method == "direct"
        # No OCR calls should be made with fast quality
        assert len(mock_primary_backend.extract_calls) == 0

    def test_extract_image_pdf_balanced_quality(
        self, mock_primary_backend, create_image_pdf
    ):
        """Test extraction of image PDF with balanced quality (OCR for images)."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        # OCR should be called for image pages
        assert len(mock_primary_backend.extract_calls) > 0

    def test_extract_hybrid_pdf_accurate_quality(
        self, mock_primary_backend, create_hybrid_pdf
    ):
        """Test extraction of hybrid PDF with accurate quality."""
        pdf_path = create_hybrid_pdf("hybrid.pdf")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        result = processor.extract(pdf_path, quality="accurate")

        assert result.success is True
        assert result.pdf_type == "hybrid"

    def test_extract_multipage_pdf(
        self, mock_primary_backend, create_multipage_text_pdf
    ):
        """Test extraction of multi-page PDF."""
        pdf_path = create_multipage_text_pdf("multipage.pdf", pages=3)
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        result = processor.extract(pdf_path, quality="fast")

        assert result.success is True
        assert result.total_pages == 3
        assert len(result.pages) == 3


# =============================================================================
# TwoPassProcessor OCR Fallback Tests
# =============================================================================


@pytest.mark.unit
class TestTwoPassProcessorFallback:
    """Tests for OCR fallback behavior."""

    def test_fallback_on_primary_failure(
        self, mock_failing_backend, mock_fallback_backend, create_image_pdf
    ):
        """Test that fallback backend is used when primary fails."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(
            primary_backend=mock_failing_backend,
            fallback_backend=mock_fallback_backend,
            config=ProcessorConfig(fallback_on_error=True),
        )

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        # Fallback should have been called
        assert len(mock_fallback_backend.extract_calls) > 0

    def test_no_fallback_when_disabled(
        self, mock_failing_backend, mock_fallback_backend, create_image_pdf
    ):
        """Test that fallback is not used when disabled."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(
            primary_backend=mock_failing_backend,
            fallback_backend=mock_fallback_backend,
            config=ProcessorConfig(fallback_on_error=False),
        )

        processor.extract(pdf_path, quality="balanced")

        # Fallback should NOT have been called
        assert len(mock_fallback_backend.extract_calls) == 0

    def test_no_backend_available(
        self, mock_unavailable_backend, create_image_pdf
    ):
        """Test extraction when no backend is available."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(
            primary_backend=mock_unavailable_backend,
        )

        result = processor.extract(pdf_path, quality="balanced")

        # Should still succeed with direct extraction
        assert result.success is True
        assert "direct" in result.extraction_method
        # Backend status should reflect unavailability
        assert result.backend_status is not None
        assert result.backend_status.primary_available is False
        # Page errors should be populated for image pages that needed OCR
        assert len(result.page_errors) > 0
        assert result.page_errors[0].error == "backend unavailable"


# =============================================================================
# TwoPassProcessor Page OCR Decision Tests
# =============================================================================


@pytest.mark.unit
class TestPageNeedsOCR:
    """Tests for _page_needs_ocr() method."""

    def test_fast_quality_never_needs_ocr(
        self, mock_primary_backend, create_image_pdf
    ):
        """Test that fast quality never triggers OCR."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        processor.extract(pdf_path, quality="fast")

        # No OCR calls with fast quality
        assert len(mock_primary_backend.extract_calls) == 0

    def test_balanced_quality_ocr_for_image_pages(
        self, mock_primary_backend, create_hybrid_pdf
    ):
        """Test that balanced quality uses OCR only for image pages."""
        pdf_path = create_hybrid_pdf("hybrid.pdf")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        # Reset call tracking
        mock_primary_backend.extract_calls = []

        processor.extract(pdf_path, quality="balanced")

        # OCR should only be called for image pages (page 2)
        ocr_pages = [call[1] for call in mock_primary_backend.extract_calls]
        assert 2 in ocr_pages  # Page 2 is image
        assert 1 not in ocr_pages  # Page 1 is text


# =============================================================================
# TwoPassProcessor Text Building Tests
# =============================================================================


@pytest.mark.unit
class TestTextBuilding:
    """Tests for text building and formatting."""

    def test_page_markers_included(
        self, mock_primary_backend, create_text_pdf
    ):
        """Test that page markers are included by default."""
        pdf_path = create_text_pdf("text.pdf", "Test content")
        processor = TwoPassProcessor(
            primary_backend=mock_primary_backend,
            config=ProcessorConfig(include_page_markers=True),
        )

        result = processor.extract(pdf_path, quality="fast")

        assert "--- Page 1 ---" in result.text

    def test_page_markers_excluded(
        self, mock_primary_backend, create_text_pdf
    ):
        """Test that page markers can be excluded."""
        pdf_path = create_text_pdf("text.pdf", "Test content")
        processor = TwoPassProcessor(
            primary_backend=mock_primary_backend,
            config=ProcessorConfig(include_page_markers=False),
        )

        result = processor.extract(pdf_path, quality="fast")

        assert "--- Page" not in result.text


# =============================================================================
# TwoPassProcessor Metadata Tests
# =============================================================================


@pytest.mark.unit
class TestExtractionMetadata:
    """Tests for extraction result metadata."""

    def test_result_contains_quality(
        self, mock_primary_backend, create_text_pdf
    ):
        """Test that result metadata contains quality setting."""
        pdf_path = create_text_pdf("text.pdf", "Test")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        result = processor.extract(pdf_path, quality="balanced")

        assert result.metadata["quality"] == "balanced"

    def test_result_contains_page_lists(
        self, mock_primary_backend, create_hybrid_pdf
    ):
        """Test that result metadata contains page classification lists."""
        pdf_path = create_hybrid_pdf("hybrid.pdf")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        result = processor.extract(pdf_path, quality="balanced")

        assert "text_pages" in result.metadata
        assert "image_pages" in result.metadata
        assert "hybrid_pages" in result.metadata

    def test_word_count_accurate(
        self, mock_primary_backend, create_text_pdf
    ):
        """Test that word count is calculated correctly."""
        pdf_path = create_text_pdf("text.pdf", "One two three four five")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        result = processor.extract(pdf_path, quality="fast")

        assert result.word_count > 0
        assert result.word_count == len(result.text.split())


# =============================================================================
# Quality Enum Tests
# =============================================================================


@pytest.mark.unit
class TestQualityEnum:
    """Tests for Quality enum."""

    def test_quality_values(self):
        """Test Quality enum values."""
        assert Quality.FAST.value == "fast"
        assert Quality.BALANCED.value == "balanced"
        assert Quality.ACCURATE.value == "accurate"


# =============================================================================
# ExtractionResult Tests
# =============================================================================


@pytest.mark.unit
class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_full_text_property(self):
        """Test that full_text property returns text field."""
        result = ExtractionResult(
            success=True,
            file_name="test.pdf",
            pdf_type="pure_text",
            total_pages=1,
            text="Test content",
            word_count=2,
            confidence=1.0,
            processing_time_ms=100.0,
            extraction_method="direct",
        )

        assert result.full_text == "Test content"

    def test_error_result(self):
        """Test error result creation."""
        result = ExtractionResult(
            success=False,
            file_name="test.pdf",
            pdf_type="unknown",
            total_pages=0,
            text="",
            word_count=0,
            confidence=0.0,
            processing_time_ms=0.0,
            extraction_method="none",
            error="Test error",
        )

        assert result.success is False
        assert result.error == "Test error"

    def test_backend_status_defaults(self):
        """Test ExtractionResult with backend_status and page_errors defaults."""
        result = ExtractionResult(
            success=True,
            file_name="test.pdf",
            pdf_type="pure_text",
            total_pages=1,
            text="Test",
            word_count=1,
            confidence=1.0,
            processing_time_ms=10.0,
            extraction_method="direct",
        )

        assert result.backend_status is None
        assert result.page_errors == []


# =============================================================================
# OCR Failure Cascade Tests
# =============================================================================


@pytest.mark.unit
class TestOCRFailureCascade:
    """Tests for OCR failure tracking via backend_status and page_errors."""

    def test_image_pdf_no_backend_has_page_errors(
        self, create_image_pdf
    ):
        """Pure image PDF with no backend → page_errors populated."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(primary_backend=None)

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        # No primary backend means no OCR attempt, but _extract_page_text
        # skips OCR when primary_backend is None → no page_errors
        # (errors only tracked when OCR was attempted)
        assert result.backend_status is not None
        assert result.backend_status.primary_backend == "none"
        assert result.backend_status.primary_available is False

    def test_image_pdf_unavailable_backend_has_page_errors(
        self, mock_unavailable_backend, create_image_pdf
    ):
        """Pure image PDF with unavailable backend → page_errors populated."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(primary_backend=mock_unavailable_backend)

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        assert result.backend_status is not None
        assert result.backend_status.primary_available is False
        assert result.backend_status.failed_pages > 0
        assert len(result.page_errors) > 0
        for pe in result.page_errors:
            assert pe.error == "backend unavailable"

    def test_image_pdf_failing_backend_has_page_errors(
        self, mock_failing_backend, create_image_pdf
    ):
        """Backend throws exception → errors captured in page_errors."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(
            primary_backend=mock_failing_backend,
            config=ProcessorConfig(fallback_on_error=False),
        )

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        assert len(result.page_errors) > 0
        assert "Mock OCR failure" in result.page_errors[0].error
        assert result.backend_status is not None
        assert result.backend_status.failed_pages == len(result.page_errors)

    def test_text_pdf_no_backend_no_errors(
        self, create_text_pdf
    ):
        """Text PDF without OCR backend → no errors (OCR not needed)."""
        pdf_path = create_text_pdf("text.pdf", "Hello World")
        processor = TwoPassProcessor(primary_backend=None)

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        assert len(result.page_errors) == 0
        assert result.backend_status is not None
        assert result.backend_status.attempted_pages == 0

    def test_hybrid_pdf_partial_errors(
        self, mock_failing_backend, create_hybrid_pdf
    ):
        """Hybrid PDF with failing backend → errors only for image pages."""
        pdf_path = create_hybrid_pdf("hybrid.pdf")
        processor = TwoPassProcessor(
            primary_backend=mock_failing_backend,
            config=ProcessorConfig(fallback_on_error=False),
        )

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        # Only image pages should have errors
        error_pages = {pe.page_number for pe in result.page_errors}
        # Page 1 is text, page 2 is image in hybrid PDFs
        assert 1 not in error_pages
        assert 2 in error_pages

    def test_fast_quality_image_pdf_no_errors(
        self, mock_failing_backend, create_image_pdf
    ):
        """Fast quality skips OCR → no errors even with failing backend."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(primary_backend=mock_failing_backend)

        result = processor.extract(pdf_path, quality="fast")

        assert result.success is True
        assert len(result.page_errors) == 0
        assert result.backend_status is not None
        assert result.backend_status.attempted_pages == 0

    def test_successful_ocr_no_errors(
        self, mock_primary_backend, create_image_pdf
    ):
        """Successful OCR → no page_errors, backend_status shows success."""
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(primary_backend=mock_primary_backend)

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        assert len(result.page_errors) == 0
        assert result.backend_status is not None
        assert result.backend_status.primary_available is True
        assert result.backend_status.successful_pages > 0
        assert result.backend_status.failed_pages == 0

    def test_empty_ocr_response_has_page_errors(
        self, create_image_pdf
    ):
        """Backend returns empty text (no exception) → page_errors populated."""
        empty_backend = MockOCRBackend(
            name="MockEmpty",
            available=True,
            return_text="",  # Returns empty string
        )
        pdf_path = create_image_pdf("image.pdf")
        processor = TwoPassProcessor(
            primary_backend=empty_backend,
            config=ProcessorConfig(fallback_on_error=False),
        )

        result = processor.extract(pdf_path, quality="balanced")

        assert result.success is True
        assert len(result.page_errors) > 0
        assert "empty response" in result.page_errors[0].error
