"""
Test Configuration and Fixtures for text-extraction-service

This module provides shared fixtures, markers, and configuration for all tests.
"""

import os
import tempfile
from pathlib import Path
from typing import Generator, Dict, Any
from dataclasses import dataclass

import pytest


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, no external deps)")
    config.addinivalue_line("markers", "integration: Integration tests (may need APIs)")
    config.addinivalue_line("markers", "performance: Performance benchmark tests")
    config.addinivalue_line("markers", "regression: Regression tests against original 42 PDFs")
    config.addinivalue_line("markers", "slow: Slow tests (skip with -m 'not slow')")
    config.addinivalue_line("markers", "api: API/service tests")


# =============================================================================
# Path Fixtures
# =============================================================================

@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory(prefix="text_extraction_test_") as tmpdir:
        yield Path(tmpdir)


# =============================================================================
# PDF Fixture Data Classes
# =============================================================================

@dataclass
class PDFFixture:
    """Represents a PDF test fixture with expected results."""
    name: str
    path: Path
    expected_type: str  # "pure_text", "pure_image", "hybrid", "unknown"
    expected_pages: int
    expected_text_pages: list
    expected_image_pages: list
    expected_confidence_min: float = 0.5
    expected_confidence_max: float = 1.0
    description: str = ""


@dataclass
class OCRExpectedResult:
    """Expected OCR result for comparison."""
    file_name: str
    success: bool
    text_contains: list  # Key phrases that must be present
    word_count_min: int = 0
    word_count_max: int = 100000


# =============================================================================
# Sample PDF Creation Fixtures
# =============================================================================

@pytest.fixture
def create_text_pdf(temp_dir: Path):
    """Factory fixture to create a text PDF with sufficient text blocks."""
    def _create(filename: str = "text.pdf", content: str = "Sample text content") -> Path:
        try:
            import fitz
            pdf_path = temp_dir / filename
            doc = fitz.open()
            page = doc.new_page()
            # Add multiple text insertions to ensure text_block_threshold (default 2) is met
            y_pos = 72
            for line in content.split('\n') if '\n' in content else [content]:
                page.insert_text((72, y_pos), line, fontsize=12)
                y_pos += 20
            # Add extra text blocks to ensure classification as text
            page.insert_text((72, y_pos), "Additional text block 1", fontsize=12)
            page.insert_text((72, y_pos + 20), "Additional text block 2", fontsize=12)
            page.insert_text((72, y_pos + 40), "Additional text block 3", fontsize=12)
            doc.save(str(pdf_path))
            doc.close()
            return pdf_path
        except ImportError:
            pytest.skip("PyMuPDF not installed")
    return _create


@pytest.fixture
def create_image_pdf(temp_dir: Path):
    """Factory fixture to create a PDF with only images (simulates scanned)."""
    def _create(filename: str = "image.pdf") -> Path:
        try:
            import fitz
            from PIL import Image
            import io

            pdf_path = temp_dir / filename

            # Create a simple image
            img = Image.new('RGB', (200, 100), color='white')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            # Create PDF with image
            doc = fitz.open()
            page = doc.new_page()
            rect = fitz.Rect(72, 72, 300, 200)
            page.insert_image(rect, stream=img_bytes.read())
            doc.save(str(pdf_path))
            doc.close()
            return pdf_path
        except ImportError:
            pytest.skip("PyMuPDF or Pillow not installed")
    return _create


@pytest.fixture
def create_hybrid_pdf(temp_dir: Path):
    """Factory fixture to create a hybrid PDF (text + image pages)."""
    def _create(filename: str = "hybrid.pdf") -> Path:
        try:
            import fitz
            from PIL import Image
            import io

            pdf_path = temp_dir / filename
            doc = fitz.open()

            # Page 1: Text
            page1 = doc.new_page()
            page1.insert_text((72, 72), "This is text content on page 1", fontsize=12)
            page1.insert_text((72, 100), "More text here for detection", fontsize=12)
            page1.insert_text((72, 128), "Additional content line", fontsize=12)

            # Page 2: Image only
            page2 = doc.new_page()
            img = Image.new('RGB', (400, 300), color='lightgray')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            rect = fitz.Rect(72, 72, 500, 400)
            page2.insert_image(rect, stream=img_bytes.read())

            doc.save(str(pdf_path))
            doc.close()
            return pdf_path
        except ImportError:
            pytest.skip("PyMuPDF or Pillow not installed")
    return _create


@pytest.fixture
def create_empty_pdf(temp_dir: Path):
    """Factory fixture to create a minimal PDF (1 blank page - PyMuPDF requires at least 1)."""
    def _create(filename: str = "empty.pdf") -> Path:
        try:
            import fitz
            pdf_path = temp_dir / filename
            doc = fitz.open()
            # PyMuPDF requires at least one page to save
            # Create a blank page with no content
            page = doc.new_page()
            # Don't add any content - this simulates an "empty" PDF
            doc.save(str(pdf_path))
            doc.close()
            return pdf_path
        except ImportError:
            pytest.skip("PyMuPDF not installed")
    return _create


@pytest.fixture
def create_multipage_text_pdf(temp_dir: Path):
    """Factory fixture to create a multi-page text PDF."""
    def _create(filename: str = "multipage.pdf", pages: int = 5) -> Path:
        try:
            import fitz
            pdf_path = temp_dir / filename
            doc = fitz.open()
            for i in range(pages):
                page = doc.new_page()
                page.insert_text((72, 72), f"Page {i + 1} content", fontsize=12)
                page.insert_text((72, 100), f"Additional text on page {i + 1}", fontsize=12)
                page.insert_text((72, 128), f"More content for page {i + 1}", fontsize=12)
            doc.save(str(pdf_path))
            doc.close()
            return pdf_path
        except ImportError:
            pytest.skip("PyMuPDF not installed")
    return _create


# =============================================================================
# Sample Response Fixtures
# =============================================================================

@pytest.fixture
def sample_langdock_response() -> Dict[str, Any]:
    """Sample Langdock API response structure."""
    return {
        "result": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "```json\n{\"supplier\": {\"name\": \"Test Corp\"}, \"amounts\": {\"total\": 100.0}, \"document_flags\": {}, \"line_items\": []}\n```"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_ocr_text_response() -> Dict[str, Any]:
    """Sample Langdock OCR text extraction response."""
    return {
        "result": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "```text\nInvoice Number: 12345\nCompany: ABC GmbH\nAmount: EUR 1,234.56\n```"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_broken_json() -> str:
    """Sample broken JSON for repair testing."""
    return '''{
        "supplier": {
            "name": "Test Corp"
        }
        "amounts": {
            "total": 100.0
        }
    }'''


@pytest.fixture
def sample_valid_invoice_json() -> Dict[str, Any]:
    """Sample valid invoice JSON structure."""
    return {
        "supplier": {"name": "Test GmbH", "address": "Test Street 1"},
        "amounts": {"net": 100.0, "tax": 19.0, "total": 119.0},
        "document_flags": {"is_invoice": True},
        "line_items": [
            {"description": "Item 1", "quantity": 1, "price": 100.0}
        ]
    }


# =============================================================================
# Environment Fixtures
# =============================================================================

@pytest.fixture
def langdock_api_key() -> str:
    """Get Langdock API key from environment, skip if not available."""
    key = os.getenv("LANGDOCK_API_KEY")
    if not key:
        pytest.skip("LANGDOCK_API_KEY not set")
    return key


@pytest.fixture
def langdock_upload_url() -> str:
    """Get Langdock upload URL from environment, skip if not available."""
    url = os.getenv("LANGDOCK_UPLOAD_URL")
    if not url:
        pytest.skip("LANGDOCK_UPLOAD_URL not set")
    return url


@pytest.fixture
def tesseract_available() -> bool:
    """Check if Tesseract is available."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@pytest.fixture
def skip_if_no_tesseract(tesseract_available):
    """Skip test if Tesseract is not available."""
    if not tesseract_available:
        pytest.skip("Tesseract not installed or not accessible")


# =============================================================================
# Detector Fixtures
# =============================================================================

@pytest.fixture
def detector():
    """Create a PDFTypeDetector instance."""
    from text_extraction import PDFTypeDetector
    return PDFTypeDetector()


@pytest.fixture
def detector_strict():
    """Create a PDFTypeDetector with strict thresholds."""
    from text_extraction import PDFTypeDetector
    return PDFTypeDetector(text_block_threshold=5, image_block_threshold=2)


@pytest.fixture
def detector_lenient():
    """Create a PDFTypeDetector with lenient thresholds."""
    from text_extraction import PDFTypeDetector
    return PDFTypeDetector(text_block_threshold=1, image_block_threshold=1)


# =============================================================================
# Helper Functions
# =============================================================================

def text_similarity(text1: str, text2: str) -> float:
    """Calculate simple text similarity (0.0 to 1.0)."""
    if not text1 or not text2:
        return 0.0
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def contains_all_phrases(text: str, phrases: list) -> bool:
    """Check if text contains all given phrases (case-insensitive)."""
    text_lower = text.lower()
    return all(phrase.lower() in text_lower for phrase in phrases)


# =============================================================================
# Performance Fixtures
# =============================================================================

@pytest.fixture
def performance_timer():
    """Simple performance timer context manager."""
    import time

    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.elapsed_ms = None

        def __enter__(self):
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, *args):
            self.end_time = time.perf_counter()
            self.elapsed_ms = (self.end_time - self.start_time) * 1000

    return Timer
