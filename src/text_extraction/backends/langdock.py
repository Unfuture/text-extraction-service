"""
Langdock OCR Backend
====================

LLM-based OCR using Langdock API (Claude, GPT-4o).
Best quality OCR, especially for complex documents.
"""

import os
import base64
import time
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
import fitz  # PyMuPDF

from .base import BaseOCRBackend, OCRResult, ExtractionMethod


class LangdockBackend(BaseOCRBackend):
    """
    OCR backend using Langdock API with vision-capable LLMs.

    Uses Claude Sonnet 4.5 or similar models to extract text
    from images with high accuracy.

    Environment variables:
        LANGDOCK_API_KEY: API key for Langdock
        LANGDOCK_UPLOAD_URL: Upload endpoint (default: https://api.langdock.com/attachment/v1/upload)
        LANGDOCK_ASSISTANT_URL: Chat completions endpoint
        LANGDOCK_OCR_MODEL: Model to use (default: claude-sonnet-4-5)
    """

    DEFAULT_UPLOAD_URL = "https://api.langdock.com/attachment/v1/upload"
    DEFAULT_ASSISTANT_URL = "https://api.langdock.com/assistant/v1/chat/completions"
    DEFAULT_MODEL = "claude-sonnet-4-5@20250929"

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
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        upload_url: Optional[str] = None,
        assistant_url: Optional[str] = None,
        temperature: float = 0.0,
        timeout: int = 120,
    ):
        """
        Initialize Langdock backend.

        Args:
            api_key: Langdock API key (or LANGDOCK_API_KEY env var)
            model: Model to use (or LANGDOCK_OCR_MODEL env var)
            upload_url: Upload endpoint URL
            assistant_url: Chat completions endpoint URL
            temperature: Model temperature (0.0 for deterministic)
            timeout: Request timeout in seconds
        """
        super().__init__(name="Langdock")

        self.api_key = api_key or os.getenv("LANGDOCK_API_KEY")
        self.model = model or os.getenv("LANGDOCK_OCR_MODEL", self.DEFAULT_MODEL)
        self.upload_url = upload_url or os.getenv("LANGDOCK_UPLOAD_URL", self.DEFAULT_UPLOAD_URL)
        self.assistant_url = assistant_url or os.getenv("LANGDOCK_ASSISTANT_URL", self.DEFAULT_ASSISTANT_URL)
        self.temperature = temperature
        self.timeout = timeout

    def is_available(self) -> bool:
        """Check if Langdock API is configured."""
        return bool(self.api_key)

    def extract_text(
        self,
        file_path: Path,
        page_number: Optional[int] = None,
        **kwargs
    ) -> OCRResult:
        """
        Extract text from a PDF page or image using Langdock LLM.

        Args:
            file_path: Path to PDF or image file
            page_number: Page to extract (1-indexed), None for single image
            **kwargs: Additional options (prompt, timeout)

        Returns:
            OCRResult with extracted text
        """
        if not self.is_available():
            raise RuntimeError("Langdock API key not configured")

        start_time = time.time()
        prompt = kwargs.get("prompt", self.OCR_PROMPT)
        timeout = kwargs.get("timeout", self.timeout)

        # Convert PDF page to image if needed
        if file_path.suffix.lower() == ".pdf":
            if page_number is None:
                page_number = 1
            image_data = self._pdf_page_to_image(file_path, page_number)
        else:
            # Direct image file
            with open(file_path, "rb") as f:
                image_data = f.read()

        # Upload image and get text
        text = self._ocr_with_langdock(image_data, file_path.name, prompt, timeout)

        processing_time = (time.time() - start_time) * 1000

        return OCRResult(
            text=text,
            confidence=0.95,  # LLM OCR is typically high quality
            method=ExtractionMethod.LLM_OCR,
            page_number=page_number,
            metadata={
                "model": self.model,
                "processing_time_ms": processing_time,
            }
        )

    def _pdf_page_to_image(self, pdf_path: Path, page_number: int) -> bytes:
        """Convert a PDF page to PNG image bytes."""
        doc = fitz.open(pdf_path)
        try:
            # page_number is 1-indexed, fitz uses 0-indexed
            page = doc[page_number - 1]

            # Render at 2x resolution for better OCR
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)

            return pix.tobytes("png")
        finally:
            doc.close()

    def _ocr_with_langdock(
        self,
        image_data: bytes,
        filename: str,
        prompt: str,
        timeout: int
    ) -> str:
        """
        Send image to Langdock for OCR.

        Args:
            image_data: PNG image bytes
            filename: Original filename for reference
            prompt: OCR extraction prompt
            timeout: Request timeout

        Returns:
            Extracted text
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        # Step 1: Upload image
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_data)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                files = {"file": (f"{filename}.png", f, "image/png")}
                upload_response = requests.post(
                    self.upload_url,
                    headers=headers,
                    files=files,
                    timeout=timeout
                )

            if upload_response.status_code != 200:
                raise RuntimeError(
                    f"Upload failed: {upload_response.status_code} - {upload_response.text}"
                )

            attachment_id = upload_response.json()["attachmentId"]
        finally:
            os.unlink(tmp_path)

        # Step 2: Send to LLM for OCR
        headers["Content-Type"] = "application/json"

        payload = {
            "assistant": {
                "name": "OCR-Assistent",
                "model": self.model,
                "temperature": self.temperature,
                "instructions": "Du bist ein präziser OCR-Assistent. Extrahiere Text exakt wie er im Dokument steht.",
            },
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "attachmentIds": [attachment_id]
                }
            ]
        }

        response = requests.post(
            self.assistant_url,
            headers=headers,
            json=payload,
            timeout=timeout
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"OCR failed: {response.status_code} - {response.text}"
            )

        return self._extract_text_from_response(response.json())

    def _extract_text_from_response(self, response: Dict[str, Any]) -> str:
        """Extract text content from Langdock API response."""
        if "result" not in response:
            raise ValueError("No 'result' in response")

        # Find assistant message with text content
        for message in reversed(response["result"]):
            if message.get("role") == "assistant":
                content = message.get("content", [])

                if isinstance(content, str):
                    return content.strip()
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            return item.get("text", "").strip()
                        elif isinstance(item, str):
                            return item.strip()

        raise ValueError("No text content found in response")
