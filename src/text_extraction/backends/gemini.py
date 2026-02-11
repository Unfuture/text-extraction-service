"""
Gemini OCR Backend
==================

LLM-based OCR using Google Gemini API with native multimodal support.
Uses PIL Images directly - no base64 encoding needed.
"""

import logging
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import BaseOCRBackend, ExtractionMethod, OCRResult

logger = logging.getLogger(__name__)


class GeminiRetryableError(RuntimeError):
    """Raised for Gemini API errors that are worth retrying (429, RESOURCE_EXHAUSTED)."""


class GeminiBackend(BaseOCRBackend):
    """
    OCR backend using Google Gemini API with vision-capable models.

    Uses the google-genai SDK for native multimodal content generation.
    Accepts PIL Images directly without base64 encoding.

    Environment variables:
        GEMINI_API_KEY: API key for Google Gemini
        GEMINI_OCR_MODEL: Model to use (default: gemini-2.5-flash)
    """

    DEFAULT_MODEL = "gemini-2.5-flash"

    OCR_PROMPT = """Extrahiere den gesamten Text aus diesem Dokument.

Regeln:
- Gib NUR den extrahierten Text zurück, keine Erklärungen
- Behalte die ursprüngliche Formatierung bei (Absätze, Listen, Tabellen)
- Bei Tabellen: Trenne Spalten mit | und Zeilen mit Zeilenumbrüchen
- Ignoriere Wasserzeichen und Hintergründe
- Bei unleserlichen Stellen schreibe [unleserlich]

Text:"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        timeout: int = 120,
    ):
        """
        Initialize Gemini backend.

        Args:
            api_key: Gemini API key (or GEMINI_API_KEY env var)
            model: Model to use (or GEMINI_OCR_MODEL env var)
            temperature: Model temperature (0.0 for deterministic)
            timeout: Request timeout in seconds
        """
        super().__init__(name="Gemini")

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_OCR_MODEL", self.DEFAULT_MODEL)
        self.temperature = temperature
        self.timeout = timeout
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-initialize the genai client."""
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        """Check if Gemini API is configured."""
        return bool(self.api_key)

    def extract_text(
        self,
        file_path: Path,
        page_number: int | None = None,
        **kwargs: Any,
    ) -> OCRResult:
        """
        Extract text from a PDF page or image using Gemini.

        Args:
            file_path: Path to PDF or image file
            page_number: Page to extract (1-indexed), None for single image
            **kwargs: Additional options (model, prompt, timeout)

        Returns:
            OCRResult with extracted text
        """
        if not self.is_available():
            raise RuntimeError("Gemini API key not configured")

        from google.genai import types

        start_time = time.time()
        prompt = kwargs.get("prompt", self.OCR_PROMPT)
        model = kwargs.get("model") or self.model

        # Convert PDF page to PIL Image
        if file_path.suffix.lower() == ".pdf":
            if page_number is None:
                page_number = 1
            image = self._pdf_page_to_image(file_path, page_number)
        else:
            from PIL import Image

            image = Image.open(file_path)

        # Call Gemini API with PIL Image directly (with retry for rate limits)
        response = self._call_api(model, image, prompt, types)

        text = response.text or ""
        processing_time = (time.time() - start_time) * 1000

        logger.info(
            "Gemini OCR completed: model=%s, page=%s, words=%d, time=%.0fms",
            model,
            page_number,
            len(text.split()),
            processing_time,
        )

        return OCRResult(
            text=text,
            confidence=0.92,
            method=ExtractionMethod.LLM_OCR,
            page_number=page_number,
            metadata={
                "model": model,
                "backend": "gemini",
                "processing_time_ms": processing_time,
            },
        )

    @retry(
        retry=retry_if_exception_type(GeminiRetryableError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        before_sleep=lambda retry_state: logger.warning(
            "Gemini API rate limited, retrying in %.0fs (attempt %d/5)",
            retry_state.next_action.sleep,  # type: ignore[union-attr]
            retry_state.attempt_number,
        ),
        reraise=True,
    )
    def _call_api(self, model: str, image: Any, prompt: str, types: Any) -> Any:
        """Call Gemini API with retry logic for rate limits."""
        from google.genai import errors as genai_errors

        client = self._get_client()
        try:
            return client.models.generate_content(
                model=model,
                contents=[image, prompt],
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    http_options=types.HttpOptions(timeout=self.timeout * 1000),
                ),
            )
        except genai_errors.ClientError as exc:
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                raise GeminiRetryableError(str(exc)) from exc
            raise  # Non-retryable client error

    def _pdf_page_to_image(self, pdf_path: Path, page_number: int) -> Any:
        """
        Convert a PDF page to a PIL Image.

        Args:
            pdf_path: Path to PDF file
            page_number: Page number (1-indexed)

        Returns:
            PIL.Image.Image
        """
        from PIL import Image

        doc = fitz.open(pdf_path)
        try:
            page = doc[page_number - 1]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
            return Image.open(BytesIO(png_bytes))
        finally:
            doc.close()
