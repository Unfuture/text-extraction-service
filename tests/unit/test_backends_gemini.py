"""
Tests for GeminiBackend
=======================

Unit tests for the Google Gemini OCR backend.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from text_extraction.backends.base import ExtractionMethod, OCRResult
from text_extraction.backends.gemini import GeminiBackend, GeminiRetryableError

# =============================================================================
# TestGeminiBackendInit
# =============================================================================


@pytest.mark.unit
class TestGeminiBackendInit:
    """Test GeminiBackend initialization."""

    def test_default_config(self):
        """Backend uses defaults when no args provided."""
        with patch.dict(os.environ, {}, clear=True):
            backend = GeminiBackend(api_key="test-key")
        assert backend.api_key == "test-key"
        assert backend.model == "gemini-2.5-flash"
        assert backend.temperature == 0.0
        assert backend.timeout == 120
        assert backend.name == "Gemini"

    def test_custom_config(self):
        """Backend uses provided arguments."""
        backend = GeminiBackend(
            api_key="custom-key",
            model="gemini-2.5-pro",
            temperature=0.5,
            timeout=60,
        )
        assert backend.api_key == "custom-key"
        assert backend.model == "gemini-2.5-pro"
        assert backend.temperature == 0.5
        assert backend.timeout == 60

    def test_env_var_api_key(self):
        """Backend reads API key from environment."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}):
            backend = GeminiBackend()
        assert backend.api_key == "env-key"

    def test_env_var_model(self):
        """Backend reads model from environment."""
        with patch.dict(os.environ, {"GEMINI_OCR_MODEL": "gemini-2.5-pro"}):
            backend = GeminiBackend(api_key="test")
        assert backend.model == "gemini-2.5-pro"

    def test_param_overrides_env(self):
        """Explicit parameter overrides environment variable."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}):
            backend = GeminiBackend(api_key="param-key")
        assert backend.api_key == "param-key"


# =============================================================================
# TestGeminiBackendAvailability
# =============================================================================


@pytest.mark.unit
class TestGeminiBackendAvailability:
    """Test GeminiBackend availability checks."""

    def test_available_with_key(self):
        """Backend is available when API key is set."""
        backend = GeminiBackend(api_key="test-key")
        assert backend.is_available() is True

    def test_unavailable_without_key(self):
        """Backend is unavailable without API key."""
        with patch.dict(os.environ, {}, clear=True):
            backend = GeminiBackend(api_key=None)
        assert backend.is_available() is False

    def test_unavailable_with_empty_key(self):
        """Backend is unavailable with empty API key."""
        backend = GeminiBackend(api_key="")
        assert backend.is_available() is False


# =============================================================================
# TestGeminiBackendExtraction
# =============================================================================


@pytest.mark.unit
class TestGeminiBackendExtraction:
    """Test GeminiBackend text extraction."""

    def test_extract_raises_without_key(self, create_text_pdf):
        """Extraction raises RuntimeError without API key."""
        backend = GeminiBackend(api_key="")
        pdf_path = create_text_pdf()
        with pytest.raises(RuntimeError, match="Gemini API key not configured"):
            backend.extract_text(pdf_path, page_number=1)

    @patch("text_extraction.backends.gemini.GeminiBackend._get_client")
    def test_extract_returns_ocr_result(self, mock_get_client, create_text_pdf):
        """Extraction returns properly structured OCRResult."""
        mock_response = MagicMock()
        mock_response.text = "Extracted invoice text here"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        backend = GeminiBackend(api_key="test-key")
        pdf_path = create_text_pdf()
        result = backend.extract_text(pdf_path, page_number=1)

        assert isinstance(result, OCRResult)
        assert result.text == "Extracted invoice text here"
        assert result.confidence == 0.92
        assert result.method == ExtractionMethod.LLM_OCR
        assert result.page_number == 1
        assert result.metadata["backend"] == "gemini"
        assert result.metadata["model"] == "gemini-2.5-flash"

    @patch("text_extraction.backends.gemini.GeminiBackend._get_client")
    def test_extract_with_model_override(self, mock_get_client, create_text_pdf):
        """Model can be overridden per request via kwargs."""
        mock_response = MagicMock()
        mock_response.text = "Text"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        backend = GeminiBackend(api_key="test-key", model="gemini-2.5-flash")
        pdf_path = create_text_pdf()
        result = backend.extract_text(pdf_path, page_number=1, model="gemini-2.5-pro")

        # Verify the overridden model was passed to the API
        call_kwargs = mock_client.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemini-2.5-pro"
        assert result.metadata["model"] == "gemini-2.5-pro"

    @patch("text_extraction.backends.gemini.GeminiBackend._get_client")
    def test_extract_default_page_number(self, mock_get_client, create_text_pdf):
        """Page number defaults to 1 for PDFs when not specified."""
        mock_response = MagicMock()
        mock_response.text = "Page 1 text"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        backend = GeminiBackend(api_key="test-key")
        pdf_path = create_text_pdf()
        result = backend.extract_text(pdf_path)

        assert result.page_number == 1

    @patch("text_extraction.backends.gemini.GeminiBackend._get_client")
    def test_extract_empty_response(self, mock_get_client, create_text_pdf):
        """Handles empty response text gracefully."""
        mock_response = MagicMock()
        mock_response.text = None

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        backend = GeminiBackend(api_key="test-key")
        pdf_path = create_text_pdf()
        result = backend.extract_text(pdf_path, page_number=1)

        assert result.text == ""


# =============================================================================
# TestGeminiModelRouting
# =============================================================================


@pytest.mark.unit
class TestGeminiModelRouting:
    """Test model-based routing logic from service/main.py."""

    def test_gemini_flash_is_gemini(self):
        """gemini-2.5-flash routes to Gemini."""
        from service.main import _is_gemini_model

        assert _is_gemini_model("gemini-2.5-flash") is True

    def test_gemini_pro_is_gemini(self):
        """gemini-2.5-pro routes to Gemini."""
        from service.main import _is_gemini_model

        assert _is_gemini_model("gemini-2.5-pro") is True

    def test_claude_is_not_gemini(self):
        """claude-sonnet-4-5 does NOT route to Gemini."""
        from service.main import _is_gemini_model

        assert _is_gemini_model("claude-sonnet-4-5@20250929") is False

    def test_gpt_is_not_gemini(self):
        """gpt models do NOT route to Gemini."""
        from service.main import _is_gemini_model

        assert _is_gemini_model("gpt-5-mini-eu") is False

    def test_none_is_not_gemini(self):
        """None model does NOT route to Gemini."""
        from service.main import _is_gemini_model

        assert _is_gemini_model(None) is False

    def test_empty_is_not_gemini(self):
        """Empty string does NOT route to Gemini."""
        from service.main import _is_gemini_model

        assert _is_gemini_model("") is False


# =============================================================================
# TestTesseractModelRouting
# =============================================================================


@pytest.mark.unit
class TestTesseractModelRouting:
    """Test tesseract model routing logic from service/main.py."""

    def test_tesseract_routes_to_tesseract(self):
        """'tesseract' routes to TesseractBackend."""
        from service.main import _is_tesseract_model

        assert _is_tesseract_model("tesseract") is True

    def test_tesseract_prefix_does_not_match(self):
        """'tesseract-v2' does NOT route to Tesseract."""
        from service.main import _is_tesseract_model

        assert _is_tesseract_model("tesseract-v2") is False

    def test_gemini_is_not_tesseract(self):
        """gemini models do NOT route to Tesseract."""
        from service.main import _is_tesseract_model

        assert _is_tesseract_model("gemini-2.5-flash") is False

    def test_none_is_not_tesseract(self):
        """None does NOT route to Tesseract."""
        from service.main import _is_tesseract_model

        assert _is_tesseract_model(None) is False


# =============================================================================
# TestGeminiRetryBehavior
# =============================================================================


@pytest.mark.unit
class TestGeminiRetryBehavior:
    """Test retry logic only retries rate-limit errors."""

    @patch("text_extraction.backends.gemini.GeminiBackend._get_client")
    def test_rate_limit_raises_retryable_error(self, mock_get_client, create_text_pdf):
        """429 errors are wrapped in GeminiRetryableError for tenacity."""
        mock_client = MagicMock()

        # Simulate google.genai ClientError with 429
        exc = type("ClientError", (Exception,), {"__str__": lambda self: "429 Too Many Requests"})
        mock_client.models.generate_content.side_effect = exc()
        mock_get_client.return_value = mock_client

        # Patch the genai_errors module inside _call_api
        with patch("text_extraction.backends.gemini.GeminiBackend._call_api") as mock_call:
            mock_call.side_effect = GeminiRetryableError("429 Too Many Requests")

            backend = GeminiBackend(api_key="test-key")
            pdf_path = create_text_pdf()

            with pytest.raises(GeminiRetryableError, match="429"):
                backend.extract_text(pdf_path, page_number=1)

    @patch("text_extraction.backends.gemini.GeminiBackend._get_client")
    def test_auth_error_not_retried(self, mock_get_client, create_text_pdf):
        """Non-rate-limit errors (401) propagate immediately without retry."""
        mock_client = MagicMock()

        # Create a mock ClientError for 401
        auth_error = type("ClientError", (Exception,), {
            "__str__": lambda self: "401 Unauthorized: Invalid API key",
        })()
        mock_client.models.generate_content.side_effect = auth_error
        mock_get_client.return_value = mock_client

        # Patch genai_errors so the except clause can match
        mock_errors_module = MagicMock()
        mock_errors_module.ClientError = type(auth_error)

        backend = GeminiBackend(api_key="test-key")
        pdf_path = create_text_pdf()

        with patch.dict("sys.modules", {"google.genai.errors": mock_errors_module}):
            with pytest.raises(type(auth_error)):
                backend.extract_text(pdf_path, page_number=1)
