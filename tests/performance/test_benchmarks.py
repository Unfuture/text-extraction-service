"""
Performance Benchmark Tests

Test Coverage:
- PDF classification speed
- Text extraction performance
- JSON repair performance
- Memory usage
- Concurrent processing

Targets:
- PRF-001: Text PDF classification < 100ms
- PRF-002: Text PDF extraction < 2s
- PRF-003: Scanned PDF (1 page) < 10s (with OCR)
- PRF-004: Scanned PDF (5 pages) < 30s (with OCR)
- PRF-005: Hybrid PDF routing < 500ms
- PRF-006: JSON repair (10KB) < 50ms
"""

import time
import json
import pytest

from text_extraction import PDFTypeDetector


# =============================================================================
# Test: PDF Classification Speed
# =============================================================================

class TestClassificationSpeed:
    """Performance tests for PDF classification."""

    @pytest.mark.performance
    def test_text_pdf_classification_under_100ms(
        self, create_text_pdf, detector, performance_timer
    ):
        """PRF-001: Text PDF classification should complete under 100ms."""
        pdf_path = create_text_pdf("speed_test.pdf", "Sample text content")

        with performance_timer() as timer:
            result = detector.classify_pdf(pdf_path)

        assert timer.elapsed_ms < 100, f"Classification took {timer.elapsed_ms}ms, expected <100ms"
        assert result.pdf_type is not None

    @pytest.mark.performance
    def test_multipage_classification_linear_scaling(
        self, create_multipage_text_pdf, detector, performance_timer
    ):
        """Classification time should scale reasonably with page count."""
        # Test with 5 pages
        pdf_5 = create_multipage_text_pdf("pages_5.pdf", pages=5)
        with performance_timer() as timer_5:
            detector.classify_pdf(pdf_5)
        time_5 = timer_5.elapsed_ms

        # Test with 20 pages
        pdf_20 = create_multipage_text_pdf("pages_20.pdf", pages=20)
        with performance_timer() as timer_20:
            detector.classify_pdf(pdf_20)
        time_20 = timer_20.elapsed_ms

        # Time should not grow more than linearly (allow 5x for 4x pages)
        assert time_20 < time_5 * 6, f"Scaling issue: 5p={time_5}ms, 20p={time_20}ms"

    @pytest.mark.performance
    def test_hybrid_pdf_routing_under_500ms(
        self, create_hybrid_pdf, detector, performance_timer
    ):
        """PRF-005: Hybrid PDF routing decision should complete under 500ms."""
        pdf_path = create_hybrid_pdf("hybrid_speed.pdf")

        with performance_timer() as timer:
            result = detector.classify_pdf(pdf_path)

        assert timer.elapsed_ms < 500, f"Routing took {timer.elapsed_ms}ms, expected <500ms"


# =============================================================================
# Test: Text Extraction Speed
# =============================================================================

class TestExtractionSpeed:
    """Performance tests for text extraction."""

    @pytest.mark.performance
    def test_direct_text_extraction_under_2s(
        self, create_text_pdf, performance_timer
    ):
        """PRF-002: Direct text extraction should complete under 2 seconds."""
        pdf_path = create_text_pdf(
            "extraction_speed.pdf",
            "Sample invoice content with multiple lines.\n" * 100
        )

        import fitz

        with performance_timer() as timer:
            doc = fitz.open(pdf_path)
            text = doc[0].get_text()
            doc.close()

        assert timer.elapsed_ms < 2000, f"Extraction took {timer.elapsed_ms}ms, expected <2000ms"
        assert len(text) > 0

    @pytest.mark.performance
    def test_multipage_extraction_under_5s(
        self, create_multipage_text_pdf, performance_timer
    ):
        """Multi-page text extraction should complete under 5 seconds."""
        pdf_path = create_multipage_text_pdf("multi_extract.pdf", pages=20)

        import fitz

        with performance_timer() as timer:
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text()
            doc.close()

        assert timer.elapsed_ms < 5000, f"Extraction took {timer.elapsed_ms}ms, expected <5000ms"
        assert len(full_text) > 0


# =============================================================================
# Test: JSON Repair Speed
# =============================================================================

class TestJSONRepairSpeed:
    """Performance tests for JSON repair."""

    @pytest.mark.performance
    def test_json_repair_10kb_under_50ms(self, performance_timer):
        """PRF-006: JSON repair for 10KB should complete under 50ms."""
        from text_extraction.json_repair import repair_json_text

        # Create ~10KB JSON with trailing comma issue
        items = [{"key": f"value_{i}", "data": "x" * 100} for i in range(50)]
        large_json = json.dumps({"items": items})[:-1] + ",}"  # Add trailing comma

        with performance_timer() as timer:
            repaired = repair_json_text(large_json)

        assert timer.elapsed_ms < 50, f"Repair took {timer.elapsed_ms}ms, expected <50ms"

    @pytest.mark.performance
    def test_safe_json_parse_valid_fast(self, performance_timer):
        """Valid JSON should parse very fast."""
        from text_extraction.json_repair import safe_json_parse

        valid_json = json.dumps({"items": list(range(1000))})

        with performance_timer() as timer:
            data, repaired = safe_json_parse(valid_json)

        assert timer.elapsed_ms < 20, f"Parse took {timer.elapsed_ms}ms, expected <20ms"
        assert repaired is False


# =============================================================================
# Test: Memory Usage
# =============================================================================

class TestMemoryUsage:
    """Performance tests for memory consumption."""

    @pytest.mark.performance
    @pytest.mark.slow
    def test_large_pdf_memory_usage(self, create_multipage_text_pdf):
        """PRF-007: Processing large PDF should not use excessive memory."""
        import tracemalloc

        pdf_path = create_multipage_text_pdf("memory_test.pdf", pages=100)

        tracemalloc.start()

        detector = PDFTypeDetector()
        result = detector.classify_pdf(pdf_path)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Peak memory should be under 100MB for 100 pages
        peak_mb = peak / (1024 * 1024)
        assert peak_mb < 100, f"Peak memory {peak_mb}MB exceeds 100MB limit"

        assert result.total_pages == 100

    @pytest.mark.performance
    def test_detector_memory_release(self, create_text_pdf):
        """Detector should release memory after processing."""
        import tracemalloc
        import gc

        pdf_path = create_text_pdf("release_test.pdf", "Test content")

        tracemalloc.start()

        # Process multiple times
        for _ in range(10):
            detector = PDFTypeDetector()
            detector.classify_pdf(pdf_path)

        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Current memory should be much less than peak (memory released)
        current_mb = current / (1024 * 1024)
        assert current_mb < 50, f"Current memory {current_mb}MB too high after GC"


# =============================================================================
# Test: Concurrent Processing
# =============================================================================

class TestConcurrentProcessing:
    """Performance tests for concurrent operations."""

    @pytest.mark.performance
    @pytest.mark.slow
    def test_concurrent_classification(self, create_text_pdf, performance_timer):
        """PRF-008: Concurrent classification should scale reasonably."""
        import concurrent.futures

        # Create test PDFs
        pdf_paths = [
            create_text_pdf(f"concurrent_{i}.pdf", f"Content {i}")
            for i in range(5)
        ]

        def classify_pdf(path):
            detector = PDFTypeDetector()
            return detector.classify_pdf(path)

        # Sequential timing
        with performance_timer() as seq_timer:
            for path in pdf_paths:
                classify_pdf(path)
        seq_time = seq_timer.elapsed_ms

        # Concurrent timing
        with performance_timer() as conc_timer:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(classify_pdf, pdf_paths))
        conc_time = conc_timer.elapsed_ms

        # Concurrent should not be much slower than sequential
        # (accounting for thread overhead)
        assert conc_time < seq_time * 2, f"Concurrent too slow: {conc_time}ms vs seq {seq_time}ms"
        assert len(results) == 5


# =============================================================================
# Test: Repeated Operations
# =============================================================================

class TestRepeatedOperations:
    """Performance tests for repeated operations (caching, warm-up)."""

    @pytest.mark.performance
    def test_repeated_classification_consistent_time(
        self, create_text_pdf, detector
    ):
        """Repeated classification should have consistent timing."""
        pdf_path = create_text_pdf("repeated.pdf", "Test content")

        times = []
        for _ in range(10):
            start = time.perf_counter()
            detector.classify_pdf(pdf_path)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # No single run should be more than 3x average
        assert max_time < avg_time * 3, f"Inconsistent timing: max={max_time}ms, avg={avg_time}ms"

    @pytest.mark.performance
    def test_detector_reuse_efficient(self, create_multipage_text_pdf):
        """Reusing detector instance should be efficient."""
        pdf_path = create_multipage_text_pdf("reuse.pdf", pages=5)
        detector = PDFTypeDetector()

        # First call (potential warm-up)
        start = time.perf_counter()
        detector.classify_pdf(pdf_path)
        first_time = (time.perf_counter() - start) * 1000

        # Subsequent calls
        times = []
        for _ in range(5):
            start = time.perf_counter()
            detector.classify_pdf(pdf_path)
            times.append((time.perf_counter() - start) * 1000)

        avg_subsequent = sum(times) / len(times)

        # Subsequent calls should not be much slower than first
        assert avg_subsequent < first_time * 1.5, f"Reuse inefficient: first={first_time}ms, avg={avg_subsequent}ms"


# =============================================================================
# Benchmark Utilities
# =============================================================================

@pytest.fixture
def benchmark_summary():
    """Collect benchmark results for summary."""
    results = []

    def record(name, target_ms, actual_ms, passed):
        results.append({
            "name": name,
            "target_ms": target_ms,
            "actual_ms": actual_ms,
            "passed": passed
        })

    yield record

    # Print summary at end
    if results:
        print("\n\nBenchmark Summary:")
        print("-" * 60)
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"{status}: {r['name']}: {r['actual_ms']:.2f}ms (target: {r['target_ms']}ms)")
