# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Text Extraction Service is a Python library (with FastAPI wrapper) for extracting text from PDFs and images. Extracted from the `list-eingangsrechnungen` invoice processing system where it achieved 100% success rate on 42 test PDFs.

**Core capability**: Classify PDFs by content type (text/image/hybrid) and route pages to appropriate extraction methods including LLM-based OCR.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run all tests
pytest

# Run single test file
pytest tests/unit/test_detector.py -v

# Run with coverage
pytest --cov=src/text_extraction --cov-report=html

# Lint
ruff check src/

# Type check
mypy src/

# Format
ruff format src/

# Test a PDF directly
python -m text_extraction.detector path/to/file.pdf

# Run FastAPI service locally
uvicorn service.main:app --host 0.0.0.0 --port 8080 --reload

# Docker development
docker-compose up --build

# Test API endpoints
curl http://localhost:8080/health
curl -X POST -F "file=@test.pdf" http://localhost:8080/api/v1/classify
curl -X POST -F "file=@test.pdf" http://localhost:8080/api/v1/extract
```

## Architecture

### PDF Classification Flow

```
PDF Input → PDFTypeDetector.classify_pdf()
                    ↓
         analyze_page() for each page
         (count text blocks vs image blocks)
                    ↓
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
PURE_TEXT       HYBRID          PURE_IMAGE
(all text)    (mixed pages)    (all scanned)
    ↓               ↓               ↓
Direct        Route by page     LLM OCR
extraction    text→direct       for all
              image→OCR
```

### OCR Backend Selection

```
get_ocr_backend()
        ↓
┌───────────────────┐
│ LangdockBackend   │ ← Primary (best quality)
│ is_available()?   │
└─────────┬─────────┘
          │ No
          ↓
┌───────────────────┐
│ TesseractBackend  │ ← Fallback (offline, free)
│ is_available()?   │
└─────────┬─────────┘
          │ No
          ↓
    Direct extraction only
```

### Key Concepts

**Block-Type Detection** (`detector.py`): Uses PyMuPDF's `block['type']` property:
- `type=0`: Text block
- `type=1`: Image block
- Page with `text_blocks >= 2` → text-dominant
- Page with `image_blocks >= 1` → image-dominant

**OCR Backend Pattern** (`backends/base.py`): All backends implement:
- `extract_text(file_path, page_number)` → `OCRResult`
- `is_available()` → bool
- `extract_document()` for batch processing

**Langdock OCR** (`backends/langdock.py`):
- Uploads PDF page as PNG to Langdock API
- Uses Claude Sonnet 4.5 for vision-based text extraction
- Returns markdown-formatted text with tables, headers preserved

**Tesseract OCR** (`backends/tesseract.py`):
- Local offline OCR using pytesseract
- Configurable languages (default: deu+eng)
- Good for simple documents, fallback when Langdock unavailable

**JSON Repair** (`json_repair.py`): LLM-generated JSON often has errors. Repair strategies:
1. Fix missing commas at error position
2. Pattern-match missing commas between properties
3. Remove trailing commas
4. Fix unescaped quotes

## Implementation Status

### Ready (Production)

| Component | File | Description |
|-----------|------|-------------|
| PDF Detector | `src/text_extraction/detector.py` | PDF type classification (PURE_TEXT/PURE_IMAGE/HYBRID) |
| Base Backend | `src/text_extraction/backends/base.py` | Abstract OCR backend interface |
| Langdock OCR | `src/text_extraction/backends/langdock.py` | LLM-based OCR via Claude Sonnet 4.5 |
| Tesseract OCR | `src/text_extraction/backends/tesseract.py` | Local offline OCR fallback |
| JSON Repair | `src/text_extraction/json_repair.py` | JSON error recovery utilities |
| Two-Pass Processor | `src/text_extraction/processor.py` | OCR routing with fallback support |
| Content Router | `src/text_extraction/router.py` | Page-level extraction routing with cost estimation |
| Data Models | `src/text_extraction/models.py` | Shared data models (ProcessorConfig, ExtractionResult) |
| FastAPI Service | `service/main.py` | REST API with /health, /classify, /extract |
| Docker | `Dockerfile`, `docker-compose.yml` | Multi-stage build with Tesseract |
| Terraform | `terraform/*.tf` | GCP Cloud Run deployment |
| CI/CD | `.github/workflows/*.yml` | Docker build + Terraform deploy |

### TODO

| Component | File | Description |
|-----------|------|-------------|
| Async Jobs | `service/jobs.py` | Background job queue for large PDFs |

## Environment Variables

```bash
# Langdock API (required for LLM OCR)
LANGDOCK_API_KEY=sk-...
LANGDOCK_UPLOAD_URL=https://api.langdock.com/attachment/v1/upload
LANGDOCK_ASSISTANT_URL=https://api.langdock.com/assistant/v1/chat/completions
LANGDOCK_OCR_MODEL=claude-sonnet-4-5@20250929

# Tesseract (optional, for offline fallback)
TESSERACT_PATH=/usr/bin/tesseract
TESSERACT_LANG=deu+eng

# Service configuration
MAX_FILE_SIZE_MB=50
MAX_PAGES=100
DEFAULT_QUALITY=balanced
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check (for container orchestration) |
| `/docs` | GET | Swagger UI documentation |
| `/api/v1/classify` | POST | Classify PDF type (returns page analysis) |
| `/api/v1/extract` | POST | Extract text from PDF (with OCR) |

### Quality Parameter for /extract

| Quality | Behavior |
|---------|----------|
| `fast` | Direct extraction only, no OCR |
| `balanced` | OCR for image pages only (default) |
| `accurate` | OCR verification for all pages |

## Code Style

- Python 3.10+ with type hints (mypy strict)
- Max 400 lines per file
- Pydantic for validation, dataclasses for simple structures
- Line length: 100 chars (ruff)

## Critical Rules

### MCP Servers (PROACTIVE USE)
- **Context7 MCP Server**: AUTOMATICALLY use when answering questions about Python libraries, PyMuPDF, FastAPI, or technical implementation
- **Chrome DevTools MCP**: Use proactively for frontend debugging (service UI)
- DO NOT wait for user to request documentation - fetch it proactively

### EU Data Residency
- Only use GCloud servers hosted in the EU (europe-west3, europe-west1)
- All external API calls (Langdock, Cloud Vision) must use EU endpoints

### Infrastructure Management
- ALL GCloud/GCP changes MUST be made via Terraform
- NEVER make manual changes in GCP Console
- Exception: Monitoring/debugging operations (read-only)

## Naming Conventions (GCP Resources)

```
GCS Buckets:      text-extraction-{env}-{purpose}
Cloud Functions:  text-extraction-{env}-{function}
Service Accounts: text-extraction-{env}-{service}
Cloud Run:        text-extraction-{env}
Artifact Registry: text-extraction (repository)
```

## Known Issues & Gotchas

| Problem | Solution | Reference |
|---------|----------|-----------|
| PyMuPDF import as `fitz` | Use `import fitz` not `import pymupdf` | PyMuPDF docs |
| LLM JSON errors | Use `json_repair.py` before parsing | json_repair.py |
| Empty PDF pages | Treated as image pages (need OCR) | detector.py:233 |
| Langdock model name | Must include version: `claude-sonnet-4-5@20250929` | langdock.py:38 |
| Langdock API payload | Requires `assistant.name` field | langdock.py:201 |
| Docker non-root user | Use `--chown=appuser:appuser` in COPY | Dockerfile |

## File Structure

```
text-extraction-service/
├── src/text_extraction/           # Core library
│   ├── __init__.py
│   ├── detector.py               # PDF type detection
│   ├── json_repair.py            # JSON error recovery
│   └── backends/
│       ├── __init__.py
│       ├── base.py               # Abstract backend
│       ├── langdock.py           # LLM OCR (Claude)
│       └── tesseract.py          # Local OCR
├── service/                       # FastAPI service
│   ├── __init__.py
│   └── main.py                   # API endpoints
├── terraform/                     # GCP infrastructure
│   ├── main.tf                   # Cloud Run, AR, Secrets
│   ├── variables.tf
│   ├── outputs.tf
│   └── backend.tf                # GCS state
├── .github/workflows/             # CI/CD
│   ├── docker-build.yml          # Build & push image
│   └── terraform-deploy.yml      # Plan & apply
├── tests/
├── Dockerfile                     # Multi-stage build
├── docker-compose.yml            # Local development
└── pyproject.toml
```

## Origin

Extracted from https://github.com/Unfuture/list-eingangsrechnungen (Issue #5)
