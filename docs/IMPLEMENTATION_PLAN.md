# Text Extraction Service - Implementation Plan

## Executive Summary

This document outlines the phased implementation plan for the Text Extraction Service based on the architecture design in `TEXT_EXTRACTION_SERVICE_ARCHITECTURE.md`. We adopt **Option 3: Library Package + Service** as recommended.

**Current State Analysis:**
- `detector.py` (354 lines): PDF Type Detection - READY
- `backends/base.py` (214 lines): Abstract OCR backend - READY
- `json_repair.py` (271 lines): JSON error recovery - READY
- Total implemented: ~839 lines (3 core modules)
- Total remaining: ~1,000+ lines across 8+ modules

**Estimated Total Effort:** 136 hours (3.25 weeks)

---

## Component Dependency Graph

```
                                    +-------------------+
                                    |    __init__.py    |
                                    |   Public API      |
                                    +--------+----------+
                                             |
              +------------------------------+------------------------------+
              |                              |                              |
    +---------v----------+      +-----------v-----------+      +-----------v----------+
    |   detector.py      |      |     router.py         |      |    processor.py      |
    |   PDFTypeDetector  |      |   ContentRouter       |      |  TwoPassProcessor    |
    |   [READY]          |      |   [TODO]              |      |  [TODO]              |
    +---------+----------+      +-----------+-----------+      +-----------+----------+
              |                             |                              |
              |                             |                              |
              +-----------------------------+------------------------------+
                                            |
                      +---------------------+---------------------+
                      |                     |                     |
            +---------v--------+  +---------v--------+  +---------v--------+
            | backends/        |  | backends/        |  | backends/        |
            | langdock.py      |  | tesseract.py     |  | cloud_vision.py  |
            | [TODO]           |  | [TODO]           |  | [OPTIONAL]       |
            +------------------+  +------------------+  +------------------+
                      |                     |                     |
                      +---------------------+---------------------+
                                            |
                               +------------v------------+
                               |   backends/base.py     |
                               |   BaseOCRBackend       |
                               |   [READY]              |
                               +-------------------------+

            +-----------------+
            |   models/       |
            +-----------------+
            | config.py       | <-- Configuration dataclasses
            | extraction.py   | <-- Result types (extends base.py)
            +-----------------+

            +-----------------+
            |   utils/        |
            +-----------------+
            | json_repair.py  | <-- [READY]
            | validation.py   | <-- File validation [TODO]
            +-----------------+

            +--------------------+
            |   service/         | <-- Optional FastAPI wrapper
            +--------------------+
            | app.py             |
            | routes.py          |
            | worker.py          |
            +--------------------+
```

---

## Implementation Phases

### Phase 1: Core Models and Configuration (16h)

**Goal:** Establish data models and configuration system for all components.

#### 1.1 Models Package (`src/text_extraction/models/`)

**File: `models/__init__.py`**
```python
from .config import BackendConfig, ProcessorConfig, ExtractionOptions
from .extraction import ExtractionResult, PageResult, DocumentResult
```

**File: `models/config.py`** (NEW - ~120 lines)
```python
@dataclass
class BackendConfig:
    """Configuration for OCR backends."""
    api_key: Optional[str] = None
    model: str = "claude-sonnet-4-5"
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: int = 120
    retry_attempts: int = 3

@dataclass
class ProcessorConfig:
    """Configuration for text extraction processor."""
    text_threshold: int = 10
    enable_two_pass: bool = True
    confidence_threshold: float = 0.8
    fallback_on_error: bool = True
    cleanup_temp_files: bool = True

@dataclass
class ExtractionOptions:
    """Options for extraction request."""
    backend: str = "auto"  # auto, langdock, tesseract
    language: str = "deu"
    output_format: str = "structured"  # text, structured, markdown
    include_confidence: bool = True
    gdpr_mode: bool = False
```

**File: `models/extraction.py`** (NEW - ~150 lines)
```python
@dataclass
class PageResult:
    """Result for single page extraction."""
    page_number: int
    text: str
    confidence: float
    method: ExtractionMethod
    word_count: int = 0
    processing_time_ms: float = 0.0
    bounding_boxes: Optional[List[BoundingBox]] = None

@dataclass
class ExtractionResult:
    """Complete extraction result for a document."""
    success: bool
    file_name: str
    pdf_type: PDFType
    pages: List[PageResult]
    full_text: str
    metadata: ExtractionMetadata
    error: Optional[str] = None

@dataclass
class ExtractionMetadata:
    """Metadata about extraction process."""
    backend_used: str
    processing_time_ms: float
    ocr_passes: int
    model_used: str
    pages_processed: int
    confidence_score: float
    two_pass_used: bool = False
    scanned_pages: List[int] = field(default_factory=list)
```

**Deliverables:**
- [ ] `models/__init__.py`
- [ ] `models/config.py` with BackendConfig, ProcessorConfig, ExtractionOptions
- [ ] `models/extraction.py` with PageResult, ExtractionResult, ExtractionMetadata
- [ ] Unit tests for all model classes

**Dependencies:** None (foundation layer)

---

### Phase 2: Langdock Backend (24h)

**Goal:** Implement primary LLM-based OCR backend using Langdock API.

#### 2.1 Langdock Backend (`src/text_extraction/backends/langdock.py`)

**Reference:** `examples/langdock_inline_client_original.py`

**File: `backends/langdock.py`** (NEW - ~250 lines)
```python
class LangdockBackend(BaseOCRBackend):
    """
    LLM-based OCR backend using Langdock API.

    Supports:
    - Claude Sonnet 4.5 for OCR extraction
    - GPT-4o for analysis
    - Inline assistant creation per request
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[BackendConfig] = None
    ):
        super().__init__(name="Langdock")
        self.api_key = api_key or os.getenv("LANGDOCK_API_KEY")
        self.config = config or BackendConfig()
        self.upload_url = os.getenv("LANGDOCK_UPLOAD_URL")
        self.completions_url = "https://api.langdock.com/assistant/v1/chat/completions"

    def is_available(self) -> bool:
        """Check if Langdock API is configured and reachable."""
        return bool(self.api_key and self.upload_url)

    def extract_text(
        self,
        file_path: Path,
        page_number: Optional[int] = None,
        **kwargs
    ) -> OCRResult:
        """Extract text using Langdock LLM OCR."""
        # Implementation based on langdock_inline_client_original.py
        pass

    def _upload_file(self, file_path: Path) -> str:
        """Upload file to Langdock, return attachment ID."""
        pass

    def _make_api_call(
        self,
        attachment_id: str,
        prompt: str,
        timeout: int = 120
    ) -> Dict[str, Any]:
        """Make completion API call with inline assistant."""
        pass

    def _parse_response(self, response: Dict[str, Any]) -> str:
        """Extract text from API response."""
        pass
```

**Deliverables:**
- [ ] `backends/langdock.py` with full implementation
- [ ] Integration tests with mocked API
- [ ] Real API integration test (marked as `@pytest.mark.integration`)

**Dependencies:** Phase 1 (models/config.py)

---

### Phase 3: Tesseract Backend (16h)

**Goal:** Implement local OCR fallback using Tesseract.

#### 3.1 Tesseract Backend (`src/text_extraction/backends/tesseract.py`)

**File: `backends/tesseract.py`** (NEW - ~180 lines)
```python
class TesseractBackend(BaseOCRBackend):
    """
    Local OCR backend using Tesseract.

    Used as fallback when:
    - Langdock API is unavailable
    - Cost optimization is needed
    - Offline processing is required
    """

    def __init__(
        self,
        tesseract_path: Optional[str] = None,
        language: str = "deu+eng",
        config: Optional[BackendConfig] = None
    ):
        super().__init__(name="Tesseract")
        self.tesseract_path = tesseract_path or os.getenv("TESSERACT_PATH", "tesseract")
        self.language = language
        self.config = config or BackendConfig()

    def is_available(self) -> bool:
        """Check if Tesseract is installed and accessible."""
        try:
            import pytesseract
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
        """Extract text using Tesseract OCR."""
        pass

    def _convert_pdf_to_images(self, pdf_path: Path) -> List[Path]:
        """Convert PDF pages to images for OCR."""
        pass
```

**Deliverables:**
- [ ] `backends/tesseract.py` with full implementation
- [ ] Unit tests with sample images
- [ ] Integration tests (requires Tesseract installed)

**Dependencies:** Phase 1 (models/config.py)

---

### Phase 4: Content Router (16h)

**Goal:** Implement intelligent routing based on PDF type detection.

#### 4.1 Content Router (`src/text_extraction/router.py`)

**File: `router.py`** (NEW - ~200 lines)
```python
class ContentRouter:
    """
    Intelligent content router that selects extraction strategy.

    Routing Logic:
    - PURE_TEXT: Direct PyMuPDF text extraction (fast, free)
    - PURE_IMAGE: LLM OCR for all pages (accurate but expensive)
    - HYBRID: Mixed strategy - direct for text pages, OCR for image pages
    """

    def __init__(
        self,
        primary_backend: BaseOCRBackend,
        fallback_backend: Optional[BaseOCRBackend] = None,
        detector: Optional[PDFTypeDetector] = None
    ):
        self.primary_backend = primary_backend
        self.fallback_backend = fallback_backend
        self.detector = detector or PDFTypeDetector()

    def route(self, file_path: Path) -> RoutingDecision:
        """
        Analyze file and determine extraction strategy.

        Returns:
            RoutingDecision with strategy and page assignments
        """
        pass

    def extract(
        self,
        file_path: Path,
        options: Optional[ExtractionOptions] = None
    ) -> ExtractionResult:
        """
        Extract text using optimal strategy.

        1. Detect PDF type
        2. Determine routing strategy
        3. Execute extraction with appropriate backend(s)
        4. Combine results
        """
        pass

    def _extract_direct(self, file_path: Path, pages: List[int]) -> List[PageResult]:
        """Extract text directly using PyMuPDF."""
        pass

    def _extract_with_backend(
        self,
        file_path: Path,
        pages: List[int],
        backend: BaseOCRBackend
    ) -> List[PageResult]:
        """Extract text using specified backend."""
        pass

@dataclass
class RoutingDecision:
    """Decision from content router."""
    pdf_type: PDFType
    strategy: str  # "direct", "ocr", "hybrid"
    direct_pages: List[int]
    ocr_pages: List[int]
    estimated_cost: float
    estimated_time_seconds: float
```

**Deliverables:**
- [ ] `router.py` with ContentRouter and RoutingDecision
- [ ] Unit tests for routing logic
- [ ] Integration tests with sample PDFs

**Dependencies:**
- Phase 1 (models)
- Phase 2 (langdock backend)
- Phase 3 (tesseract backend)
- `detector.py` (already ready)

---

### Phase 5: Two-Pass Processor (32h)

**Goal:** Implement the two-pass OCR strategy for scanned documents.

#### 5.1 Two-Pass Processor (`src/text_extraction/processor.py`)

**Reference:** `examples/two_pass_ocr_processor_original.py`

**File: `processor.py`** (NEW - ~350 lines)
```python
class TwoPassProcessor:
    """
    Advanced OCR processor using two-pass strategy.

    Pass 1: Extract text from scanned pages using OCR-specific prompt
    Pass 2: Analyze full document with OCR context injected

    This significantly improves recognition rate for scanned documents.
    """

    def __init__(
        self,
        ocr_backend: BaseOCRBackend,
        analysis_backend: Optional[BaseOCRBackend] = None,
        config: Optional[ProcessorConfig] = None
    ):
        self.ocr_backend = ocr_backend
        self.analysis_backend = analysis_backend or ocr_backend
        self.config = config or ProcessorConfig()
        self.detector = PDFTypeDetector()
        self._temp_dir: Optional[Path] = None

    async def process(
        self,
        file_path: Path,
        prompt: Optional[str] = None
    ) -> ProcessorResult:
        """
        Main entry point: Process document with two-pass strategy.

        Workflow:
        1. Detect PDF type and scanned pages
        2. If scanned pages: Run Pass 1 (OCR extraction)
        3. Run Pass 2 (analysis with OCR context)
        4. Return result with metadata
        """
        pass

    async def _pass_1_extract_text(
        self,
        file_path: Path,
        scanned_pages: List[int]
    ) -> Dict[int, str]:
        """Pass 1: Extract text from scanned pages."""
        pass

    async def _pass_2_analyze(
        self,
        file_path: Path,
        ocr_context: Dict[int, str],
        prompt: str
    ) -> Dict[str, Any]:
        """Pass 2: Analyze with OCR context."""
        pass

    def _split_page(self, pdf_path: Path, page_num: int) -> Path:
        """Extract single page to temporary file."""
        pass

    def _build_enhanced_prompt(
        self,
        base_prompt: str,
        ocr_context: Dict[int, str]
    ) -> str:
        """Build prompt with OCR context injection."""
        pass

    def _cleanup(self):
        """Clean up temporary files."""
        pass

@dataclass
class ProcessorResult:
    """Result from two-pass processor."""
    success: bool
    data: Dict[str, Any]
    extraction_result: ExtractionResult
    metadata: ProcessorMetadata
    error: Optional[str] = None

@dataclass
class ProcessorMetadata:
    """Metadata about processing."""
    used_two_pass: bool
    scanned_pages: List[int]
    total_pages: int
    ocr_model: str
    analysis_model: str
    pass_1_duration_seconds: float
    pass_2_duration_seconds: float
    total_duration_seconds: float
```

**Deliverables:**
- [ ] `processor.py` with TwoPassProcessor
- [ ] ProcessorResult and ProcessorMetadata dataclasses
- [ ] Unit tests with mocked backends
- [ ] Integration tests with real PDFs

**Dependencies:**
- Phase 1 (models)
- Phase 2 (langdock backend)
- Phase 4 (router)
- `detector.py` (ready)

---

### Phase 6: Public API and Package (16h)

**Goal:** Finalize public API, package structure, and documentation.

#### 6.1 Update `__init__.py`

**File: `__init__.py`** (UPDATE - ~80 lines)
```python
"""
Text Extraction Service - Public API
"""
from .detector import PDFType, PDFTypeDetector, PDFClassificationResult
from .router import ContentRouter, RoutingDecision
from .processor import TwoPassProcessor, ProcessorResult
from .backends import LangdockBackend, TesseractBackend, BaseOCRBackend
from .models import (
    BackendConfig,
    ProcessorConfig,
    ExtractionOptions,
    ExtractionResult,
    PageResult
)

# Convenience functions
def extract_text(file_path: str, **kwargs) -> ExtractionResult:
    """Quick extraction with default settings."""
    pass

def classify_pdf(file_path: str) -> PDFClassificationResult:
    """Quick PDF classification."""
    pass

__all__ = [
    # Core classes
    "PDFTypeDetector",
    "ContentRouter",
    "TwoPassProcessor",
    # Backends
    "LangdockBackend",
    "TesseractBackend",
    "BaseOCRBackend",
    # Models
    "BackendConfig",
    "ProcessorConfig",
    "ExtractionOptions",
    "ExtractionResult",
    "PageResult",
    # Enums
    "PDFType",
    # Functions
    "extract_text",
    "classify_pdf",
]
```

#### 6.2 Utils Package

**File: `utils/__init__.py`**
```python
from .json_repair import safe_json_parse, repair_json_text
from .validation import validate_file, is_supported_format
```

**File: `utils/validation.py`** (NEW - ~100 lines)
```python
SUPPORTED_FORMATS = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.heic', '.webp'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def validate_file(file_path: Path) -> ValidationResult:
    """Validate file for extraction."""
    pass

def is_supported_format(file_path: Path) -> bool:
    """Check if file format is supported."""
    pass

@dataclass
class ValidationResult:
    valid: bool
    mime_type: str
    file_size: int
    errors: List[str]
```

**Deliverables:**
- [ ] Updated `__init__.py` with full public API
- [ ] `utils/__init__.py`
- [ ] `utils/validation.py`
- [ ] Convenience functions `extract_text()` and `classify_pdf()`
- [ ] Package ready for pip install

**Dependencies:** Phases 1-5

---

### Phase 7: FastAPI Service (Optional - 24h)

**Goal:** Create REST API wrapper for non-Python consumers.

#### 7.1 Service Package (`service/`)

**File: `service/app.py`** (NEW - ~120 lines)
```python
from fastapi import FastAPI, File, UploadFile, HTTPException
from text_extraction import extract_text, classify_pdf

app = FastAPI(
    title="Text Extraction Service",
    version="1.0.0"
)

@app.post("/api/v1/extract")
async def extract(file: UploadFile = File(...), options: str = "{}"):
    """Synchronous text extraction."""
    pass

@app.post("/api/v1/extract/async")
async def extract_async(file: UploadFile = File(...)):
    """Start async extraction job."""
    pass

@app.get("/api/v1/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status."""
    pass

@app.get("/api/v1/health")
async def health():
    """Health check."""
    pass
```

**File: `service/routes.py`** (NEW - ~200 lines)
- Detailed route implementations
- Request/response schemas
- Error handling

**File: `service/worker.py`** (NEW - ~150 lines)
- Background job processing
- Queue integration (Redis)

**Deliverables:**
- [ ] `service/app.py` with FastAPI application
- [ ] `service/routes.py` with route implementations
- [ ] `service/worker.py` for async processing
- [ ] OpenAPI documentation generated
- [ ] Docker configuration

**Dependencies:** Phases 1-6 (complete library)

---

### Phase 8: Testing and Documentation (24h)

**Goal:** Comprehensive test coverage and documentation.

#### 8.1 Test Structure

```
tests/
+-- unit/
|   +-- test_detector.py       # PDFTypeDetector tests
|   +-- test_router.py         # ContentRouter tests
|   +-- test_processor.py      # TwoPassProcessor tests
|   +-- test_backends.py       # Backend tests
|   +-- test_models.py         # Model tests
|
+-- integration/
|   +-- test_langdock.py       # Real API tests
|   +-- test_tesseract.py      # Real OCR tests
|   +-- test_end_to_end.py     # Full pipeline tests
|
+-- fixtures/
|   +-- sample_text.pdf        # Pure text PDF
|   +-- sample_scanned.pdf     # Scanned PDF
|   +-- sample_hybrid.pdf      # Hybrid PDF
|   +-- sample_image.png       # Image file
```

#### 8.2 Documentation

```
docs/
+-- api.md                     # API reference
+-- quickstart.md              # Getting started guide
+-- backends.md                # Backend configuration
+-- migration.md               # Migration from list-eingangsrechnungen
```

**Deliverables:**
- [ ] Unit tests for all modules (90%+ coverage)
- [ ] Integration tests (marked appropriately)
- [ ] Sample fixture files
- [ ] API documentation
- [ ] Quickstart guide
- [ ] Migration guide

**Dependencies:** Phases 1-6

---

## Data Flow Diagrams

### 1. Simple Extraction Flow

```
User Request                    Library Components
    |
    v
+-------------------+
| extract_text()    |
+--------+----------+
         |
         v
+-------------------+
| PDFTypeDetector   |-----> Returns: PDFType, page classification
+--------+----------+
         |
         v
+-------------------+
| ContentRouter     |-----> Decides: direct vs OCR vs hybrid
+--------+----------+
         |
    +----+----+
    |         |
    v         v
+-------+  +----------+
| Direct|  | Backend  |
| (fitz)|  | (OCR)    |
+---+---+  +----+-----+
    |           |
    +-----+-----+
          |
          v
+-------------------+
| ExtractionResult  |-----> Returns to user
+-------------------+
```

### 2. Two-Pass OCR Flow

```
TwoPassProcessor.process(pdf_path, prompt)
         |
         v
+-------------------+
| 1. Detect Pages   |-----> classify_pdf() -> scanned_pages
+--------+----------+
         |
         v
+-------------------+
| 2. Pass 1: OCR    |-----> For each scanned page:
|    Extract Text   |       - Split page to temp PDF
+--------+----------+       - Send to OCR backend
         |                  - Collect extracted text
         v
+-------------------+
| 3. Build Context  |-----> ocr_context = {page: text, ...}
+--------+----------+
         |
         v
+-------------------+
| 4. Pass 2: Analyze|-----> enhanced_prompt = base + ocr_context
|    Full Document  |       Send full PDF + enhanced prompt
+--------+----------+
         |
         v
+-------------------+
| 5. Return Result  |-----> ProcessorResult with metadata
+-------------------+
```

### 3. REST API Flow

```
Client Request              FastAPI Service              Library
     |                           |                          |
     | POST /extract             |                          |
     +-------------------------->|                          |
     |                           |                          |
     |                           | validate_file()          |
     |                           +------------------------->|
     |                           |                          |
     |                           | extract_text()           |
     |                           +------------------------->|
     |                           |                          |
     |                           |<-------------------------+
     |                           | ExtractionResult         |
     |<--------------------------+                          |
     | JSON Response             |                          |
```

---

## Integration Points

### 1. Langdock API

```
Environment Variables:
- LANGDOCK_API_KEY: API authentication key
- LANGDOCK_UPLOAD_URL: File upload endpoint
- LANGDOCK_MODEL: Default model (claude-sonnet-4-5)

Endpoints:
- POST {LANGDOCK_UPLOAD_URL}: Upload PDF, returns attachmentId
- POST https://api.langdock.com/assistant/v1/chat/completions: Analysis
```

### 2. Tesseract

```
Environment Variables:
- TESSERACT_PATH: Path to tesseract binary (default: tesseract)
- TESSERACT_LANG: Language packs (default: deu+eng)

Requirements:
- tesseract-ocr system package
- pytesseract Python package
- Language data files (tessdata)
```

### 3. list-eingangsrechnungen Integration

```python
# Migration from direct code to library

# BEFORE (in list-eingangsrechnungen)
from pdf_type_detector import PDFTypeDetector
from two_pass_ocr_processor import TwoPassOCRProcessor
from langdock_inline_client import LangdockInlineClient

# AFTER (using library)
from text_extraction import (
    TwoPassProcessor,
    LangdockBackend,
    ProcessorConfig
)

# Usage remains similar
backend = LangdockBackend(api_key=os.getenv("LANGDOCK_API_KEY"))
processor = TwoPassProcessor(ocr_backend=backend)
result = await processor.process(pdf_path, prompt)
```

---

## Milestone Checklist

### Milestone 1: Foundation (Week 1)
- [ ] Phase 1 complete: Models and configuration
- [ ] Phase 2 complete: Langdock backend
- [ ] Basic tests passing

### Milestone 2: Core Features (Week 2)
- [ ] Phase 3 complete: Tesseract backend
- [ ] Phase 4 complete: Content router
- [ ] Integration tests passing

### Milestone 3: Two-Pass OCR (Week 2.5)
- [ ] Phase 5 complete: TwoPassProcessor
- [ ] End-to-end tests passing
- [ ] Parity with original implementation

### Milestone 4: Release Ready (Week 3)
- [ ] Phase 6 complete: Public API finalized
- [ ] Phase 8 complete: Documentation
- [ ] Package installable via pip

### Milestone 5: Service (Week 3.5 - Optional)
- [ ] Phase 7 complete: FastAPI service
- [ ] Docker image ready
- [ ] API documentation generated

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Langdock API changes | High | Abstract behind interface, version pin |
| Tesseract accuracy issues | Medium | Fallback to LLM OCR |
| Large file performance | Medium | Streaming, async processing |
| Memory usage (large PDFs) | Medium | Page-by-page processing |
| JSON parsing failures | Low | json_repair.py already handles |

---

## Success Criteria

| Metric | Target | Verification |
|--------|--------|--------------|
| Detection accuracy | >= 99% | Regression tests vs original |
| OCR quality | >= 95% match | A/B comparison with original |
| Processing speed | No degradation | Benchmark suite |
| Test coverage | >= 90% | pytest-cov report |
| API compatibility | 100% | Integration tests |

---

*Document Version: 1.0*
*Created: 2026-01-07*
*Author: Architecture Review (Claude Code)*
