"""
Tests for Async Job Queue
==========================

Unit tests for the async job processing system (Issue #6).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from service.jobs import (
    InMemoryJobStore,
    Job,
    JobStatus,
    process_job,
)

# =============================================================================
# TestJobModel
# =============================================================================


@pytest.mark.unit
class TestJobModel:
    """Test Job creation and defaults."""

    def test_job_defaults(self, tmp_path):
        """Job has correct default status and progress."""
        job = Job(
            job_id="test-123",
            file_name="test.pdf",
            file_path=tmp_path / "test.pdf",
            quality="balanced",
        )
        assert job.status == JobStatus.PENDING
        assert job.progress == 0
        assert job.model is None
        assert job.callback_url is None
        assert job.result is None
        assert job.error is None

    def test_job_with_options(self, tmp_path):
        """Job accepts optional model and callback URL."""
        job = Job(
            job_id="test-456",
            file_name="invoice.pdf",
            file_path=tmp_path / "invoice.pdf",
            quality="accurate",
            model="gemini-2.5-flash",
            callback_url="https://example.com/webhook",
        )
        assert job.model == "gemini-2.5-flash"
        assert job.callback_url == "https://example.com/webhook"
        assert job.quality == "accurate"


# =============================================================================
# TestInMemoryJobStore
# =============================================================================


@pytest.mark.unit
class TestInMemoryJobStore:
    """Test InMemoryJobStore operations."""

    def test_create_and_get(self, tmp_path):
        """Store creates and retrieves jobs."""
        store = InMemoryJobStore()
        job = Job(
            job_id="abc",
            file_name="test.pdf",
            file_path=tmp_path / "test.pdf",
            quality="fast",
        )
        store.create(job)
        retrieved = store.get("abc")
        assert retrieved is not None
        assert retrieved.job_id == "abc"
        assert retrieved.file_name == "test.pdf"

    def test_get_nonexistent(self):
        """Store returns None for unknown job IDs."""
        store = InMemoryJobStore()
        assert store.get("nonexistent") is None

    def test_update(self, tmp_path):
        """Store updates job attributes."""
        store = InMemoryJobStore()
        job = Job(
            job_id="update-test",
            file_name="test.pdf",
            file_path=tmp_path / "test.pdf",
            quality="balanced",
        )
        store.create(job)
        store.update("update-test", status=JobStatus.PROCESSING, progress=50)

        updated = store.get("update-test")
        assert updated is not None
        assert updated.status == JobStatus.PROCESSING
        assert updated.progress == 50

    def test_update_nonexistent(self):
        """Updating nonexistent job does nothing."""
        store = InMemoryJobStore()
        store.update("ghost", status=JobStatus.FAILED)  # Should not raise

    def test_cleanup_expired(self, tmp_path):
        """Expired jobs are removed during cleanup."""
        store = InMemoryJobStore()

        # Create an old job
        old_job = Job(
            job_id="old",
            file_name="old.pdf",
            file_path=tmp_path / "old.pdf",
            quality="fast",
        )
        old_job.created_at = datetime.utcnow() - timedelta(hours=25)
        store.create(old_job)

        # Create a recent job
        new_job = Job(
            job_id="new",
            file_name="new.pdf",
            file_path=tmp_path / "new.pdf",
            quality="fast",
        )
        store.create(new_job)

        removed = store.cleanup_expired()
        assert removed == 1
        assert store.get("old") is None
        assert store.get("new") is not None

    def test_cleanup_removes_temp_file(self, tmp_path):
        """Cleanup deletes the temp file for expired jobs."""
        store = InMemoryJobStore()
        temp_file = tmp_path / "expired.pdf"
        temp_file.write_text("dummy content")

        job = Job(
            job_id="expire-file",
            file_name="expired.pdf",
            file_path=temp_file,
            quality="fast",
        )
        job.created_at = datetime.utcnow() - timedelta(hours=25)
        store.create(job)

        store.cleanup_expired()
        assert not temp_file.exists()


# =============================================================================
# TestProcessJob
# =============================================================================


@pytest.mark.unit
class TestProcessJob:
    """Test background job processing."""

    def test_successful_processing(self, create_text_pdf):
        """Job completes successfully with extraction result."""
        pdf_path = create_text_pdf()
        store = InMemoryJobStore()
        job = Job(
            job_id="success-test",
            file_name="test.pdf",
            file_path=pdf_path,
            quality="fast",
        )
        store.create(job)

        # Mock processor that returns a successful result
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.file_name = "test.pdf"
        mock_result.pdf_type = "PURE_TEXT"
        mock_result.total_pages = 1
        mock_result.text = "Hello world"
        mock_result.word_count = 2
        mock_result.confidence = 1.0
        mock_result.processing_time_ms = 100.0
        mock_result.extraction_method = "direct"
        mock_result.backend_status = None
        mock_result.page_errors = []

        mock_processor = MagicMock()
        mock_processor.extract.return_value = mock_result
        mock_get_processor = MagicMock(return_value=mock_processor)

        process_job(job, store, mock_get_processor)

        updated = store.get("success-test")
        assert updated is not None
        assert updated.status == JobStatus.COMPLETED
        assert updated.progress == 100
        assert updated.result is not None
        assert updated.result["text"] == "Hello world"
        assert updated.result["word_count"] == 2

    def test_failed_processing(self, create_text_pdf):
        """Job fails gracefully when extraction fails."""
        pdf_path = create_text_pdf()
        store = InMemoryJobStore()
        job = Job(
            job_id="fail-test",
            file_name="test.pdf",
            file_path=pdf_path,
            quality="balanced",
        )
        store.create(job)

        # Mock processor that returns a failed result
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "OCR backend unavailable"

        mock_processor = MagicMock()
        mock_processor.extract.return_value = mock_result
        mock_get_processor = MagicMock(return_value=mock_processor)

        process_job(job, store, mock_get_processor)

        updated = store.get("fail-test")
        assert updated is not None
        assert updated.status == JobStatus.FAILED
        assert updated.error == "OCR backend unavailable"

    def test_exception_during_processing(self, create_text_pdf):
        """Job handles unexpected exceptions gracefully."""
        pdf_path = create_text_pdf()
        store = InMemoryJobStore()
        job = Job(
            job_id="exception-test",
            file_name="test.pdf",
            file_path=pdf_path,
            quality="fast",
        )
        store.create(job)

        mock_processor = MagicMock()
        mock_processor.extract.side_effect = RuntimeError("Unexpected crash")
        mock_get_processor = MagicMock(return_value=mock_processor)

        process_job(job, store, mock_get_processor)

        updated = store.get("exception-test")
        assert updated is not None
        assert updated.status == JobStatus.FAILED
        assert "Unexpected crash" in (updated.error or "")

    def test_temp_file_cleanup(self, tmp_path):
        """Temp file is cleaned up after processing."""
        temp_file = tmp_path / "cleanup.pdf"
        temp_file.write_text("dummy")

        store = InMemoryJobStore()
        job = Job(
            job_id="cleanup-test",
            file_name="cleanup.pdf",
            file_path=temp_file,
            quality="fast",
        )
        store.create(job)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.file_name = "cleanup.pdf"
        mock_result.pdf_type = "PURE_TEXT"
        mock_result.total_pages = 1
        mock_result.text = "text"
        mock_result.word_count = 1
        mock_result.confidence = 1.0
        mock_result.processing_time_ms = 50.0
        mock_result.extraction_method = "direct"
        mock_result.backend_status = None
        mock_result.page_errors = []

        mock_processor = MagicMock()
        mock_processor.extract.return_value = mock_result
        mock_get_processor = MagicMock(return_value=mock_processor)

        process_job(job, store, mock_get_processor)

        assert not temp_file.exists()


# =============================================================================
# TestJobStatusEnum
# =============================================================================


@pytest.mark.unit
class TestJobStatusEnum:
    """Test JobStatus enum values."""

    def test_status_values(self):
        """All expected status values exist."""
        assert JobStatus.PENDING == "pending"
        assert JobStatus.PROCESSING == "processing"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"

    def test_status_is_string(self):
        """Status values serialize as strings."""
        assert str(JobStatus.COMPLETED) == "JobStatus.COMPLETED"
        assert JobStatus.COMPLETED.value == "completed"
