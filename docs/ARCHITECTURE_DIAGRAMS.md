# Text Extraction Service - Architecture Diagrams

## System Overview

```
+===========================================================================+
|                        TEXT EXTRACTION SERVICE                             |
+===========================================================================+
|                                                                            |
|  +----------------------------------+    +-----------------------------+   |
|  |         PUBLIC API              |    |       REST API (Optional)   |   |
|  |----------------------------------|    |-----------------------------|   |
|  | extract_text(file)               |    | POST /api/v1/extract        |   |
|  | classify_pdf(file)               |    | POST /api/v1/extract/async  |   |
|  | PDFTypeDetector                  |    | GET  /api/v1/jobs/{id}      |   |
|  | TwoPassProcessor                 |    | GET  /api/v1/health         |   |
|  | ContentRouter                    |    +-----------------------------+   |
|  +----------------------------------+                                      |
|                    |                                                       |
|                    v                                                       |
|  +------------------------------------------------------------------+     |
|  |                        CORE LAYER                                 |     |
|  +------------------------------------------------------------------+     |
|  |                                                                   |     |
|  |  +----------------+  +-----------------+  +-------------------+   |     |
|  |  | PDFTypeDetector|  | ContentRouter   |  | TwoPassProcessor  |   |     |
|  |  |----------------|  |-----------------|  |-------------------|   |     |
|  |  | classify_pdf() |  | route()         |  | process()         |   |     |
|  |  | analyze_page() |  | extract()       |  | pass_1_extract()  |   |     |
|  |  |                |  | _extract_direct |  | pass_2_analyze()  |   |     |
|  |  | Status: READY  |  | Status: TODO    |  | Status: TODO      |   |     |
|  |  +----------------+  +-----------------+  +-------------------+   |     |
|  |                                                                   |     |
|  +------------------------------------------------------------------+     |
|                    |                                                       |
|                    v                                                       |
|  +------------------------------------------------------------------+     |
|  |                      BACKEND LAYER                                |     |
|  +------------------------------------------------------------------+     |
|  |                                                                   |     |
|  |  +----------------+  +--------------+  +----------------+  +------------------+  |
|  |  | LangdockBackend|  | GeminiBackend|  |TesseractBackend|  |CloudVisionBackend|  |
|  |  |----------------|  |--------------|  |----------------|  |------------------|  |
|  |  | extract_text() |  |extract_text()|  | extract_text() |  | extract_text()   |  |
|  |  | is_available() |  |is_available()|  | is_available() |  | is_available()   |  |
|  |  |                |  |              |  |                |  |                  |  |
|  |  | Status: DONE   |  | Status: DONE |  | Status: DONE   |  | Status: OPTIONAL |  |
|  |  +-------+--------+  +------+-------+  +-------+--------+  +------------------+  |
|  |          |                  |                   |                                 |
|  +------------------------------------------------------------------+               |
|             |                  |                   |                                 |
|             v                  v                   v                                 |
|  +------------------------------------------------------------------+               |
|  |                    EXTERNAL SERVICES                              |               |
|  +------------------------------------------------------------------+               |
|  |  +----------------+  +----------------+  +----------------+  +----------------+  |
|  |  | Langdock API   |  | Gemini API     |  | Tesseract      |  | Cloud Vision   |  |
|  |  | (Claude/GPT)   |  | (Google)       |  | (Local)        |  | (GCP)          |  |
|  |  +----------------+  +----------------+  +----------------+  +----------------+  |
|  +------------------------------------------------------------------+               |
|                                                                            |
+============================================================================+
```

---

## Component Interaction Sequence

### Scenario 1: Pure Text PDF

```
User                 Library                    PyMuPDF
  |                     |                          |
  | extract_text(pdf)   |                          |
  +-------------------->|                          |
  |                     |                          |
  |                     | classify_pdf()           |
  |                     +------------------------->|
  |                     |<-------------------------+
  |                     | PDFType.PURE_TEXT        |
  |                     |                          |
  |                     | Direct text extraction   |
  |                     +------------------------->|
  |                     |<-------------------------+
  |                     | text content             |
  |                     |                          |
  |<--------------------+                          |
  | ExtractionResult    |                          |
```

### Scenario 2: Scanned PDF (Two-Pass OCR)

```
User             TwoPassProcessor        LangdockBackend       Langdock API
  |                     |                      |                    |
  | process(pdf)        |                      |                    |
  +-------------------->|                      |                    |
  |                     |                      |                    |
  |                     | 1. Detect scanned    |                    |
  |                     |    pages             |                    |
  |                     |                      |                    |
  |                     | 2. PASS 1: Extract   |                    |
  |                     |    text from scanned |                    |
  |                     |    pages             |                    |
  |                     +--------------------->|                    |
  |                     |                      | upload + OCR prompt|
  |                     |                      +------------------->|
  |                     |                      |<-------------------+
  |                     |                      | extracted text     |
  |                     |<---------------------+                    |
  |                     | ocr_context          |                    |
  |                     |                      |                    |
  |                     | 3. Build enhanced    |                    |
  |                     |    prompt            |                    |
  |                     |                      |                    |
  |                     | 4. PASS 2: Analyze   |                    |
  |                     |    full document     |                    |
  |                     +--------------------->|                    |
  |                     |                      | upload + analysis  |
  |                     |                      +------------------->|
  |                     |                      |<-------------------+
  |                     |                      | analysis result    |
  |                     |<---------------------+                    |
  |                     |                      |                    |
  |<--------------------+                      |                    |
  | ProcessorResult     |                      |                    |
```

### Scenario 3: Hybrid PDF

```
User           ContentRouter        PDFTypeDetector     Backends
  |                  |                    |                 |
  | extract(pdf)     |                    |                 |
  +----------------->|                    |                 |
  |                  |                    |                 |
  |                  | classify_pdf()     |                 |
  |                  +------------------->|                 |
  |                  |<-------------------+                 |
  |                  | HYBRID             |                 |
  |                  | text_pages=[1,2]   |                 |
  |                  | image_pages=[3,4]  |                 |
  |                  |                    |                 |
  |                  | Route:             |                 |
  |                  | - Pages 1,2: Direct|                 |
  |                  | - Pages 3,4: OCR   |                 |
  |                  |                    |                 |
  |                  | Direct extraction  |                 |
  |                  | (pages 1,2)        |                 |
  |                  +------------------------------------>|
  |                  |<------------------------------------+
  |                  |                    |                 |
  |                  | OCR extraction     |                 |
  |                  | (pages 3,4)        |                 |
  |                  +------------------------------------>|
  |                  |<------------------------------------+
  |                  |                    |                 |
  |                  | Merge results      |                 |
  |                  |                    |                 |
  |<-----------------+                    |                 |
  | ExtractionResult |                    |                 |
```

---

## Class Hierarchy

```
BaseOCRBackend (ABC)
    |
    +-- LangdockBackend
    |       - api_key
    |       - model, upload_url, assistant_url
    |       + extract_text()
    |       + is_available()
    |       + _upload_file()
    |       + _ocr_with_langdock()
    |
    +-- GeminiBackend
    |       - api_key
    |       - model (default: gemini-2.5-flash)
    |       + extract_text()
    |       + is_available()
    |       + _get_client() (lazy google.genai.Client)
    |       + _pdf_page_to_image() (PDF → PIL Image)
    |
    +-- TesseractBackend
    |       - tesseract_path
    |       - language
    |       + extract_text()
    |       + is_available()
    |       + _convert_pdf_to_images()
    |
    +-- CloudVisionBackend (optional)
            - credentials
            + extract_text()
            + is_available()


PDFTypeDetector
    - text_block_threshold
    - image_block_threshold
    + classify_pdf() -> PDFClassificationResult
    + analyze_page() -> PageAnalysis


ContentRouter
    - primary_backend: BaseOCRBackend
    - fallback_backend: BaseOCRBackend
    - detector: PDFTypeDetector
    + route() -> RoutingDecision
    + extract() -> ExtractionResult


TwoPassProcessor
    - ocr_backend: BaseOCRBackend
    - analysis_backend: BaseOCRBackend
    - config: ProcessorConfig
    - detector: PDFTypeDetector
    + process() -> ProcessorResult
    + _pass_1_extract_text()
    + _pass_2_analyze()
```

---

## Data Model Relationships

```
+-------------------+          +--------------------+
| BackendConfig     |          | ProcessorConfig    |
|-------------------|          |--------------------|
| api_key           |          | text_threshold     |
| model             |          | enable_two_pass    |
| temperature       |          | confidence_thresh  |
| max_tokens        |          | fallback_on_error  |
| timeout           |          | cleanup_temp_files |
| retry_attempts    |          +--------------------+
+-------------------+
         |
         v
+-------------------+          +--------------------+
| LangdockBackend   |--------->| BaseOCRBackend     |
+-------------------+          +--------------------+
         |
         v
+-------------------+          +--------------------+
| OCRResult         |<---------| PageOCRResult      |
|-------------------|          |--------------------|
| text              |          | page_number        |
| confidence        |          | text               |
| method            |          | confidence         |
| page_number       |          | method             |
| word_count        |          | processing_time_ms |
| metadata          |          +--------------------+
+-------------------+                   |
                                       v
                          +------------------------+
                          | DocumentOCRResult      |
                          |------------------------|
                          | success                |
                          | file_name              |
                          | pages: List[Page...]   |
                          | total_pages            |
                          | total_word_count       |
                          | processing_time_ms     |
                          | error                  |
                          | metadata               |
                          +------------------------+
                                       |
                                       v
                          +------------------------+
                          | ExtractionResult       |
                          |------------------------|
                          | success                |
                          | file_name              |
                          | pdf_type               |
                          | pages                  |
                          | full_text              |
                          | metadata               |
                          | error                  |
                          +------------------------+
```

---

## File Structure (Final)

```
text-extraction-service/
+-- src/
|   +-- text_extraction/
|   |   +-- __init__.py              # Public API exports
|   |   +-- detector.py              # [READY] PDFTypeDetector
|   |   +-- router.py                # [TODO] ContentRouter
|   |   +-- processor.py             # [TODO] TwoPassProcessor
|   |   +-- json_repair.py           # [READY] JSON recovery
|   |   |
|   |   +-- models/
|   |   |   +-- __init__.py
|   |   |   +-- config.py            # [TODO] Configuration classes
|   |   |   +-- extraction.py        # [TODO] Result classes
|   |   |
|   |   +-- backends/
|   |   |   +-- __init__.py
|   |   |   +-- base.py              # [READY] BaseOCRBackend
|   |   |   +-- langdock.py          # [DONE] LangdockBackend
|   |   |   +-- gemini.py            # [DONE] GeminiBackend
|   |   |   +-- tesseract.py         # [DONE] TesseractBackend
|   |   |
|   |   +-- utils/
|   |       +-- __init__.py
|   |       +-- validation.py        # [TODO] File validation
|   |
|   +-- service/                      # [OPTIONAL] FastAPI wrapper
|       +-- __init__.py
|       +-- app.py
|       +-- routes.py
|       +-- worker.py
|
+-- tests/
|   +-- unit/
|   +-- integration/
|   +-- fixtures/
|
+-- docs/
|   +-- TEXT_EXTRACTION_SERVICE_ARCHITECTURE.md
|   +-- IMPLEMENTATION_PLAN.md
|   +-- ARCHITECTURE_DIAGRAMS.md
|   +-- api.md
|   +-- quickstart.md
|
+-- examples/
|   +-- two_pass_ocr_processor_original.py
|   +-- langdock_inline_client_original.py
|   +-- assistant_config_original.py
|
+-- pyproject.toml
+-- README.md
+-- CLAUDE.md
+-- .env.example
```

---

## API Reference (Library)

### Quick Start

```python
# Simple extraction
from text_extraction import extract_text

result = extract_text("invoice.pdf")
print(result.full_text)
print(result.pdf_type)  # PURE_TEXT, PURE_IMAGE, or HYBRID

# PDF classification only
from text_extraction import classify_pdf

classification = classify_pdf("invoice.pdf")
print(classification.pdf_type)
print(classification.text_pages)
print(classification.image_pages)
```

### Advanced Usage

```python
from text_extraction import (
    TwoPassProcessor,
    LangdockBackend,
    TesseractBackend,
    ProcessorConfig,
    BackendConfig
)

# Configure backends
langdock = LangdockBackend(
    api_key="sk-...",
    config=BackendConfig(
        model="claude-sonnet-4-5",
        temperature=0.0,
        timeout=120
    )
)

tesseract = TesseractBackend(
    language="deu+eng"
)

# Configure processor
config = ProcessorConfig(
    text_threshold=10,
    enable_two_pass=True,
    confidence_threshold=0.8,
    fallback_on_error=True
)

# Create processor
processor = TwoPassProcessor(
    ocr_backend=langdock,
    analysis_backend=langdock,
    config=config
)

# Process document
result = await processor.process(
    file_path=Path("scanned_invoice.pdf"),
    prompt="Extract invoice data..."
)

print(result.success)
print(result.metadata.used_two_pass)
print(result.metadata.scanned_pages)
```

### Content Router Usage

```python
from text_extraction import ContentRouter, LangdockBackend, TesseractBackend

# Setup with fallback
router = ContentRouter(
    primary_backend=LangdockBackend(),
    fallback_backend=TesseractBackend()
)

# Get routing decision
decision = router.route("document.pdf")
print(decision.strategy)      # "direct", "ocr", or "hybrid"
print(decision.direct_pages)  # Pages for direct extraction
print(decision.ocr_pages)     # Pages needing OCR

# Extract with optimal strategy
result = router.extract("document.pdf")
```

---

## REST API Reference (Service)

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/extract` | Synchronous extraction |
| POST | `/api/v1/extract/async` | Start async job |
| GET | `/api/v1/jobs/{id}` | Get job status |
| GET | `/api/v1/jobs/{id}/result` | Get extraction result |
| GET | `/api/v1/health` | Health check |

### Request Examples

```bash
# Sync extraction
curl -X POST http://localhost:1337/api/v1/extract \
  -H "X-API-Key: your-key" \
  -F "file=@invoice.pdf" \
  -F 'options={"backend":"auto","language":"deu"}'

# Async extraction
curl -X POST http://localhost:1337/api/v1/extract/async \
  -H "X-API-Key: your-key" \
  -F "file=@large_document.pdf" \
  -F 'callback_url=https://my-service.com/webhook'

# Check job status
curl http://localhost:1337/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your-key"
```

---

*Document Version: 1.0*
*Created: 2026-01-07*
*Author: Architecture Review (Claude Code)*
