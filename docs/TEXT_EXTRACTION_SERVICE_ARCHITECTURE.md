# Text Extraction Service - Architecture Design

## Executive Summary

This document presents three architectural options for extracting text extraction functionality from the `list-eingangsrechnungen` project into an independent, reusable service. The service will handle PDF and image OCR with intelligent routing, multi-backend support, and GDPR compliance.

**Current Implementation Analysis:**
- `pdf_type_detector.py` (354 lines): PyMuPDF block-type classification
- `two_pass_ocr_processor.py` (637 lines): Two-pass OCR strategy
- `langdock_inline_client.py` (354 lines): LLM API client
- `assistant_config.py` (213 lines): Model configuration
- `json_repair.py` (271 lines): JSON error recovery

**Total: ~1,800 lines of battle-tested code**

---

## Requirements Summary

### Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| F1 | PDF text extraction (native + OCR) | Must |
| F2 | Image OCR (PNG, JPG, TIFF, BMP, HEIC, WebP) | Must |
| F3 | Content-type based routing | Must |
| F4 | Async processing for large files | Must |
| F5 | Multi-backend support (LLM OCR + Tesseract) | Should |
| F6 | Structured output (JSON) | Must |
| F7 | Confidence scores | Should |

### Non-Functional Requirements
| ID | Requirement | Target |
|----|-------------|--------|
| NF1 | Response time (text PDF) | < 2s |
| NF2 | Response time (scanned PDF) | < 30s |
| NF3 | Availability | 99.5% |
| NF4 | GDPR compliance | Full |
| NF5 | Max file size | 50MB |
| NF6 | Concurrent requests | 100/min |

---

## Option 1: Microservice with FastAPI

### Architecture Diagram

```
                                   +----------------------------------+
                                   |      Load Balancer (nginx)       |
                                   +----------------+-----------------+
                                                    |
                    +-------------------------------+-------------------------------+
                    |                               |                               |
         +----------v----------+         +----------v----------+         +----------v----------+
         |   FastAPI Instance  |         |   FastAPI Instance  |         |   FastAPI Instance  |
         |      (Worker 1)     |         |      (Worker 2)     |         |      (Worker N)     |
         +----------+----------+         +----------+----------+         +----------+----------+
                    |                               |                               |
                    +-------------------------------+-------------------------------+
                                                    |
                    +-------------------------------+-------------------------------+
                    |                               |                               |
         +----------v----------+         +----------v----------+         +----------v----------+
         |       Redis         |         |     PostgreSQL      |         |    MinIO/S3         |
         |  (Queue + Cache)    |         |   (Job Tracking)    |         |  (File Storage)     |
         +---------------------+         +---------------------+         +---------------------+

                    +---------------------------------------------------------------+
                    |                        OCR Backends                           |
                    +---------------------------------------------------------------+
                    |                               |                               |
         +----------v----------+         +----------v----------+         +----------v----------+
         |   Langdock API      |         |   Tesseract         |         |   Cloud Vision      |
         | (Claude/GPT OCR)    |         |   (Local Fallback)  |         |   (GCP - Optional)  |
         +---------------------+         +---------------------+         +---------------------+
```

### Component Details

```
text-extraction-service/
+-- src/
|   +-- api/
|   |   +-- __init__.py
|   |   +-- routes/
|   |   |   +-- extract.py         # POST /extract, GET /jobs/{id}
|   |   |   +-- health.py          # GET /health, GET /ready
|   |   |   +-- files.py           # POST /files, DELETE /files/{id}
|   |   +-- schemas/
|   |   |   +-- requests.py        # ExtractionRequest, FileUpload
|   |   |   +-- responses.py       # ExtractionResult, JobStatus
|   |   +-- middleware/
|   |       +-- auth.py            # API key validation
|   |       +-- gdpr.py            # Data retention, anonymization
|   |
|   +-- core/
|   |   +-- detector.py            # PDFTypeDetector (from pdf_type_detector.py)
|   |   +-- processor.py           # TwoPassProcessor (from two_pass_ocr_processor.py)
|   |   +-- router.py              # ContentRouter (routing logic)
|   |
|   +-- backends/
|   |   +-- base.py                # BaseOCRBackend (abstract)
|   |   +-- langdock.py            # LangdockBackend (LLM OCR)
|   |   +-- tesseract.py           # TesseractBackend (local fallback)
|   |   +-- cloud_vision.py        # CloudVisionBackend (optional)
|   |
|   +-- storage/
|   |   +-- file_store.py          # MinIO/S3 file handling
|   |   +-- cleanup.py             # GDPR data retention
|   |
|   +-- workers/
|   |   +-- extraction_worker.py   # Async job processing
|   |   +-- cleanup_worker.py      # Scheduled cleanup
|   |
|   +-- config.py                  # Environment configuration
|   +-- main.py                    # FastAPI application entry
|
+-- tests/
+-- docker/
|   +-- Dockerfile
|   +-- docker-compose.yml
+-- k8s/
|   +-- deployment.yaml
|   +-- service.yaml
+-- requirements.txt
+-- pyproject.toml
```

### Tech Stack

| Component | Technology | Justification |
|-----------|------------|---------------|
| Framework | FastAPI 0.104+ | Async native, OpenAPI docs, high performance |
| Database | PostgreSQL 15 | ACID, JSON support, proven reliability |
| Queue | Redis 7 | Fast, pub/sub, caching, rate limiting |
| Storage | MinIO (S3-compatible) | Self-hosted, GDPR-friendly, cost-effective |
| OCR Primary | Langdock API | Best accuracy (Claude Sonnet 4.5) |
| OCR Fallback | Tesseract 5.3 | Free, local, offline capable |
| Container | Docker + K8s | Scalable, portable, industry standard |
| PDF Processing | PyMuPDF 1.23+ | Fast, reliable, Python native |

### Pros and Cons

**Pros:**
- Full control over infrastructure and scaling
- Self-hosted option for GDPR compliance
- Horizontal scaling with Kubernetes
- Rich monitoring (Prometheus, Grafana)
- Battle-tested FastAPI patterns already in use

**Cons:**
- Higher operational overhead
- Requires DevOps expertise
- Initial setup complexity
- Infrastructure costs (servers, storage)

### Implementation Complexity

| Phase | Effort | Duration |
|-------|--------|----------|
| Core extraction | 40h | 1 week |
| API layer | 24h | 0.5 week |
| Job queue | 16h | 0.5 week |
| Storage + GDPR | 24h | 0.5 week |
| Docker + CI/CD | 16h | 0.5 week |
| Testing | 24h | 0.5 week |
| **Total** | **144h** | **3.5 weeks** |

### Cost Considerations (Monthly)

| Item | Self-Hosted | Cloud Managed |
|------|-------------|---------------|
| Compute (3x instances) | 150 EUR | 300 EUR |
| PostgreSQL | 50 EUR | 100 EUR |
| Redis | 30 EUR | 80 EUR |
| Storage (100GB) | 20 EUR | 50 EUR |
| Langdock API (60K docs) | 3,600 EUR | 3,600 EUR |
| **Total** | **3,850 EUR** | **4,130 EUR** |

---

## Option 2: Serverless (Cloud Functions)

### Architecture Diagram

```
                                   +----------------------------------+
                                   |      API Gateway                 |
                                   |   (Cloud Endpoints / Kong)       |
                                   +----------------+-----------------+
                                                    |
                    +-------------------------------+-------------------------------+
                    |                               |                               |
         +----------v----------+         +----------v----------+         +----------v----------+
         |   Cloud Function    |         |   Cloud Function    |         |   Cloud Function    |
         |   extract_sync      |         |   extract_async     |         |   get_job_status    |
         |   (< 5MB files)     |         |   (> 5MB files)     |         |                     |
         +----------+----------+         +----------+----------+         +----------+----------+
                    |                               |                               |
                    |                    +----------v----------+                    |
                    |                    |    Cloud Tasks      |                    |
                    |                    |   (Job Queue)       |                    |
                    |                    +----------+----------+                    |
                    |                               |                               |
                    +-------------------------------+-------------------------------+
                                                    |
                    +-------------------------------+-------------------------------+
                    |                               |                               |
         +----------v----------+         +----------v----------+         +----------v----------+
         |   Cloud Storage     |         |     Firestore       |         |   Secret Manager    |
         |   (File Upload)     |         |   (Job State)       |         |   (API Keys)        |
         +---------------------+         +---------------------+         +---------------------+

                                   +----------------------------------+
                                   |        OCR Processing            |
                                   +----------------------------------+
                                   |               |                  |
                        +----------v----+  +------v------+  +--------v--------+
                        | Langdock API  |  | Cloud Vision|  | Document AI     |
                        | (Primary)     |  | (Fallback)  |  | (GCP Native)    |
                        +---------------+  +-------------+  +-----------------+
```

### Component Details

```
text-extraction-serverless/
+-- functions/
|   +-- extract_sync/
|   |   +-- main.py               # Synchronous extraction (< 5MB)
|   |   +-- requirements.txt
|   |
|   +-- extract_async/
|   |   +-- main.py               # Async extraction trigger
|   |   +-- requirements.txt
|   |
|   +-- process_job/
|   |   +-- main.py               # Cloud Tasks worker
|   |   +-- requirements.txt
|   |
|   +-- get_status/
|   |   +-- main.py               # Job status query
|   |   +-- requirements.txt
|   |
|   +-- cleanup/
|       +-- main.py               # Scheduled GDPR cleanup
|       +-- requirements.txt
|
+-- shared/
|   +-- detector.py               # PDFTypeDetector
|   +-- processor.py              # TwoPassProcessor
|   +-- backends/
|   |   +-- langdock.py
|   |   +-- cloud_vision.py
|   +-- storage.py                # Cloud Storage wrapper
|   +-- config.py
|
+-- terraform/
|   +-- main.tf
|   +-- variables.tf
|   +-- outputs.tf
|
+-- tests/
+-- cloudbuild.yaml
```

### Tech Stack

| Component | Technology | Justification |
|-----------|------------|---------------|
| Compute | Cloud Functions (Gen 2) | Auto-scale, pay-per-use |
| Queue | Cloud Tasks | Native integration, retries |
| Storage | Cloud Storage | Scalable, lifecycle policies |
| Database | Firestore | Serverless, auto-scale |
| API Gateway | Cloud Endpoints | Auth, rate limiting |
| OCR Backup | Cloud Vision API | Native GCP integration |
| IaC | Terraform | Reproducible infrastructure |

### Pros and Cons

**Pros:**
- Zero server management
- Auto-scaling (0 to 1000+)
- Pay-per-execution cost model
- Built-in monitoring (Cloud Logging)
- Quick initial deployment

**Cons:**
- Cold start latency (2-5s)
- 540s timeout limit (Gen 2)
- Vendor lock-in (GCP)
- Limited local development
- GDPR: Data residency concerns (EU region required)

### Implementation Complexity

| Phase | Effort | Duration |
|-------|--------|----------|
| Core extraction | 32h | 1 week |
| Functions setup | 16h | 0.5 week |
| Terraform IaC | 24h | 0.5 week |
| Storage + GDPR | 16h | 0.5 week |
| API Gateway | 8h | 0.25 week |
| Testing | 16h | 0.5 week |
| **Total** | **112h** | **3 weeks** |

### Cost Considerations (Monthly, 60K Documents)

| Item | Estimate |
|------|----------|
| Cloud Functions (invocations) | 50 EUR |
| Cloud Tasks | 10 EUR |
| Cloud Storage (100GB) | 20 EUR |
| Firestore (reads/writes) | 30 EUR |
| Cloud Endpoints | 20 EUR |
| Langdock API | 3,600 EUR |
| **Total** | **3,730 EUR** |

---

## Option 3: Library Package + Service

### Architecture Diagram

```
+-----------------------------------------------------------------------+
|                        text-extraction Package                         |
+-----------------------------------------------------------------------+
|                                                                        |
|  +------------------------+    +------------------------+              |
|  |   text_extraction      |    |   text_extraction      |              |
|  |   .detector            |    |   .processor           |              |
|  |                        |    |                        |              |
|  |   PDFTypeDetector      |    |   TwoPassProcessor     |              |
|  |   ImageTypeDetector    |    |   SinglePassProcessor  |              |
|  |   ContentRouter        |    |   BatchProcessor       |              |
|  +------------------------+    +------------------------+              |
|                                                                        |
|  +------------------------+    +------------------------+              |
|  |   text_extraction      |    |   text_extraction      |              |
|  |   .backends            |    |   .utils               |              |
|  |                        |    |                        |              |
|  |   LangdockBackend      |    |   JSONRepair           |              |
|  |   TesseractBackend     |    |   FileValidation       |              |
|  |   CloudVisionBackend   |    |   GDPRCompliance       |              |
|  +------------------------+    +------------------------+              |
|                                                                        |
+-----------------------------------------------------------------------+
                    |                               |
                    v                               v
    +-------------------------------+   +-------------------------------+
    |   Direct Library Usage        |   |   Service Wrapper             |
    |                               |   |                               |
    |   from text_extraction import |   |   text-extraction-service     |
    |       PDFTypeDetector,        |   |   (FastAPI + Redis + PG)      |
    |       TwoPassProcessor        |   |                               |
    |                               |   |   Uses library internally     |
    |   detector = PDFTypeDetector()|   |                               |
    |   result = detector.classify()|   |   POST /extract               |
    +-------------------------------+   +-------------------------------+
                    |                               |
                    v                               v
    +-------------------------------+   +-------------------------------+
    |   Consumer: list-eingangs-    |   |   Consumer: Other Services    |
    |   rechnungen                  |   |   (REST API clients)          |
    +-------------------------------+   +-------------------------------+
```

### Package Structure

```
text-extraction/
+-- src/
|   +-- text_extraction/
|   |   +-- __init__.py           # Public API exports
|   |   +-- detector/
|   |   |   +-- __init__.py
|   |   |   +-- pdf.py            # PDFTypeDetector
|   |   |   +-- image.py          # ImageTypeDetector
|   |   |   +-- router.py         # ContentRouter
|   |   |
|   |   +-- processor/
|   |   |   +-- __init__.py
|   |   |   +-- two_pass.py       # TwoPassProcessor
|   |   |   +-- single_pass.py    # SinglePassProcessor (images)
|   |   |   +-- batch.py          # BatchProcessor
|   |   |
|   |   +-- backends/
|   |   |   +-- __init__.py
|   |   |   +-- base.py           # BaseBackend (Protocol)
|   |   |   +-- langdock.py       # LangdockBackend
|   |   |   +-- tesseract.py      # TesseractBackend
|   |   |   +-- cloud_vision.py   # CloudVisionBackend
|   |   |
|   |   +-- models/
|   |   |   +-- __init__.py
|   |   |   +-- classification.py # PDFType, ClassificationResult
|   |   |   +-- extraction.py     # ExtractionResult, TextBlock
|   |   |   +-- config.py         # BackendConfig, ProcessorConfig
|   |   |
|   |   +-- utils/
|   |       +-- __init__.py
|   |       +-- json_repair.py    # JSON repair utilities
|   |       +-- validation.py     # File validation
|   |       +-- gdpr.py           # GDPR compliance helpers
|   |
|   +-- service/                   # Optional service wrapper
|       +-- __init__.py
|       +-- app.py                 # FastAPI application
|       +-- routes.py              # API endpoints
|       +-- worker.py              # Background worker
|
+-- tests/
|   +-- unit/
|   +-- integration/
|   +-- fixtures/
|
+-- docs/
|   +-- api.md
|   +-- quickstart.md
|   +-- backends.md
|
+-- examples/
|   +-- basic_usage.py
|   +-- custom_backend.py
|   +-- batch_processing.py
|
+-- pyproject.toml
+-- README.md
+-- CHANGELOG.md
```

### Tech Stack

| Component | Technology | Justification |
|-----------|------------|---------------|
| Package | Python 3.10+ | Type hints, async support |
| PDF | PyMuPDF 1.23+ | Fast, reliable |
| Image | Pillow 10+ | Standard image processing |
| OCR Local | pytesseract 0.3+ | Tesseract wrapper |
| Typing | Pydantic 2.0+ | Validation, serialization |
| Async | asyncio | Native Python async |
| Build | Poetry/PDM | Modern dependency management |
| Service (opt) | FastAPI | When REST API needed |

### Pros and Cons

**Pros:**
- Maximum flexibility for consumers
- No network overhead for direct usage
- Testable in isolation
- Gradual adoption possible
- Open-source friendly (MIT license)
- Reusable across multiple projects

**Cons:**
- Requires Python environment
- No built-in job tracking
- Consumers must handle async themselves
- Additional service layer for non-Python consumers

### Implementation Complexity

| Phase | Effort | Duration |
|-------|--------|----------|
| Core package | 40h | 1 week |
| Backend implementations | 24h | 0.5 week |
| Service wrapper | 24h | 0.5 week |
| Documentation | 16h | 0.5 week |
| PyPI packaging | 8h | 0.25 week |
| Testing | 24h | 0.5 week |
| **Total** | **136h** | **3.25 weeks** |

### Cost Considerations

| Item | Library Only | With Service |
|------|--------------|--------------|
| Development | One-time | One-time |
| Hosting | 0 EUR | 250 EUR/mo |
| Langdock API | Per consumer | Shared |
| Maintenance | 8h/month | 16h/month |

---

## API Contract Design

### REST API Endpoints

```yaml
openapi: 3.1.0
info:
  title: Text Extraction Service API
  version: 1.0.0
  description: |
    Intelligent text extraction from PDFs and images with
    LLM-powered OCR and automatic content routing.

servers:
  - url: https://api.extraction.example.com/v1
    description: Production
  - url: http://localhost:8080/v1
    description: Development

paths:
  /extract:
    post:
      summary: Extract text from document
      description: |
        Synchronous extraction for small files (< 5MB).
        For larger files, use async endpoint.
      operationId: extractText
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              $ref: '#/components/schemas/ExtractionRequest'
      responses:
        '200':
          description: Extraction successful
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ExtractionResult'
        '202':
          description: Job accepted (async processing)
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAccepted'
        '400':
          description: Invalid request
        '413':
          description: File too large
        '429':
          description: Rate limit exceeded

  /extract/async:
    post:
      summary: Start async extraction job
      description: |
        Create extraction job for processing in background.
        Use for large files or batch processing.
      operationId: startAsyncExtraction
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              $ref: '#/components/schemas/AsyncExtractionRequest'
      responses:
        '202':
          description: Job created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAccepted'

  /jobs/{job_id}:
    get:
      summary: Get job status
      operationId: getJobStatus
      parameters:
        - name: job_id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Job status
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobStatus'
        '404':
          description: Job not found

  /jobs/{job_id}/result:
    get:
      summary: Get extraction result
      operationId: getJobResult
      parameters:
        - name: job_id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Extraction result
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ExtractionResult'
        '202':
          description: Job still processing
        '404':
          description: Job not found

  /health:
    get:
      summary: Health check
      operationId: healthCheck
      responses:
        '200':
          description: Service healthy

components:
  schemas:
    ExtractionRequest:
      type: object
      required:
        - file
      properties:
        file:
          type: string
          format: binary
          description: PDF or image file
        options:
          $ref: '#/components/schemas/ExtractionOptions'

    AsyncExtractionRequest:
      type: object
      required:
        - file
      properties:
        file:
          type: string
          format: binary
        callback_url:
          type: string
          format: uri
          description: Webhook URL for completion notification
        options:
          $ref: '#/components/schemas/ExtractionOptions'

    ExtractionOptions:
      type: object
      properties:
        backend:
          type: string
          enum: [auto, langdock, tesseract, cloud_vision]
          default: auto
          description: OCR backend to use
        language:
          type: string
          default: deu
          description: Primary document language (ISO 639-3)
        output_format:
          type: string
          enum: [text, structured, markdown]
          default: structured
        include_confidence:
          type: boolean
          default: true
        include_bounding_boxes:
          type: boolean
          default: false
        gdpr_mode:
          type: boolean
          default: false
          description: If true, file deleted immediately after processing

    ExtractionResult:
      type: object
      required:
        - job_id
        - status
        - content_type
        - extracted_text
      properties:
        job_id:
          type: string
          format: uuid
        status:
          type: string
          enum: [completed, failed]
        content_type:
          $ref: '#/components/schemas/ContentType'
        extracted_text:
          type: string
          description: Full extracted text
        structured_content:
          type: array
          items:
            $ref: '#/components/schemas/TextBlock'
        metadata:
          $ref: '#/components/schemas/ExtractionMetadata'
        error:
          type: string
          description: Error message if failed

    ContentType:
      type: object
      properties:
        document_type:
          type: string
          enum: [pure_text, pure_image, hybrid]
        mime_type:
          type: string
        page_count:
          type: integer
        text_pages:
          type: array
          items:
            type: integer
        image_pages:
          type: array
          items:
            type: integer

    TextBlock:
      type: object
      properties:
        page:
          type: integer
        text:
          type: string
        confidence:
          type: number
          minimum: 0
          maximum: 1
        bounding_box:
          $ref: '#/components/schemas/BoundingBox'
        block_type:
          type: string
          enum: [paragraph, heading, table, list, other]

    BoundingBox:
      type: object
      properties:
        x0:
          type: number
        y0:
          type: number
        x1:
          type: number
        y1:
          type: number

    ExtractionMetadata:
      type: object
      properties:
        backend_used:
          type: string
        processing_time_ms:
          type: integer
        ocr_passes:
          type: integer
        model_used:
          type: string
        pages_processed:
          type: integer
        confidence_score:
          type: number

    JobAccepted:
      type: object
      properties:
        job_id:
          type: string
          format: uuid
        status:
          type: string
          enum: [pending, processing]
        estimated_duration_seconds:
          type: integer
        status_url:
          type: string
          format: uri

    JobStatus:
      type: object
      properties:
        job_id:
          type: string
          format: uuid
        status:
          type: string
          enum: [pending, processing, completed, failed]
        progress:
          type: integer
          minimum: 0
          maximum: 100
        created_at:
          type: string
          format: date-time
        completed_at:
          type: string
          format: date-time
        result_url:
          type: string
          format: uri

  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

security:
  - ApiKeyAuth: []
```

### Request/Response Examples

**Sync Extraction Request:**
```bash
curl -X POST https://api.extraction.example.com/v1/extract \
  -H "X-API-Key: your-api-key" \
  -F "file=@invoice.pdf" \
  -F "options={\"backend\":\"auto\",\"language\":\"deu\"}"
```

**Sync Extraction Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "content_type": {
    "document_type": "hybrid",
    "mime_type": "application/pdf",
    "page_count": 3,
    "text_pages": [1],
    "image_pages": [2, 3]
  },
  "extracted_text": "Rechnung Nr. 12345\nFirma ABC GmbH\n...",
  "structured_content": [
    {
      "page": 1,
      "text": "Rechnung Nr. 12345",
      "confidence": 0.98,
      "block_type": "heading"
    },
    {
      "page": 2,
      "text": "Position 1: Montagearbeiten...",
      "confidence": 0.89,
      "block_type": "paragraph"
    }
  ],
  "metadata": {
    "backend_used": "langdock",
    "processing_time_ms": 4523,
    "ocr_passes": 2,
    "model_used": "claude-sonnet-4-5@20250929",
    "pages_processed": 3,
    "confidence_score": 0.92
  }
}
```

---

## Integration Pattern for list-eingangsrechnungen

### Current Architecture
```
list-eingangsrechnungen/
+-- batch_langdock_client.py    --> Uses langdock_inline_client.py
+-- two_pass_ocr_processor.py   --> Uses pdf_type_detector.py
+-- langdock_inline_client.py   --> Direct Langdock API calls
+-- pdf_type_detector.py        --> PyMuPDF classification
```

### Target Architecture (Option 3 - Library)

```python
# list-eingangsrechnungen/batch_client.py

from text_extraction import (
    PDFTypeDetector,
    TwoPassProcessor,
    LangdockBackend,
    ProcessorConfig
)

class BatchInvoiceProcessor:
    """Invoice processing using text-extraction library."""

    def __init__(self):
        # Configure extraction backend
        self.backend = LangdockBackend(
            api_key=os.getenv('LANGDOCK_API_KEY'),
            ocr_model="claude-sonnet-4-5@20250929",
            analysis_model="gpt-4o"
        )

        # Configure processor
        self.config = ProcessorConfig(
            text_threshold=10,
            enable_two_pass=True,
            confidence_threshold=0.8
        )

        # Initialize processor
        self.processor = TwoPassProcessor(
            backend=self.backend,
            config=self.config
        )

    async def process_invoice(self, pdf_path: Path) -> dict:
        """Process single invoice with text extraction."""

        # Extract text using library
        extraction_result = await self.processor.process(pdf_path)

        # Continue with invoice-specific analysis
        return self._analyze_invoice(extraction_result)
```

### Target Architecture (Option 1/2 - Service)

```python
# list-eingangsrechnungen/extraction_client.py

import httpx
from typing import Optional

class ExtractionServiceClient:
    """Client for external text extraction service."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=60.0
        )

    async def extract_text(
        self,
        file_path: Path,
        options: Optional[dict] = None
    ) -> dict:
        """Extract text from document via service."""

        with open(file_path, "rb") as f:
            response = await self.client.post(
                "/v1/extract",
                files={"file": f},
                data={"options": json.dumps(options or {})}
            )

        response.raise_for_status()
        return response.json()

    async def extract_async(
        self,
        file_path: Path,
        callback_url: Optional[str] = None
    ) -> str:
        """Start async extraction job, return job_id."""

        with open(file_path, "rb") as f:
            response = await self.client.post(
                "/v1/extract/async",
                files={"file": f},
                data={"callback_url": callback_url}
            )

        response.raise_for_status()
        return response.json()["job_id"]

    async def get_result(self, job_id: str) -> dict:
        """Get extraction result by job ID."""

        response = await self.client.get(f"/v1/jobs/{job_id}/result")
        response.raise_for_status()
        return response.json()
```

---

## Migration Strategy

### Phase 1: Extract and Package (Week 1-2)

```
Step 1.1: Create new repository
  - text-extraction/ (new repo)
  - Copy core files with minimal changes

Step 1.2: Refactor dependencies
  - Remove list-eingangsrechnungen specific code
  - Abstract backend configuration
  - Add Pydantic models for type safety

Step 1.3: Create unit tests
  - Test PDFTypeDetector independently
  - Test TwoPassProcessor with mock backends
  - Test each backend implementation
```

### Phase 2: Parallel Operation (Week 3-4)

```
Step 2.1: Install library in list-eingangsrechnungen
  pip install text-extraction (from private PyPI or Git)

Step 2.2: Create adapter layer
  - TextExtractionAdapter wraps library
  - Same interface as old implementation
  - A/B testing capability

Step 2.3: Run parallel comparison
  - Process same PDFs with old and new code
  - Compare results automatically
  - Log any discrepancies
```

### Phase 3: Cutover (Week 5)

```
Step 3.1: Remove old implementation
  - Delete pdf_type_detector.py
  - Delete two_pass_ocr_processor.py
  - Delete langdock_inline_client.py
  - Update imports

Step 3.2: Update documentation
  - New architecture diagrams
  - Updated CLAUDE.md
  - Migration notes

Step 3.3: Cleanup
  - Remove dead code
  - Update tests
  - Final verification
```

### Rollback Plan

```python
# Keep old files in archive branch
git checkout -b archive/pre-extraction-service
git tag pre-extraction-migration

# If issues arise:
git revert --no-commit HEAD~N  # N = commits since migration
# Or restore specific files from tag
```

---

## Recommendation

### Recommended Approach: Option 3 (Library + Service)

**Justification:**

1. **Lowest Risk Migration**
   - Preserves existing code structure
   - Gradual adoption possible
   - Easy rollback if issues

2. **Maximum Flexibility**
   - Direct library usage for list-eingangsrechnungen (no network overhead)
   - Optional service wrapper for other consumers
   - Custom backends can be added

3. **Cost Efficiency**
   - No additional infrastructure for library usage
   - Service layer only when needed
   - Shared development effort across projects

4. **Alignment with Current Stack**
   - Already using FastAPI patterns
   - Python ecosystem familiarity
   - Same deployment infrastructure

5. **GDPR Compliance**
   - Data stays local with library usage
   - Service can be self-hosted
   - Clear data retention policies

### Implementation Order

1. **Start with Library** (136h)
   - Extract core functionality
   - Create pip package
   - Migrate list-eingangsrechnungen

2. **Add Service Wrapper Later** (if needed)
   - When non-Python consumers emerge
   - When centralized job tracking required
   - Incremental effort: +40-60h

### Success Criteria

| Metric | Target | Verification |
|--------|--------|--------------|
| Detection accuracy | >= 99% | Regression tests |
| OCR quality | >= 95% (vs current) | A/B comparison |
| Processing speed | No degradation | Benchmark suite |
| Test coverage | >= 90% | pytest-cov |
| Documentation | Complete API docs | Manual review |

---

## Implementation Status (2026-01-08)

All major components from Option 3 (Library + Service) have been implemented:

### Completed Components

| Component | File | Status |
|-----------|------|--------|
| PDF Type Detector | `src/text_extraction/detector.py` | ✅ Production |
| OCR Base Backend | `src/text_extraction/backends/base.py` | ✅ Production |
| Langdock OCR | `src/text_extraction/backends/langdock.py` | ✅ Production |
| Tesseract OCR | `src/text_extraction/backends/tesseract.py` | ✅ Production |
| JSON Repair | `src/text_extraction/json_repair.py` | ✅ Production |
| FastAPI Service | `service/main.py` | ✅ Production |
| Docker Setup | `Dockerfile`, `docker-compose.yml` | ✅ Production |
| Terraform (GCP) | `terraform/*.tf` | ✅ Ready |
| CI/CD Workflows | `.github/workflows/*.yml` | ✅ Ready |

### Tested OCR Results

- **Langdock (Claude Sonnet 4.5)**: Excellent quality, markdown formatting, ~25s/page
- **Tesseract**: Good quality, plain text, ~2s/page
- **Automatic fallback**: Langdock → Tesseract → direct extraction

### API Endpoints (Implemented)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/classify` | POST | PDF type classification |
| `/api/v1/extract` | POST | Text extraction with OCR |

### Remaining TODO

- Two-Pass Processor (`processor.py`) - full document caching
- Async job queue for large PDFs
- Cloud Vision backend (optional)

---

*Document Version: 2.0*
*Last Updated: 2026-01-08*
*Author: Architecture Review (Claude Code)*
