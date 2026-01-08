"""
Text Extraction Service - FastAPI Application

Minimal REST API for PDF text extraction and classification.
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from text_extraction import PDFTypeDetector, PDFType, PDFClassificationResult
from text_extraction import TwoPassProcessor, ProcessorConfig
from text_extraction.backends import LangdockBackend, TesseractBackend

# Initialize FastAPI app
app = FastAPI(
    title="Text Extraction Service",
    description="PDF text extraction with intelligent OCR routing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Initialize detector and OCR backends
detector = PDFTypeDetector()

# Initialize OCR backends (lazy - check availability on use)
_langdock_backend: Optional[LangdockBackend] = None
_tesseract_backend: Optional[TesseractBackend] = None
_processor: Optional[TwoPassProcessor] = None


def get_ocr_backend() -> Optional[LangdockBackend | TesseractBackend]:
    """Get best available OCR backend (Langdock preferred, Tesseract fallback)."""
    global _langdock_backend, _tesseract_backend

    # Try Langdock first (best quality)
    if _langdock_backend is None:
        _langdock_backend = LangdockBackend()

    if _langdock_backend.is_available():
        return _langdock_backend

    # Fallback to Tesseract
    if _tesseract_backend is None:
        _tesseract_backend = TesseractBackend()

    if _tesseract_backend.is_available():
        return _tesseract_backend

    return None


def get_processor() -> TwoPassProcessor:
    """Get or create the TwoPassProcessor instance."""
    global _processor, _langdock_backend, _tesseract_backend

    if _processor is None:
        # Initialize backends if needed
        if _langdock_backend is None:
            _langdock_backend = LangdockBackend()
        if _tesseract_backend is None:
            _tesseract_backend = TesseractBackend()

        # Determine primary and fallback backends based on availability
        primary = _langdock_backend if _langdock_backend.is_available() else None
        fallback = _tesseract_backend if _tesseract_backend.is_available() else None

        # If Langdock not available, use Tesseract as primary
        if primary is None and fallback is not None:
            primary = fallback
            fallback = None

        _processor = TwoPassProcessor(
            primary_backend=primary,
            fallback_backend=fallback,
            config=ProcessorConfig(
                fallback_on_error=True,
                include_page_markers=True,
            ),
        )

    return _processor


# ============================================================================
# Pydantic Models
# ============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "0.1.0"
    uptime_seconds: float


class ClassificationResponse(BaseModel):
    """PDF classification response."""

    success: bool
    file_name: str
    pdf_type: str
    total_pages: int
    text_pages: list[int]
    image_pages: list[int]
    hybrid_pages: list[int]
    confidence: float
    processing_time_ms: float


class ExtractionResponse(BaseModel):
    """Text extraction response."""

    success: bool
    file_name: str
    pdf_type: str
    total_pages: int
    text: str
    word_count: int
    confidence: float
    processing_time_ms: float
    extraction_method: str


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool = False
    error: str
    detail: Optional[str] = None


# ============================================================================
# Global state
# ============================================================================

_start_time = time.time()


# ============================================================================
# Endpoints
# ============================================================================


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint for container orchestration."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        uptime_seconds=time.time() - _start_time,
    )


@app.get("/", tags=["System"])
async def root():
    """Root endpoint with API info."""
    return {
        "service": "text-extraction",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.post(
    "/api/v1/classify",
    response_model=ClassificationResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Extraction"],
)
async def classify_pdf(
    file: UploadFile = File(..., description="PDF file to classify"),
):
    """
    Classify a PDF by content type.

    Returns whether the PDF is PURE_TEXT, PURE_IMAGE, or HYBRID,
    along with page-level analysis.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    start_time = time.time()

    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            # Classify PDF
            result: PDFClassificationResult = detector.classify_pdf(tmp_path)

            processing_time = (time.time() - start_time) * 1000

            return ClassificationResponse(
                success=True,
                file_name=file.filename,
                pdf_type=result.pdf_type.value,
                total_pages=result.total_pages,
                text_pages=result.text_pages,
                image_pages=result.image_pages,
                hybrid_pages=result.hybrid_pages,
                confidence=result.confidence,
                processing_time_ms=processing_time,
            )
        finally:
            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@app.post(
    "/api/v1/extract",
    response_model=ExtractionResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Extraction"],
)
async def extract_text(
    file: UploadFile = File(..., description="PDF file to extract text from"),
    quality: str = Query(
        default="balanced",
        description="Quality preference: fast, balanced, accurate",
        pattern="^(fast|balanced|accurate)$",
    ),
):
    """
    Extract text from a PDF file.

    Quality options:
    - **fast**: Direct extraction only, no OCR
    - **balanced**: OCR for image pages only (default)
    - **accurate**: Full OCR verification for all pages

    Note: Full extraction with OCR backends not yet implemented.
    Currently returns direct text extraction only.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    start_time = time.time()

    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            # Use TwoPassProcessor for extraction
            processor = get_processor()
            result = processor.extract(tmp_path, quality=quality)

            if not result.success:
                raise HTTPException(
                    status_code=500,
                    detail=result.error or "Extraction failed"
                )

            return ExtractionResponse(
                success=True,
                file_name=file.filename,
                pdf_type=result.pdf_type,
                total_pages=result.total_pages,
                text=result.text,
                word_count=result.word_count,
                confidence=result.confidence,
                processing_time_ms=result.processing_time_ms,
                extraction_method=result.extraction_method,
            )
        finally:
            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


# ============================================================================
# Error handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler."""
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error", "detail": str(exc)},
    )
