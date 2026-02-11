"""
Text Extraction Service - FastAPI Application

Minimal REST API for PDF text extraction and classification.
"""

import logging
import os
import tempfile
import time
from pathlib import Path

import requests as http_requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from text_extraction import (
    PDFClassificationResult,
    PDFTypeDetector,
    ProcessorConfig,
    TwoPassProcessor,
)
from text_extraction.backends import GeminiBackend, LangdockBackend, TesseractBackend

from service.jobs import InMemoryJobStore, create_router

# Initialize FastAPI app
app = FastAPI(
    title="Text Extraction Service",
    description="PDF text extraction with intelligent OCR routing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Initialize detector, OCR backends, and job store
detector = PDFTypeDetector()
_job_store = InMemoryJobStore()

# Initialize OCR backends (lazy - check availability on use)
# Note: get_processor is defined below, router registered after function definition
_langdock_backend: LangdockBackend | None = None
_gemini_backend: GeminiBackend | None = None
_tesseract_backend: TesseractBackend | None = None
_langdock_processor: TwoPassProcessor | None = None
_gemini_processor: TwoPassProcessor | None = None


def _is_gemini_model(model: str | None) -> bool:
    """Check if the requested model should be routed to the Gemini backend."""
    return bool(model and model.startswith("gemini-"))


def get_processor(model: str | None = None) -> TwoPassProcessor:
    """
    Get or create the TwoPassProcessor for the given model.

    Routes gemini-* models to GeminiBackend, all others to LangdockBackend.
    """
    if _is_gemini_model(model):
        return _get_gemini_processor()
    return _get_default_processor()


def _get_default_processor() -> TwoPassProcessor:
    """Get Langdock-based processor (default)."""
    global _langdock_processor, _langdock_backend, _tesseract_backend

    if _langdock_processor is None:
        if _langdock_backend is None:
            _langdock_backend = LangdockBackend()
        if _tesseract_backend is None:
            _tesseract_backend = TesseractBackend()

        primary = _langdock_backend if _langdock_backend.is_available() else None
        fallback = _tesseract_backend if _tesseract_backend.is_available() else None

        if primary is None and fallback is not None:
            primary = fallback
            fallback = None

        _langdock_processor = TwoPassProcessor(
            primary_backend=primary,
            fallback_backend=fallback,
            config=ProcessorConfig(
                fallback_on_error=True,
                include_page_markers=True,
            ),
        )

    return _langdock_processor


def _get_gemini_processor() -> TwoPassProcessor:
    """Get Gemini-based processor."""
    global _gemini_processor, _gemini_backend, _tesseract_backend

    if _gemini_processor is None:
        if _gemini_backend is None:
            _gemini_backend = GeminiBackend()
        if _tesseract_backend is None:
            _tesseract_backend = TesseractBackend()

        primary = _gemini_backend if _gemini_backend.is_available() else None
        fallback = _tesseract_backend if _tesseract_backend.is_available() else None

        if primary is None and fallback is not None:
            primary = fallback
            fallback = None

        _gemini_processor = TwoPassProcessor(
            primary_backend=primary,
            fallback_backend=fallback,
            config=ProcessorConfig(
                fallback_on_error=True,
                include_page_markers=True,
            ),
        )

    return _gemini_processor


# Register async jobs router
app.include_router(create_router(store=_job_store, get_processor_fn=get_processor))


# ============================================================================
# Pydantic Models
# ============================================================================


class BackendStatusResponse(BaseModel):
    """OCR backend status in extraction response."""

    primary_backend: str
    primary_available: bool
    fallback_backend: str | None = None
    fallback_available: bool = False
    attempted_pages: int = 0
    successful_pages: int = 0
    failed_pages: int = 0


class PageErrorResponse(BaseModel):
    """Error from a specific page during OCR extraction."""

    page_number: int
    backend: str
    error: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "0.1.0"
    uptime_seconds: float
    backends: dict[str, bool] = {}


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
    backend_status: BackendStatusResponse | None = None
    page_errors: list[PageErrorResponse] = []


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool = False
    error: str
    detail: str | None = None


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
    global _langdock_backend, _gemini_backend, _tesseract_backend

    if _langdock_backend is None:
        _langdock_backend = LangdockBackend()
    if _gemini_backend is None:
        _gemini_backend = GeminiBackend()
    if _tesseract_backend is None:
        _tesseract_backend = TesseractBackend()

    backends = {
        "langdock": _langdock_backend.is_available(),
        "gemini": _gemini_backend.is_available(),
        "tesseract": _tesseract_backend.is_available(),
    }

    return HealthResponse(
        status="healthy",
        version="0.1.0",
        uptime_seconds=time.time() - _start_time,
        backends=backends,
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


@app.get("/api/v1/models", tags=["System"])
async def list_models():
    """
    List available OCR models (EU region only).

    Returns models from the Langdock API filtered to EU-hosted models
    for GDPR/data residency compliance.
    """
    api_key = os.getenv("LANGDOCK_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Langdock API not configured")

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = http_requests.get(
            "https://api.langdock.com/assistant/v1/models",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        # Deduplicate and filter to EU region only
        seen = set()
        eu_models = []
        for m in data.get("data", []):
            if m.get("region") == "eu" and m["id"] not in seen:
                seen.add(m["id"])
                eu_models.append({"id": m["id"], "region": m["region"]})

        default_model = os.getenv(
            "LANGDOCK_OCR_MODEL", LangdockBackend.DEFAULT_MODEL
        )
        return {
            "default": default_model,
            "models": sorted(eu_models, key=lambda x: x["id"]),
        }
    except http_requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models: {e}")


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
    model: str | None = Query(
        default=None,
        description=(
            "OCR model override (EU region only). "
            "Default: claude-sonnet-4-5@20250929. "
            "Available: claude-sonnet-4-5@20250929, claude-haiku-4-5@20251001, "
            "claude-opus-4-5@20251101, claude-opus-4-6@default, "
            "gemini-2.5-flash, gemini-2.5-pro, "
            "gpt-5-mini-eu, gpt-5.1, gpt-5.2, gpt-5.2-pro"
        ),
    ),
):
    """
    Extract text from a PDF file.

    **Quality options:**
    - **fast**: Direct extraction only, no OCR
    - **balanced**: OCR for image pages only (default)
    - **accurate**: Full OCR verification for all pages

    **Available OCR models** (EU region, only used when OCR is triggered):

    | Model | Provider | Notes |
    |-------|----------|-------|
    | `claude-sonnet-4-5@20250929` | Anthropic | **Default** - Best quality/cost ratio |
    | `claude-haiku-4-5@20251001` | Anthropic | Fastest, lowest cost |
    | `claude-opus-4-5@20251101` | Anthropic | Highest quality |
    | `claude-opus-4-6@default` | Anthropic | Latest Opus |
    | `gemini-2.5-flash` | Google | Fast, good quality |
    | `gemini-2.5-pro` | Google | High quality |
    | `gpt-5-mini-eu` | OpenAI | Fast, EU-hosted |
    | `gpt-5.1` | OpenAI | Good quality |
    | `gpt-5.2` | OpenAI | Latest GPT |
    | `gpt-5.2-pro` | OpenAI | Highest OpenAI quality |

    Use **GET /api/v1/models** for the live list from the API.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            # Use TwoPassProcessor for extraction (model-based routing)
            processor = get_processor(model=model)
            result = processor.extract(tmp_path, quality=quality, model=model)

            if not result.success:
                raise HTTPException(
                    status_code=500,
                    detail=result.error or "Extraction failed"
                )

            backend_status = None
            if result.backend_status:
                bs = result.backend_status
                backend_status = BackendStatusResponse(
                    primary_backend=bs.primary_backend,
                    primary_available=bs.primary_available,
                    fallback_backend=bs.fallback_backend,
                    fallback_available=bs.fallback_available,
                    attempted_pages=bs.attempted_pages,
                    successful_pages=bs.successful_pages,
                    failed_pages=bs.failed_pages,
                )

            page_errors = [
                PageErrorResponse(
                    page_number=pe.page_number,
                    backend=pe.backend,
                    error=pe.error,
                )
                for pe in result.page_errors
            ]

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
                backend_status=backend_status,
                page_errors=page_errors,
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
