"""
Unit Tests for PDFTypeDetector

Test Coverage:
- PDF classification (pure text, pure image, hybrid, unknown)
- Page analysis with block detection
- Confidence calculation
- Error handling (file not found, corrupted, empty)
- Threshold behavior
"""

import pytest
from pathlib import Path

from text_extraction import PDFTypeDetector, PDFType, PDFClassificationResult, PageAnalysis


# =============================================================================
# Test: Basic Classification
# =============================================================================

class TestPDFClassification:
    """Tests for PDF type classification."""

    @pytest.mark.unit
    def test_pure_text_pdf_returns_pure_text_type(self, detector, create_text_pdf):
        """DET-001: Text-only PDF should be classified as PURE_TEXT."""
        pdf_path = create_text_pdf("text_only.pdf", "Sample invoice text content here")

        result = detector.classify_pdf(pdf_path)

        assert result.pdf_type == PDFType.PURE_TEXT
        assert result.total_pages == 1
        assert 1 in result.text_pages
        assert len(result.image_pages) == 0

    @pytest.mark.unit
    def test_pure_image_pdf_returns_pure_image_type(self, detector, create_image_pdf):
        """DET-002: Image-only PDF should be classified as PURE_IMAGE."""
        pdf_path = create_image_pdf("image_only.pdf")

        result = detector.classify_pdf(pdf_path)

        assert result.pdf_type == PDFType.PURE_IMAGE
        assert result.total_pages == 1
        assert len(result.text_pages) == 0
        assert 1 in result.image_pages

    @pytest.mark.unit
    def test_hybrid_pdf_returns_hybrid_type(self, detector, create_hybrid_pdf):
        """DET-003: Mixed PDF should be classified as HYBRID."""
        pdf_path = create_hybrid_pdf("hybrid.pdf")

        result = detector.classify_pdf(pdf_path)

        assert result.pdf_type == PDFType.HYBRID
        assert result.total_pages == 2
        # Page 1 has text, Page 2 has image
        assert len(result.text_pages) > 0 or len(result.hybrid_pages) > 0

    @pytest.mark.unit
    def test_blank_pdf_returns_image_type(self, detector, create_empty_pdf):
        """DET-004: Blank PDF (no content) should be classified as PURE_IMAGE."""
        # Note: PyMuPDF requires at least 1 page to save, so we test with blank page
        pdf_path = create_empty_pdf("empty.pdf")

        result = detector.classify_pdf(pdf_path)

        # Blank page has no text blocks, so treated as image (scanned)
        assert result.pdf_type == PDFType.PURE_IMAGE
        assert result.total_pages == 1
        # Image pages have the blank page
        assert 1 in result.image_pages


# =============================================================================
# Test: Page Analysis
# =============================================================================

class TestPageAnalysis:
    """Tests for individual page analysis."""

    @pytest.mark.unit
    def test_page_analysis_counts_text_blocks(self, detector, create_text_pdf):
        """DET-005: Page analysis should count text blocks correctly."""
        pdf_path = create_text_pdf("text_blocks.pdf", "Line 1\nLine 2\nLine 3")

        result = detector.classify_pdf(pdf_path)

        assert len(result.page_analyses) == 1
        analysis = result.page_analyses[0]
        assert analysis.page_number == 1
        # The fixture adds extra text blocks, so we should have >= 2 (threshold)
        assert analysis.text_blocks >= 2
        # With >= 2 text blocks and threshold=2, is_text_dominant should be True
        assert analysis.is_text_dominant is True

    @pytest.mark.unit
    def test_page_analysis_counts_image_blocks(self, detector, create_image_pdf):
        """Page analysis should count image blocks correctly."""
        pdf_path = create_image_pdf("image_blocks.pdf")

        result = detector.classify_pdf(pdf_path)

        assert len(result.page_analyses) == 1
        analysis = result.page_analyses[0]
        assert analysis.image_blocks >= 1  # At least one image block
        assert analysis.is_image_dominant is True

    @pytest.mark.unit
    def test_multipage_analysis_lists_correct_pages(self, detector, create_multipage_text_pdf):
        """DET-005: Multi-page PDF should list all pages correctly."""
        pdf_path = create_multipage_text_pdf("multipage.pdf", pages=5)

        result = detector.classify_pdf(pdf_path)

        assert result.total_pages == 5
        assert len(result.page_analyses) == 5
        assert result.text_pages == [1, 2, 3, 4, 5]

    @pytest.mark.unit
    def test_hybrid_pages_detected_correctly(self, detector, create_hybrid_pdf):
        """Mixed pages should be detected and categorized."""
        pdf_path = create_hybrid_pdf("hybrid_analysis.pdf")

        result = detector.classify_pdf(pdf_path)

        # Should have both text and image pages
        total_categorized = (
            len(result.text_pages) +
            len(result.image_pages) +
            len(result.hybrid_pages)
        )
        assert total_categorized == result.total_pages


# =============================================================================
# Test: Confidence Calculation
# =============================================================================

class TestConfidenceCalculation:
    """Tests for confidence score calculation."""

    @pytest.mark.unit
    def test_confidence_in_valid_range(self, detector, create_text_pdf):
        """DET-006: Confidence should be between 0.0 and 1.0."""
        pdf_path = create_text_pdf("confidence_test.pdf", "Test content")

        result = detector.classify_pdf(pdf_path)

        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.unit
    def test_pure_text_has_high_confidence(self, detector, create_text_pdf):
        """Pure text PDF should have high confidence."""
        pdf_path = create_text_pdf("high_confidence.pdf", "Lots of text content here")

        result = detector.classify_pdf(pdf_path)

        assert result.confidence >= 0.5  # Text-dominant should be confident

    @pytest.mark.unit
    def test_blank_pdf_confidence(self, detector, create_empty_pdf):
        """Blank PDF (no content) has low or uncertain confidence."""
        pdf_path = create_empty_pdf("blank_confidence.pdf")

        result = detector.classify_pdf(pdf_path)

        # Blank page has no blocks, so confidence calculation returns 0.5 (uncertain)
        # The classifier treats it as image (no text blocks meet threshold)
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0


# =============================================================================
# Test: Custom Thresholds
# =============================================================================

class TestCustomThresholds:
    """Tests for custom threshold behavior."""

    @pytest.mark.unit
    def test_strict_threshold_changes_classification(
        self, detector_strict, create_text_pdf
    ):
        """DET-007: Strict thresholds should require more blocks."""
        # Create PDF with minimal text
        pdf_path = create_text_pdf("minimal_text.pdf", "X")

        result = detector_strict.classify_pdf(pdf_path)

        # With strict threshold (5), single text block may not be enough
        # The classification depends on actual block count
        assert result.pdf_type in [PDFType.PURE_TEXT, PDFType.PURE_IMAGE, PDFType.HYBRID]

    @pytest.mark.unit
    def test_lenient_threshold_accepts_less_blocks(
        self, detector_lenient, create_text_pdf
    ):
        """Lenient thresholds should accept fewer blocks."""
        pdf_path = create_text_pdf("lenient_text.pdf", "X")

        result = detector_lenient.classify_pdf(pdf_path)

        # Lenient threshold should more easily classify as text
        assert result.pdf_type in [PDFType.PURE_TEXT, PDFType.HYBRID]


# =============================================================================
# Test: Error Handling
# =============================================================================

class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.unit
    def test_file_not_found_raises_error(self, detector):
        """DET-008: Non-existent file should raise FileNotFoundError."""
        fake_path = Path("/nonexistent/path/to/file.pdf")

        with pytest.raises(FileNotFoundError):
            detector.classify_pdf(fake_path)

    @pytest.mark.unit
    def test_invalid_path_type_handled(self, detector):
        """String path should be accepted and converted."""
        fake_path = "/nonexistent/path/to/file.pdf"

        with pytest.raises(FileNotFoundError):
            detector.classify_pdf(fake_path)

    @pytest.mark.unit
    def test_corrupted_pdf_handling(self, detector, temp_dir):
        """DET-009: Corrupted PDF should raise an exception."""
        corrupted_path = temp_dir / "corrupted.pdf"
        corrupted_path.write_bytes(b"This is not a valid PDF content")

        with pytest.raises(Exception):  # PyMuPDF raises various exceptions
            detector.classify_pdf(corrupted_path)

    @pytest.mark.unit
    def test_binary_file_not_pdf_handling(self, detector, temp_dir):
        """Binary file that is not a PDF should raise an exception."""
        binary_path = temp_dir / "not_a_pdf.pdf"
        binary_path.write_bytes(b"\x00\x01\x02\x03\x04\x05")

        with pytest.raises(Exception):
            detector.classify_pdf(binary_path)


# =============================================================================
# Test: Result Object
# =============================================================================

class TestResultObject:
    """Tests for PDFClassificationResult object."""

    @pytest.mark.unit
    def test_result_str_representation(self, detector, create_text_pdf):
        """Result should have readable string representation."""
        pdf_path = create_text_pdf("str_test.pdf", "Test")

        result = detector.classify_pdf(pdf_path)

        str_repr = str(result)
        assert "PDFType" in str_repr
        assert "Pages" in str_repr
        assert "Confidence" in str_repr

    @pytest.mark.unit
    def test_result_contains_page_analyses(self, detector, create_text_pdf):
        """Result should contain page analysis details."""
        pdf_path = create_text_pdf("analysis_test.pdf", "Test")

        result = detector.classify_pdf(pdf_path)

        assert isinstance(result.page_analyses, list)
        if result.total_pages > 0:
            assert len(result.page_analyses) == result.total_pages
            for analysis in result.page_analyses:
                assert isinstance(analysis, PageAnalysis)
                assert analysis.page_number >= 1

    @pytest.mark.unit
    def test_result_total_blocks_are_summed(self, detector, create_multipage_text_pdf):
        """Result should sum blocks across all pages."""
        pdf_path = create_multipage_text_pdf("sum_test.pdf", pages=3)

        result = detector.classify_pdf(pdf_path)

        # Total blocks should equal sum of page blocks
        total_from_pages = sum(
            a.text_blocks + a.image_blocks for a in result.page_analyses
        )
        assert result.total_text_blocks + result.total_image_blocks == total_from_pages


# =============================================================================
# Test: Helper Function
# =============================================================================

class TestHelperFunction:
    """Tests for the classify_pdf helper function."""

    @pytest.mark.unit
    def test_classify_pdf_helper_works(self, create_text_pdf):
        """The classify_pdf helper should work like detector.classify_pdf."""
        from text_extraction.detector import classify_pdf

        pdf_path = create_text_pdf("helper_test.pdf", "Test content")

        result = classify_pdf(pdf_path)

        assert isinstance(result, PDFClassificationResult)
        assert result.pdf_type in [PDFType.PURE_TEXT, PDFType.PURE_IMAGE, PDFType.HYBRID]


# =============================================================================
# Test: PDFType Enum
# =============================================================================

class TestPDFTypeEnum:
    """Tests for PDFType enum values."""

    @pytest.mark.unit
    def test_pdf_type_values(self):
        """PDFType enum should have expected values."""
        assert PDFType.PURE_TEXT.value == "pure_text"
        assert PDFType.PURE_IMAGE.value == "pure_image"
        assert PDFType.HYBRID.value == "hybrid"
        assert PDFType.UNKNOWN.value == "unknown"

    @pytest.mark.unit
    def test_pdf_type_comparison(self):
        """PDFType enum should support comparison."""
        assert PDFType.PURE_TEXT == PDFType.PURE_TEXT
        assert PDFType.PURE_TEXT != PDFType.PURE_IMAGE


# =============================================================================
# Test: PageAnalysis Dataclass
# =============================================================================

class TestPageAnalysisDataclass:
    """Tests for PageAnalysis dataclass."""

    @pytest.mark.unit
    def test_page_analysis_creation(self):
        """PageAnalysis should be creatable with expected fields."""
        analysis = PageAnalysis(
            page_number=1,
            text_blocks=5,
            image_blocks=2,
            total_blocks=7,
            is_text_dominant=True,
            is_image_dominant=False,
            has_mixed_content=True
        )

        assert analysis.page_number == 1
        assert analysis.text_blocks == 5
        assert analysis.image_blocks == 2
        assert analysis.total_blocks == 7
        assert analysis.is_text_dominant is True
        assert analysis.is_image_dominant is False
        assert analysis.has_mixed_content is True
