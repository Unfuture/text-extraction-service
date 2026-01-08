"""
Unit Tests for BaseOCRBackend and Related Classes

Test Coverage:
- OCRResult dataclass
- PageOCRResult dataclass
- DocumentOCRResult dataclass
- BaseOCRBackend abstract class
- Default implementations
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from text_extraction.backends.base import (
    BaseOCRBackend,
    OCRResult,
    PageOCRResult,
    DocumentOCRResult,
    ExtractionMethod,
)


# =============================================================================
# Test: ExtractionMethod Enum
# =============================================================================

class TestExtractionMethodEnum:
    """Tests for ExtractionMethod enum."""

    @pytest.mark.unit
    def test_extraction_method_values(self):
        """ExtractionMethod enum should have expected values."""
        assert ExtractionMethod.DIRECT.value == "direct"
        assert ExtractionMethod.LLM_OCR.value == "llm_ocr"
        assert ExtractionMethod.TESSERACT.value == "tesseract"
        assert ExtractionMethod.CLOUD_VISION.value == "cloud_vision"


# =============================================================================
# Test: OCRResult Dataclass
# =============================================================================

class TestOCRResult:
    """Tests for OCRResult dataclass."""

    @pytest.mark.unit
    def test_ocr_result_creation_minimal(self):
        """OCRResult should be creatable with minimal args."""
        result = OCRResult(text="Hello World")

        assert result.text == "Hello World"
        assert result.confidence == 1.0
        assert result.method == ExtractionMethod.DIRECT
        assert result.page_number is None

    @pytest.mark.unit
    def test_ocr_result_word_count_auto_calculated(self):
        """BKD-001: OCRResult should calculate word count automatically."""
        result = OCRResult(text="One two three four five")

        assert result.word_count == 5

    @pytest.mark.unit
    def test_ocr_result_word_count_empty_text(self):
        """Empty text should have zero word count."""
        result = OCRResult(text="")

        assert result.word_count == 0

    @pytest.mark.unit
    def test_ocr_result_word_count_preserves_explicit(self):
        """Explicit word count should be preserved if > 0."""
        result = OCRResult(text="One two", word_count=10)

        assert result.word_count == 10  # Explicit value kept

    @pytest.mark.unit
    def test_ocr_result_full_creation(self):
        """OCRResult should be creatable with all args."""
        result = OCRResult(
            text="Test content",
            confidence=0.95,
            method=ExtractionMethod.LLM_OCR,
            page_number=3,
            word_count=2,
            metadata={"model": "claude-sonnet"}
        )

        assert result.text == "Test content"
        assert result.confidence == 0.95
        assert result.method == ExtractionMethod.LLM_OCR
        assert result.page_number == 3
        assert result.word_count == 2
        assert result.metadata["model"] == "claude-sonnet"


# =============================================================================
# Test: PageOCRResult Dataclass
# =============================================================================

class TestPageOCRResult:
    """Tests for PageOCRResult dataclass."""

    @pytest.mark.unit
    def test_page_ocr_result_creation(self):
        """PageOCRResult should be creatable with required args."""
        result = PageOCRResult(
            page_number=1,
            text="Page content",
            confidence=0.9,
            method=ExtractionMethod.TESSERACT
        )

        assert result.page_number == 1
        assert result.text == "Page content"
        assert result.confidence == 0.9
        assert result.method == ExtractionMethod.TESSERACT
        assert result.word_count == 0  # Default
        assert result.processing_time_ms == 0.0  # Default

    @pytest.mark.unit
    def test_page_ocr_result_with_timing(self):
        """PageOCRResult should store processing time."""
        result = PageOCRResult(
            page_number=2,
            text="Content",
            confidence=0.85,
            method=ExtractionMethod.LLM_OCR,
            word_count=1,
            processing_time_ms=1234.5
        )

        assert result.processing_time_ms == 1234.5


# =============================================================================
# Test: DocumentOCRResult Dataclass
# =============================================================================

class TestDocumentOCRResult:
    """Tests for DocumentOCRResult dataclass."""

    @pytest.mark.unit
    def test_document_ocr_result_creation(self):
        """DocumentOCRResult should be creatable with required args."""
        pages = [
            PageOCRResult(1, "Page 1", 0.9, ExtractionMethod.DIRECT),
            PageOCRResult(2, "Page 2", 0.85, ExtractionMethod.DIRECT),
        ]

        result = DocumentOCRResult(
            success=True,
            file_name="test.pdf",
            pages=pages,
            total_pages=2
        )

        assert result.success is True
        assert result.file_name == "test.pdf"
        assert len(result.pages) == 2
        assert result.total_pages == 2
        assert result.error is None

    @pytest.mark.unit
    def test_document_ocr_result_full_text_property(self):
        """BKD-002: full_text property should concatenate all page texts."""
        pages = [
            PageOCRResult(1, "First page", 0.9, ExtractionMethod.DIRECT),
            PageOCRResult(2, "Second page", 0.85, ExtractionMethod.DIRECT),
            PageOCRResult(3, "Third page", 0.8, ExtractionMethod.DIRECT),
        ]

        result = DocumentOCRResult(
            success=True,
            file_name="test.pdf",
            pages=pages,
            total_pages=3
        )

        full_text = result.full_text
        assert "First page" in full_text
        assert "Second page" in full_text
        assert "Third page" in full_text
        assert full_text == "First page\n\nSecond page\n\nThird page"

    @pytest.mark.unit
    def test_document_ocr_result_full_text_handles_empty_pages(self):
        """full_text should skip empty pages."""
        pages = [
            PageOCRResult(1, "Content", 0.9, ExtractionMethod.DIRECT),
            PageOCRResult(2, "", 0.0, ExtractionMethod.DIRECT),  # Empty
            PageOCRResult(3, "More content", 0.85, ExtractionMethod.DIRECT),
        ]

        result = DocumentOCRResult(
            success=True,
            file_name="test.pdf",
            pages=pages,
            total_pages=3
        )

        full_text = result.full_text
        assert full_text == "Content\n\nMore content"  # Empty page skipped

    @pytest.mark.unit
    def test_document_ocr_result_failure(self):
        """Failed result should have error message."""
        result = DocumentOCRResult(
            success=False,
            file_name="failed.pdf",
            pages=[],
            total_pages=0,
            error="File corrupted"
        )

        assert result.success is False
        assert result.error == "File corrupted"
        assert result.full_text == ""


# =============================================================================
# Test: BaseOCRBackend Abstract Class
# =============================================================================

class ConcreteOCRBackend(BaseOCRBackend):
    """Concrete implementation for testing BaseOCRBackend."""

    def __init__(self, available: bool = True):
        super().__init__(name="TestBackend")
        self._available = available
        self._extract_result = OCRResult(text="Extracted text")

    def extract_text(self, file_path: Path, page_number=None, **kwargs) -> OCRResult:
        return self._extract_result

    def is_available(self) -> bool:
        return self._available


class TestBaseOCRBackend:
    """Tests for BaseOCRBackend abstract class."""

    @pytest.mark.unit
    def test_backend_name_stored(self):
        """Backend should store its name."""
        backend = ConcreteOCRBackend()

        assert backend.name == "TestBackend"

    @pytest.mark.unit
    def test_backend_is_available_check(self):
        """BKD-003: is_available should return correct status."""
        available_backend = ConcreteOCRBackend(available=True)
        unavailable_backend = ConcreteOCRBackend(available=False)

        assert available_backend.is_available() is True
        assert unavailable_backend.is_available() is False

    @pytest.mark.unit
    def test_backend_repr(self):
        """Backend repr should show name and availability."""
        available = ConcreteOCRBackend(available=True)
        unavailable = ConcreteOCRBackend(available=False)

        assert "TestBackend" in repr(available)
        assert "available" in repr(available)
        assert "unavailable" in repr(unavailable)

    @pytest.mark.unit
    def test_backend_supported_formats_default(self):
        """BKD-004: Default supported formats should include common types."""
        backend = ConcreteOCRBackend()

        formats = backend.get_supported_formats()

        assert ".pdf" in formats
        assert ".png" in formats
        assert ".jpg" in formats
        assert ".jpeg" in formats
        assert ".tiff" in formats

    @pytest.mark.unit
    def test_backend_extract_document_default_implementation(
        self, create_text_pdf
    ):
        """extract_document should call extract_text for each page."""
        backend = ConcreteOCRBackend()
        pdf_path = create_text_pdf("multi.pdf", "Test")

        result = backend.extract_document(pdf_path)

        assert result.success is True
        assert result.file_name == "multi.pdf"
        assert len(result.pages) >= 1
        assert result.metadata["backend"] == "TestBackend"

    @pytest.mark.unit
    def test_backend_extract_document_specific_pages(self, create_multipage_text_pdf):
        """extract_document should process only specified pages."""
        backend = ConcreteOCRBackend()
        pdf_path = create_multipage_text_pdf("specific.pdf", pages=5)

        result = backend.extract_document(pdf_path, pages=[1, 3, 5])

        assert result.success is True
        assert len(result.pages) == 3
        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 3
        assert result.pages[2].page_number == 5

    @pytest.mark.unit
    def test_backend_extract_document_handles_error(self, temp_dir):
        """extract_document should handle errors gracefully."""
        # Create a backend that raises an error on extract_text
        class ErrorBackend(BaseOCRBackend):
            def __init__(self):
                super().__init__(name="ErrorBackend")

            def extract_text(self, file_path, page_number=None, **kwargs):
                raise RuntimeError("Simulated extraction error")

            def is_available(self):
                return True

        backend = ErrorBackend()
        # Create a valid PDF so _get_page_numbers works, but extract_text will fail
        from text_extraction import PDFTypeDetector
        import fitz
        test_pdf = temp_dir / "test.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(str(test_pdf))
        doc.close()

        result = backend.extract_document(test_pdf)

        assert result.success is False
        assert result.error is not None
        assert "Simulated extraction error" in result.error

    @pytest.mark.unit
    def test_backend_get_page_numbers_pdf(self, create_multipage_text_pdf):
        """BKD-005: _get_page_numbers should return correct count for PDF."""
        backend = ConcreteOCRBackend()
        pdf_path = create_multipage_text_pdf("pages.pdf", pages=7)

        pages = backend._get_page_numbers(pdf_path)

        assert pages == [1, 2, 3, 4, 5, 6, 7]

    @pytest.mark.unit
    def test_backend_get_page_numbers_image(self, temp_dir):
        """BKD-006: _get_page_numbers should return [1] for images."""
        backend = ConcreteOCRBackend()

        # Create a dummy image file
        image_path = temp_dir / "test.png"
        image_path.write_bytes(b"fake image data")

        pages = backend._get_page_numbers(image_path)

        assert pages == [1]

    @pytest.mark.unit
    def test_backend_extract_document_tracks_timing(self, create_text_pdf):
        """extract_document should track processing time."""
        backend = ConcreteOCRBackend()
        pdf_path = create_text_pdf("timing.pdf", "Test")

        result = backend.extract_document(pdf_path)

        assert result.processing_time_ms > 0
        for page in result.pages:
            assert page.processing_time_ms >= 0


# =============================================================================
# Test: Backend Inheritance Pattern
# =============================================================================

class TestBackendInheritance:
    """Tests for proper backend inheritance patterns."""

    @pytest.mark.unit
    def test_abstract_methods_must_be_implemented(self):
        """Backends must implement extract_text and is_available."""

        class IncompleteBackend(BaseOCRBackend):
            pass

        with pytest.raises(TypeError):
            IncompleteBackend()  # Should fail - abstract methods not implemented

    @pytest.mark.unit
    def test_partial_implementation_fails(self):
        """Partial implementation should still fail."""

        class PartialBackend(BaseOCRBackend):
            def extract_text(self, file_path, page_number=None, **kwargs):
                return OCRResult(text="test")
            # Missing is_available

        with pytest.raises(TypeError):
            PartialBackend()
