# Text Extraction Service - Comprehensive Testing Strategy

## Executive Summary

This document defines the complete testing strategy for the text-extraction-service,
ensuring **100% regression compatibility** with the original list-eingangsrechnungen
implementation (42/42 PDFs success rate).

**Testing Philosophy:**
- No mocking of real APIs in integration tests (per CLAUDE.md guidelines)
- Real PDF fixtures for all scenarios
- Performance benchmarks as acceptance criteria
- Edge case coverage for production reliability

---

## Test Categories Overview

| Category | Scope | Target Coverage | Execution Time |
|----------|-------|-----------------|----------------|
| Unit Tests | Individual functions/classes | 95%+ | < 30s |
| Integration Tests | Component interactions | 90%+ | < 5min |
| End-to-End Tests | Full pipeline | 100% critical paths | < 10min |
| Performance Tests | Benchmarks | All targets met | < 2min |
| Regression Tests | Original 42 PDFs | 100% | Variable |

---

## 1. Unit Tests

### 1.1 PDFTypeDetector (`test_detector.py`)

**Test Scenarios:**

| Test ID | Scenario | Input | Expected Output | Priority |
|---------|----------|-------|-----------------|----------|
| DET-001 | Pure text PDF classification | Text-only PDF | `PDFType.PURE_TEXT` | High |
| DET-002 | Pure image PDF classification | Scanned PDF | `PDFType.PURE_IMAGE` | High |
| DET-003 | Hybrid PDF classification | Mixed PDF | `PDFType.HYBRID` | High |
| DET-004 | Empty PDF handling | 0-page PDF | `PDFType.UNKNOWN`, confidence=0 | High |
| DET-005 | Page analysis accuracy | Multi-page PDF | Correct page lists | High |
| DET-006 | Confidence calculation | Various PDFs | 0.0-1.0 range | Medium |
| DET-007 | Custom threshold behavior | Modified thresholds | Adjusted classification | Medium |
| DET-008 | File not found error | Invalid path | `FileNotFoundError` | High |
| DET-009 | Corrupted PDF handling | Malformed PDF | Graceful error | High |
| DET-010 | Large PDF (100+ pages) | Stress test | Completes < 5s | Medium |

**Acceptance Criteria:**
- All page classifications match manual inspection
- Confidence scores mathematically correct
- Error handling graceful, never crashes

### 1.2 BaseOCRBackend (`test_backends_base.py`)

**Test Scenarios:**

| Test ID | Scenario | Input | Expected Output | Priority |
|---------|----------|-------|-----------------|----------|
| BKD-001 | OCRResult word count | Text string | Correct count | Medium |
| BKD-002 | DocumentOCRResult full_text | Multiple pages | Concatenated text | Medium |
| BKD-003 | Backend unavailable check | No config | `is_available() = False` | High |
| BKD-004 | Supported formats list | Default backend | Standard formats | Low |
| BKD-005 | Page number extraction | PDF file | Correct count | Medium |
| BKD-006 | Image page detection | PNG file | Returns [1] | Medium |

### 1.3 JSON Repair (`test_json_repair.py`)

**Test Scenarios:**

| Test ID | Scenario | Input | Expected Output | Priority |
|---------|----------|-------|-----------------|----------|
| JSN-001 | Valid JSON passthrough | Valid JSON | Parsed dict, `was_repaired=False` | High |
| JSN-002 | Missing comma repair | `}  "key"` pattern | Repaired JSON | High |
| JSN-003 | Trailing comma removal | `{"key": "val",}` | Valid JSON | High |
| JSN-004 | Position-based comma fix | Error at line:col | Comma inserted | High |
| JSN-005 | Multiple repair attempts | Complex broken JSON | Best-effort repair | Medium |
| JSN-006 | Invoice structure validation | Invoice JSON | True/False | High |
| JSN-007 | Missing required keys | Incomplete JSON | `validate=False` | High |
| JSN-008 | Non-list line_items | `{"line_items": {}}` | `validate=False` | Medium |

**Edge Cases:**
- Deeply nested JSON with errors
- Unicode characters in strings
- Very long strings (10KB+)
- Empty JSON `{}`

---

## 2. Integration Tests

### 2.1 PDF Processing Pipeline (`test_integration_pipeline.py`)

**Test Scenarios:**

| Test ID | Scenario | Components Involved | Expected Result |
|---------|----------|---------------------|-----------------|
| INT-001 | Text PDF full extraction | Detector + Direct | Text extracted < 2s |
| INT-002 | Scanned PDF OCR | Detector + Backend | OCR text accurate |
| INT-003 | Hybrid PDF routing | Detector + Router | Correct page routing |
| INT-004 | Backend fallback | Primary fail + Fallback | Graceful degradation |
| INT-005 | Two-pass OCR flow | Processor full cycle | Context injected |

### 2.2 Backend Integration (`test_integration_backends.py`)

**Langdock Backend (requires API key):**

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| LDK-001 | File upload | `attachmentId` returned |
| LDK-002 | OCR extraction | Text extracted |
| LDK-003 | Rate limit handling | Retry with backoff |
| LDK-004 | Timeout handling | Graceful timeout |
| LDK-005 | Invalid API key | Clear error message |

**Tesseract Backend (requires tesseract installed):**

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| TES-001 | PDF to image conversion | Images generated |
| TES-002 | German text recognition | Correct extraction |
| TES-003 | Multi-language support | Both languages work |
| TES-004 | Image file OCR | Direct extraction |

---

## 3. Edge Case Tests

### 3.1 Input Validation (`test_edge_cases_input.py`)

| Test ID | Scenario | Input | Expected Behavior |
|---------|----------|-------|-------------------|
| EDG-001 | Empty file | 0 bytes | Error: empty file |
| EDG-002 | Non-PDF binary | Random bytes | Error: invalid format |
| EDG-003 | Password-protected PDF | Encrypted PDF | Error: encrypted |
| EDG-004 | PDF with no pages | Valid but empty | UNKNOWN type |
| EDG-005 | Extremely large file | 100MB PDF | Memory handling |
| EDG-006 | Special characters in path | `path/with spaces/file.pdf` | Works correctly |
| EDG-007 | Unicode filename | `rechnung_januar.pdf` | Works correctly |
| EDG-008 | Symlink to PDF | Symbolic link | Resolves correctly |
| EDG-009 | Read-only file | No write perms | Extraction works |
| EDG-010 | Network path | `//server/share/file.pdf` | Timeout handling |

### 3.2 Content Edge Cases (`test_edge_cases_content.py`)

| Test ID | Scenario | Content | Expected Behavior |
|---------|----------|---------|-------------------|
| CNT-001 | All-whitespace text | Spaces only | Low confidence |
| CNT-002 | Single character per page | Minimal text | Classified correctly |
| CNT-003 | Rotated pages | 90/180/270 degrees | OCR handles rotation |
| CNT-004 | Multi-column layout | Complex layout | Text order preserved |
| CNT-005 | Embedded forms | Fillable PDF | Form data extracted |
| CNT-006 | Tables | Tabular data | Structure preserved |
| CNT-007 | Handwritten text | Handwriting | OCR attempts extraction |
| CNT-008 | Mixed DPI images | Variable quality | Best-effort OCR |
| CNT-009 | Watermarked pages | Background image | Main text extracted |
| CNT-010 | Inverted colors | White on black | OCR handles inversion |

### 3.3 Multi-Language Tests (`test_edge_cases_language.py`)

| Test ID | Language | Test Content | Expected Result |
|---------|----------|--------------|-----------------|
| LNG-001 | German (primary) | Invoice text | High accuracy |
| LNG-002 | English | Invoice text | High accuracy |
| LNG-003 | German + English | Mixed document | Both recognized |
| LNG-004 | French | Invoice text | Reasonable accuracy |
| LNG-005 | Special chars | Umlauts, etc | Correct encoding |

---

## 4. Regression Tests

### 4.1 Original 42 PDF Test Suite (`test_regression_original.py`)

**Objective:** Ensure 100% compatibility with original list-eingangsrechnungen results.

**Test Structure:**
```python
@pytest.mark.regression
@pytest.mark.parametrize("pdf_fixture", ORIGINAL_42_PDFS)
def test_original_pdf_classification(pdf_fixture):
    """Verify classification matches original implementation."""
    result = detector.classify_pdf(pdf_fixture.path)
    assert result.pdf_type == pdf_fixture.expected_type
    assert abs(result.confidence - pdf_fixture.expected_confidence) < 0.05

@pytest.mark.regression
@pytest.mark.parametrize("pdf_fixture", ORIGINAL_42_PDFS)
def test_original_pdf_extraction(pdf_fixture):
    """Verify extraction matches original output."""
    result = processor.process(pdf_fixture.path)
    assert result.success == True
    assert similarity(result.text, pdf_fixture.expected_text) > 0.95
```

**Acceptance Criteria:**
- 42/42 PDFs must pass (100% success rate)
- Classification must match original
- Extraction quality >= 95% similarity

### 4.2 Regression Guard (`test_regression_guard.py`)

| Test ID | Guard Condition | Trigger |
|---------|-----------------|---------|
| RGR-001 | No accuracy drop | Any commit |
| RGR-002 | No new failures | Any commit |
| RGR-003 | Performance stable | Any commit |

---

## 5. Performance Benchmarks

### 5.1 Performance Targets (`test_performance.py`)

| Test ID | Scenario | Target | Measurement |
|---------|----------|--------|-------------|
| PRF-001 | Text PDF classification | < 100ms | `timeit` |
| PRF-002 | Text PDF extraction | < 2s | `timeit` |
| PRF-003 | Scanned PDF (1 page) | < 10s | `timeit` |
| PRF-004 | Scanned PDF (5 pages) | < 30s | `timeit` |
| PRF-005 | Hybrid PDF routing | < 500ms | `timeit` |
| PRF-006 | JSON repair (10KB) | < 50ms | `timeit` |
| PRF-007 | Memory usage (50MB PDF) | < 500MB | `tracemalloc` |
| PRF-008 | Concurrent processing (5x) | Linear scaling | `asyncio` |

**Benchmark Implementation:**
```python
@pytest.mark.performance
def test_text_pdf_extraction_time(text_pdf_fixture, benchmark):
    """Text PDF extraction must complete under 2 seconds."""
    result = benchmark(detector.classify_pdf, text_pdf_fixture)
    assert benchmark.stats['mean'] < 2.0

@pytest.mark.performance
def test_scanned_pdf_extraction_time(scanned_pdf_fixture, benchmark):
    """Scanned PDF OCR must complete under 30 seconds."""
    result = benchmark(processor.process, scanned_pdf_fixture)
    assert benchmark.stats['mean'] < 30.0
```

---

## 6. API Tests (FastAPI Service)

### 6.1 Endpoint Tests (`test_api_endpoints.py`)

| Test ID | Endpoint | Method | Expected Status |
|---------|----------|--------|-----------------|
| API-001 | `/api/v1/health` | GET | 200 |
| API-002 | `/api/v1/extract` | POST | 200/202 |
| API-003 | `/api/v1/extract` | POST (no file) | 400 |
| API-004 | `/api/v1/extract` | POST (invalid file) | 422 |
| API-005 | `/api/v1/extract/async` | POST | 202 |
| API-006 | `/api/v1/jobs/{id}` | GET | 200/404 |
| API-007 | `/api/v1/jobs/{id}/result` | GET | 200/202/404 |

### 6.2 API Contract Tests (`test_api_contract.py`)

| Test ID | Contract Check | Validation |
|---------|----------------|------------|
| CON-001 | Response schema | JSON Schema validation |
| CON-002 | Error format | Standard error structure |
| CON-003 | Content-Type | `application/json` |
| CON-004 | CORS headers | Proper CORS config |

---

## 7. Test Fixtures

### 7.1 PDF Fixtures Required

```
tests/fixtures/
|-- pdfs/
|   |-- text_simple.pdf          # Simple text-only PDF
|   |-- text_multipage.pdf       # 10-page text PDF
|   |-- text_german.pdf          # German language text
|   |-- scanned_single.pdf       # Single scanned page
|   |-- scanned_multi.pdf        # Multi-page scanned
|   |-- hybrid_basic.pdf         # Basic hybrid (1 text, 1 scan)
|   |-- hybrid_complex.pdf       # Complex hybrid (interleaved)
|   |-- empty.pdf                # Empty PDF (0 pages)
|   |-- corrupted.pdf            # Malformed PDF
|   |-- large_100pages.pdf       # 100-page stress test
|   |-- encrypted.pdf            # Password-protected
|   |-- rotated_90.pdf           # Rotated pages
|   |-- unicode_content.pdf      # Special characters
|
|-- images/
|   |-- invoice_scan.png         # Scanned invoice image
|   |-- low_quality.jpg          # Low DPI image
|   |-- high_quality.tiff        # High DPI image
|
|-- expected/
|   |-- text_simple_result.json  # Expected output for text_simple.pdf
|   |-- scanned_single_result.json
|   # ... etc
```

### 7.2 Mock Data Fixtures

```python
# tests/conftest.py

@pytest.fixture
def sample_ocr_response():
    """Sample Langdock API response structure."""
    return {
        "result": [{
            "role": "assistant",
            "content": [{"type": "text", "text": "Extracted text..."}]
        }]
    }

@pytest.fixture
def sample_classification_result():
    """Sample PDFClassificationResult."""
    return PDFClassificationResult(
        pdf_type=PDFType.HYBRID,
        total_pages=3,
        text_pages=[1],
        image_pages=[2, 3],
        confidence=0.85
    )
```

---

## 8. Test Execution Commands

### 8.1 Basic Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/text_extraction --cov-report=html --cov-report=term-missing

# Run specific category
pytest -m unit
pytest -m integration
pytest -m performance
pytest -m regression

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_detector.py

# Run specific test function
pytest tests/unit/test_detector.py::test_pure_text_classification
```

### 8.2 CI/CD Pipeline Commands

```bash
# Fast checks (pre-commit)
pytest -m "unit and not slow" --tb=short

# Full test suite (CI)
pytest --cov=src/text_extraction --cov-fail-under=90

# Integration tests (with API keys)
pytest -m integration --tb=long

# Performance benchmarks
pytest -m performance --benchmark-only --benchmark-json=benchmark.json
```

---

## 9. Coverage Targets

| Module | Target Coverage | Critical Paths |
|--------|-----------------|----------------|
| `detector.py` | 95% | `classify_pdf`, `analyze_page` |
| `backends/base.py` | 90% | `extract_document` |
| `backends/langdock.py` | 85% | API calls, response parsing |
| `backends/tesseract.py` | 85% | Image conversion, OCR |
| `json_repair.py` | 95% | All repair strategies |
| `router.py` | 90% | Routing decisions |
| `processor.py` | 90% | Two-pass flow |
| **Overall** | **90%** | |

---

## 10. Acceptance Criteria by Phase

### Phase 1: Foundation (detector.py, base.py, json_repair.py)

- [ ] Unit tests for PDFTypeDetector: 15+ test cases
- [ ] Unit tests for BaseOCRBackend: 10+ test cases
- [ ] Unit tests for json_repair: 10+ test cases
- [ ] All tests pass (100%)
- [ ] Coverage >= 95% for these modules
- [ ] No regressions in existing behavior

### Phase 2: Backends (langdock.py, tesseract.py)

- [ ] Unit tests with mocked responses: 10+ per backend
- [ ] Integration tests with real APIs: 5+ per backend
- [ ] Error handling tests: 5+ per backend
- [ ] Performance within targets

### Phase 3: Router & Processor

- [ ] Unit tests for routing logic: 10+ test cases
- [ ] Integration tests for full pipeline: 5+ scenarios
- [ ] Two-pass OCR flow verified
- [ ] Hybrid PDF handling correct

### Phase 4: Regression & Performance

- [ ] All 42 original PDFs pass
- [ ] Performance benchmarks met
- [ ] Memory usage within limits
- [ ] Concurrent processing stable

### Phase 5: API Service (if implemented)

- [ ] All endpoints tested: 7+ test cases
- [ ] Contract validation passing
- [ ] Error responses correct
- [ ] Authentication working

---

## 11. Test Naming Convention

```
test_<component>_<scenario>_<expected_outcome>

Examples:
- test_detector_pure_text_pdf_returns_pure_text_type
- test_langdock_upload_invalid_file_raises_error
- test_json_repair_missing_comma_repairs_successfully
- test_router_hybrid_pdf_routes_pages_correctly
```

---

## 12. CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: pip install -e ".[dev]"
      - run: pytest -m unit --cov=src/text_extraction --cov-fail-under=90

  integration-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    env:
      LANGDOCK_API_KEY: ${{ secrets.LANGDOCK_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[all]"
      - run: pytest -m integration

  performance-benchmarks:
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[dev]"
      - run: pytest -m performance --benchmark-json=benchmark.json
      - uses: benchmark-action/github-action-benchmark@v1
```

---

*Document Version: 1.0*
*Created: 2026-01-07*
*Author: QA Engineering (Claude Code)*
