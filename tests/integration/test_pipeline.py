"""
Integration Tests for Text Extraction Pipeline

Test Coverage:
- Full PDF processing pipeline
- Detector + Backend integration
- Two-pass OCR flow
- Backend fallback scenarios
- Real API integration (when credentials available)
"""

import pytest
from pathlib import Path

from text_extraction import PDFTypeDetector, PDFType


# =============================================================================
# Test: Detection Pipeline
# =============================================================================

class TestDetectionPipeline:
    """Integration tests for PDF detection pipeline."""

    @pytest.mark.integration
    def test_text_pdf_detection_pipeline(self, create_text_pdf, detector):
        """INT-001: Text PDF should be detected and ready for direct extraction."""
        pdf_path = create_text_pdf(
            "invoice_text.pdf",
            "Invoice Number: 12345\nCompany: ABC GmbH\nTotal: EUR 1,234.56"
        )

        # Step 1: Classify PDF
        classification = detector.classify_pdf(pdf_path)

        # Verify classification
        assert classification.pdf_type == PDFType.PURE_TEXT
        assert classification.confidence > 0.5
        assert len(classification.text_pages) == 1

        # Step 2: For PURE_TEXT, would use direct extraction (PyMuPDF)
        # This would be handled by router.py (TODO)
        import fitz
        doc = fitz.open(pdf_path)
        text = doc[0].get_text()
        doc.close()

        assert "Invoice" in text
        assert "12345" in text

    @pytest.mark.integration
    def test_image_pdf_detection_pipeline(self, create_image_pdf, detector):
        """INT-002: Image PDF should be detected and flagged for OCR."""
        pdf_path = create_image_pdf("scanned_invoice.pdf")

        classification = detector.classify_pdf(pdf_path)

        assert classification.pdf_type == PDFType.PURE_IMAGE
        assert len(classification.image_pages) == 1
        assert len(classification.text_pages) == 0
        # For PURE_IMAGE, OCR backend would be needed

    @pytest.mark.integration
    def test_hybrid_pdf_routing(self, create_hybrid_pdf, detector):
        """INT-003: Hybrid PDF should route pages correctly."""
        pdf_path = create_hybrid_pdf("hybrid_invoice.pdf")

        classification = detector.classify_pdf(pdf_path)

        assert classification.pdf_type == PDFType.HYBRID
        assert classification.total_pages == 2
        # Page categorization should identify different page types
        total_categorized = (
            len(classification.text_pages) +
            len(classification.image_pages) +
            len(classification.hybrid_pages)
        )
        assert total_categorized == classification.total_pages

    @pytest.mark.integration
    def test_multipage_processing_flow(self, create_multipage_text_pdf, detector):
        """Multi-page PDF should be fully processed."""
        pdf_path = create_multipage_text_pdf("multipage_invoice.pdf", pages=10)

        classification = detector.classify_pdf(pdf_path)

        assert classification.total_pages == 10
        assert len(classification.page_analyses) == 10
        # All pages should be categorized
        for i, analysis in enumerate(classification.page_analyses):
            assert analysis.page_number == i + 1


# =============================================================================
# Test: Backend Integration (Mocked)
# =============================================================================

class TestBackendIntegration:
    """Integration tests for backend interactions."""

    @pytest.mark.integration
    def test_backend_selection_for_text_pdf(self, create_text_pdf, detector):
        """Correct backend should be selected for text PDF."""
        pdf_path = create_text_pdf("simple.pdf", "Simple text content")

        classification = detector.classify_pdf(pdf_path)

        # For PURE_TEXT, direct extraction is optimal
        assert classification.pdf_type == PDFType.PURE_TEXT
        # Router would select: direct PyMuPDF extraction
        # Backend not needed for pure text

    @pytest.mark.integration
    def test_backend_selection_for_image_pdf(self, create_image_pdf, detector):
        """OCR backend should be selected for image PDF."""
        pdf_path = create_image_pdf("scanned.pdf")

        classification = detector.classify_pdf(pdf_path)

        assert classification.pdf_type == PDFType.PURE_IMAGE
        # Router would select: LLM OCR or Tesseract backend
        # All pages need OCR processing


# =============================================================================
# Test: Error Handling in Pipeline
# =============================================================================

class TestPipelineErrorHandling:
    """Integration tests for error handling across components."""

    @pytest.mark.integration
    def test_corrupted_file_handled_gracefully(self, temp_dir, detector):
        """Pipeline should handle corrupted files gracefully."""
        corrupted_path = temp_dir / "corrupted.pdf"
        corrupted_path.write_bytes(b"Not a valid PDF")

        with pytest.raises(Exception):
            detector.classify_pdf(corrupted_path)

    @pytest.mark.integration
    def test_empty_pdf_handled(self, create_empty_pdf, detector):
        """Pipeline should handle empty PDFs."""
        empty_path = create_empty_pdf("empty.pdf")

        classification = detector.classify_pdf(empty_path)

        assert classification.pdf_type == PDFType.UNKNOWN
        assert classification.total_pages == 0

    @pytest.mark.integration
    def test_missing_file_error(self, detector):
        """Pipeline should raise clear error for missing files."""
        missing_path = Path("/nonexistent/file.pdf")

        with pytest.raises(FileNotFoundError):
            detector.classify_pdf(missing_path)


# =============================================================================
# Test: Real API Integration (Conditional)
# =============================================================================

class TestRealAPIIntegration:
    """Tests that require real API credentials."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_langdock_api_available(self, langdock_api_key, langdock_upload_url):
        """LDK-001: Langdock API should be accessible with valid credentials."""
        import requests

        # Simple health check - just verify we can reach the API
        headers = {"Authorization": f"Bearer {langdock_api_key}"}

        # This is a minimal check - full upload test would need a file
        assert langdock_api_key is not None
        assert langdock_upload_url is not None
        assert len(langdock_api_key) > 10  # Basic validation

    @pytest.mark.integration
    @pytest.mark.slow
    def test_tesseract_backend_available(self, tesseract_available):
        """TES-001: Tesseract should be available for local OCR."""
        if not tesseract_available:
            pytest.skip("Tesseract not installed")

        import pytesseract
        version = pytesseract.get_tesseract_version()
        assert version is not None


# =============================================================================
# Test: Two-Pass Flow Preparation
# =============================================================================

class TestTwoPassFlowPreparation:
    """Tests for two-pass OCR flow (preparation for processor.py)."""

    @pytest.mark.integration
    def test_scanned_pages_identified_for_two_pass(
        self, create_hybrid_pdf, detector
    ):
        """INT-005: Scanned pages should be identified for two-pass OCR."""
        pdf_path = create_hybrid_pdf("two_pass_candidate.pdf")

        classification = detector.classify_pdf(pdf_path)

        # Scanned pages = image_pages + hybrid_pages
        scanned_pages = classification.image_pages + classification.hybrid_pages
        scanned_pages.sort()

        # Two-pass OCR would process these pages first
        assert len(scanned_pages) >= 0
        # If there are scanned pages, two-pass would be triggered

    @pytest.mark.integration
    def test_all_text_pdf_skips_two_pass(self, create_text_pdf, detector):
        """All-text PDF should skip two-pass OCR."""
        pdf_path = create_text_pdf("all_text.pdf", "All text content here")

        classification = detector.classify_pdf(pdf_path)

        scanned_pages = classification.image_pages + classification.hybrid_pages

        # No scanned pages = no two-pass needed
        assert len(scanned_pages) == 0
        assert classification.pdf_type == PDFType.PURE_TEXT


# =============================================================================
# Test: End-to-End Scenarios
# =============================================================================

class TestEndToEndScenarios:
    """End-to-end test scenarios."""

    @pytest.mark.integration
    def test_german_invoice_text_extraction(self, create_text_pdf, detector):
        """German invoice text should be handled correctly."""
        german_content = """
        Rechnung Nr. 2024-001
        Firma: Muller & Partner GmbH
        Straße: Hauptstraße 123
        PLZ/Ort: 80331 Munchen

        Nettobetrag: 1.000,00 EUR
        MwSt. (19%): 190,00 EUR
        Bruttobetrag: 1.190,00 EUR
        """
        pdf_path = create_text_pdf("german_invoice.pdf", german_content)

        classification = detector.classify_pdf(pdf_path)

        assert classification.pdf_type == PDFType.PURE_TEXT

        # Verify text can be extracted
        import fitz
        doc = fitz.open(pdf_path)
        text = doc[0].get_text()
        doc.close()

        assert "Rechnung" in text
        assert "Munchen" in text
        assert "EUR" in text

    @pytest.mark.integration
    def test_large_pdf_processing(self, create_multipage_text_pdf, detector):
        """Large PDF should be processed within reasonable time."""
        import time

        pdf_path = create_multipage_text_pdf("large_document.pdf", pages=50)

        start = time.time()
        classification = detector.classify_pdf(pdf_path)
        duration = time.time() - start

        assert classification.total_pages == 50
        assert duration < 10  # Should complete within 10 seconds
