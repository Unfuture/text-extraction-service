"""
Tesseract OCR Backend
=====================

Local OCR using Tesseract. Free, offline, good for simple documents.
"""

import os
import time
from pathlib import Path
from typing import Optional, List

import fitz  # PyMuPDF
from PIL import Image
import pytesseract

from .base import BaseOCRBackend, OCRResult, ExtractionMethod


class TesseractBackend(BaseOCRBackend):
    """
    OCR backend using local Tesseract installation.

    Good for:
    - Offline processing
    - Simple, clean documents
    - Cost-free OCR

    Environment variables:
        TESSERACT_PATH: Path to tesseract binary (default: /usr/bin/tesseract)
        TESSERACT_LANG: Languages to use (default: deu+eng)
    """

    def __init__(
        self,
        tesseract_path: Optional[str] = None,
        lang: Optional[str] = None,
        dpi: int = 300,
    ):
        """
        Initialize Tesseract backend.

        Args:
            tesseract_path: Path to tesseract binary
            lang: OCR languages (e.g., "deu+eng")
            dpi: DPI for PDF to image conversion
        """
        super().__init__(name="Tesseract")

        self.tesseract_path = tesseract_path or os.getenv(
            "TESSERACT_PATH", "/usr/bin/tesseract"
        )
        self.lang = lang or os.getenv("TESSERACT_LANG", "deu+eng")
        self.dpi = dpi

        # Configure pytesseract
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_path

    def is_available(self) -> bool:
        """Check if Tesseract is installed and accessible."""
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extract_text(
        self,
        file_path: Path,
        page_number: Optional[int] = None,
        **kwargs
    ) -> OCRResult:
        """
        Extract text from a PDF page or image using Tesseract.

        Args:
            file_path: Path to PDF or image file
            page_number: Page to extract (1-indexed), None for single image
            **kwargs: Additional options (lang, dpi, config)

        Returns:
            OCRResult with extracted text
        """
        if not self.is_available():
            raise RuntimeError("Tesseract is not available")

        start_time = time.time()
        lang = kwargs.get("lang", self.lang)
        dpi = kwargs.get("dpi", self.dpi)
        config = kwargs.get("config", "")

        # Convert PDF page to image if needed
        if file_path.suffix.lower() == ".pdf":
            if page_number is None:
                page_number = 1
            image = self._pdf_page_to_pil(file_path, page_number, dpi)
        else:
            image = Image.open(file_path)

        # Run Tesseract OCR
        text = pytesseract.image_to_string(
            image,
            lang=lang,
            config=config
        )

        # Get confidence if available
        try:
            data = pytesseract.image_to_data(
                image, lang=lang, output_type=pytesseract.Output.DICT
            )
            confidences = [
                int(c) for c in data["conf"] if c != "-1" and str(c).isdigit()
            ]
            confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.5
        except Exception:
            confidence = 0.5

        processing_time = (time.time() - start_time) * 1000

        return OCRResult(
            text=text.strip(),
            confidence=confidence,
            method=ExtractionMethod.TESSERACT,
            page_number=page_number,
            metadata={
                "lang": lang,
                "dpi": dpi,
                "processing_time_ms": processing_time,
            }
        )

    def _pdf_page_to_pil(
        self,
        pdf_path: Path,
        page_number: int,
        dpi: int = 300
    ) -> Image.Image:
        """Convert a PDF page to PIL Image."""
        doc = fitz.open(pdf_path)
        try:
            # page_number is 1-indexed, fitz uses 0-indexed
            page = doc[page_number - 1]

            # Calculate zoom factor for desired DPI (PDF default is 72 DPI)
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            return img
        finally:
            doc.close()

    def get_available_languages(self) -> List[str]:
        """Get list of installed Tesseract languages."""
        try:
            return pytesseract.get_languages()
        except Exception:
            return []
