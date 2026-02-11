"""
Async Job Queue for Large PDF Processing
=========================================

Async PDF extraction with job tracking, progress monitoring,
and optional webhook notifications.
"""

import asyncio
import logging
import tempfile
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import requests as http_requests
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

JOB_EXPIRY_HOURS = 24


class JobStatus(str, Enum):
    """Status of an async extraction job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResponse(BaseModel):
    """Job status response."""

    job_id: str
    status: JobStatus
    file_name: str
    progress: int  # 0-100
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    processing_time_ms: float | None = None
    error: str | None = None


class AsyncExtractionResponse(BaseModel):
    """Response from starting an async extraction job."""

    job_id: str
    status: JobStatus
    status_url: str
    result_url: str


class Job:
    """Internal job representation."""

    def __init__(
        self,
        job_id: str,
        file_name: str,
        file_path: Path,
        quality: str,
        model: str | None = None,
        callback_url: str | None = None,
    ):
        self.job_id = job_id
        self.file_name = file_name
        self.file_path = file_path
        self.quality = quality
        self.model = model
        self.callback_url = callback_url
        self.status = JobStatus.PENDING
        self.progress = 0
        self.created_at = datetime.utcnow()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.processing_time_ms: float | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None


class JobStore(ABC):
    """Abstract job storage. Extend with RedisJobStore for production."""

    @abstractmethod
    def create(self, job: Job) -> str: ...

    @abstractmethod
    def get(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def update(self, job_id: str, **kwargs: Any) -> None: ...

    @abstractmethod
    def cleanup_expired(self) -> int: ...


class InMemoryJobStore(JobStore):
    """Simple in-memory job storage for development."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self, job: Job) -> str:
        self._jobs[job.job_id] = job
        return job.job_id

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs: Any) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

    def cleanup_expired(self) -> int:
        """Remove jobs older than JOB_EXPIRY_HOURS."""
        cutoff = datetime.utcnow() - timedelta(hours=JOB_EXPIRY_HOURS)
        expired = [
            jid for jid, job in self._jobs.items() if job.created_at < cutoff
        ]
        for jid in expired:
            job = self._jobs.pop(jid)
            if job.file_path.exists():
                job.file_path.unlink(missing_ok=True)
        return len(expired)


def _serialize_result(result: Any) -> dict[str, Any]:
    """Convert ExtractionResult to a JSON-serializable dict."""
    result_dict: dict[str, Any] = {
        "success": True,
        "file_name": result.file_name,
        "pdf_type": result.pdf_type,
        "total_pages": result.total_pages,
        "text": result.text,
        "word_count": result.word_count,
        "confidence": result.confidence,
        "processing_time_ms": result.processing_time_ms,
        "extraction_method": result.extraction_method,
    }

    if result.backend_status:
        bs = result.backend_status
        result_dict["backend_status"] = {
            "primary_backend": bs.primary_backend,
            "primary_available": bs.primary_available,
            "fallback_backend": bs.fallback_backend,
            "fallback_available": bs.fallback_available,
            "attempted_pages": bs.attempted_pages,
            "successful_pages": bs.successful_pages,
            "failed_pages": bs.failed_pages,
        }

    if result.page_errors:
        result_dict["page_errors"] = [
            {
                "page_number": pe.page_number,
                "backend": pe.backend,
                "error": pe.error,
            }
            for pe in result.page_errors
        ]

    return result_dict


def process_job(job: Job, store: JobStore, get_processor_fn: Any) -> None:
    """Process an extraction job in the background."""
    store.update(
        job.job_id,
        status=JobStatus.PROCESSING,
        started_at=datetime.utcnow(),
        progress=10,
    )

    try:
        processor = get_processor_fn(model=job.model)
        result = processor.extract(
            job.file_path,
            quality=job.quality,
            model=job.model,
        )

        if result.success:
            store.update(
                job.job_id,
                status=JobStatus.COMPLETED,
                completed_at=datetime.utcnow(),
                progress=100,
                processing_time_ms=result.processing_time_ms,
                result=_serialize_result(result),
            )
        else:
            store.update(
                job.job_id,
                status=JobStatus.FAILED,
                completed_at=datetime.utcnow(),
                progress=100,
                error=result.error or "Extraction failed",
            )

    except Exception as e:
        logger.exception("Job %s failed: %s", job.job_id, e)
        store.update(
            job.job_id,
            status=JobStatus.FAILED,
            completed_at=datetime.utcnow(),
            progress=100,
            error=str(e),
        )

    finally:
        if job.file_path.exists():
            job.file_path.unlink(missing_ok=True)

    # Send webhook notification if configured
    if job.callback_url:
        _send_webhook(job, store)


def _send_webhook(job: Job, store: JobStore) -> None:
    """Send webhook notification for completed/failed job."""
    updated_job = store.get(job.job_id)
    if updated_job is None or not updated_job.callback_url:
        return

    payload = {
        "job_id": updated_job.job_id,
        "status": updated_job.status.value,
        "file_name": updated_job.file_name,
    }

    try:
        http_requests.post(updated_job.callback_url, json=payload, timeout=10)
        logger.info("Webhook sent for job %s to %s", job.job_id, job.callback_url)
    except Exception as e:
        logger.warning("Webhook failed for job %s: %s", job.job_id, e)


def create_router(store: JobStore, get_processor_fn: Any) -> APIRouter:
    """Create the async jobs APIRouter."""
    router = APIRouter(tags=["Async Jobs"])

    @router.post(
        "/api/v1/extract/async",
        response_model=AsyncExtractionResponse,
        status_code=202,
    )
    async def extract_async(
        file: UploadFile = File(..., description="PDF file to extract text from"),
        quality: str = Query(
            default="balanced",
            description="Quality: fast, balanced, accurate",
            pattern="^(fast|balanced|accurate)$",
        ),
        model: str | None = Query(default=None, description="OCR model override"),
        callback_url: str | None = Query(
            default=None, description="Webhook URL for completion notification"
        ),
    ) -> AsyncExtractionResponse:
        """
        Start an async text extraction job.

        Returns a job ID immediately. Poll the status URL for progress.
        For small PDFs (<5 pages), prefer the synchronous `/api/v1/extract`.
        """
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        store.cleanup_expired()

        # Save file to persistent temp location (not auto-deleted)
        tmp_dir = Path(tempfile.mkdtemp(prefix="textextract_"))
        tmp_path = tmp_dir / (file.filename or "upload.pdf")
        content = await file.read()
        tmp_path.write_bytes(content)

        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            file_name=file.filename or "upload.pdf",
            file_path=tmp_path,
            quality=quality,
            model=model,
            callback_url=callback_url,
        )
        store.create(job)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, process_job, job, store, get_processor_fn)

        logger.info("Async job %s created for %s", job_id, file.filename)

        return AsyncExtractionResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            status_url=f"/api/v1/jobs/{job_id}",
            result_url=f"/api/v1/jobs/{job_id}/result",
        )

    @router.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
    async def get_job_status(job_id: str) -> JobResponse:
        """Get status and progress of an async extraction job."""
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        return JobResponse(
            job_id=job.job_id,
            status=job.status,
            file_name=job.file_name,
            progress=job.progress,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            processing_time_ms=job.processing_time_ms,
            error=job.error,
        )

    @router.get("/api/v1/jobs/{job_id}/result")
    async def get_job_result(job_id: str) -> dict[str, Any]:
        """Get extraction result for a completed job. Returns 409 if still processing."""
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status == JobStatus.PENDING:
            raise HTTPException(status_code=409, detail="Job is pending")

        if job.status == JobStatus.PROCESSING:
            raise HTTPException(status_code=409, detail="Job is still processing")

        if job.status == JobStatus.FAILED:
            raise HTTPException(
                status_code=500, detail=job.error or "Extraction failed"
            )

        if job.result is None:
            raise HTTPException(status_code=500, detail="Result not available")

        return job.result

    return router
