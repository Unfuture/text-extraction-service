# Text Extraction Service - Quick Reference

## Implementation Status (Updated 2026-01-08)

| Component | File | Status |
|-----------|------|--------|
| PDFTypeDetector | `detector.py` | ✅ DONE |
| BaseOCRBackend | `backends/base.py` | ✅ DONE |
| LangdockBackend | `backends/langdock.py` | ✅ DONE |
| GeminiBackend | `backends/gemini.py` | ✅ DONE |
| TesseractBackend | `backends/tesseract.py` | ✅ DONE |
| JSON Repair | `json_repair.py` | ✅ DONE |
| FastAPI Service | `service/main.py` | ✅ DONE |
| Docker Setup | `Dockerfile` | ✅ DONE |
| Docker Compose | `docker-compose.yml` | ✅ DONE |
| Terraform (GCP) | `terraform/*.tf` | ✅ DONE |
| CI/CD Workflows | `.github/workflows/*.yml` | ✅ DONE |
| TwoPassProcessor | `processor.py` | ⏳ TODO |
| ContentRouter | `router.py` | ⏳ TODO |
| Async Job Queue | `service/jobs.py` | ⏳ TODO |

---

## Quick Start Commands

### Docker (Recommended)

```bash
# Build and run
docker-compose up --build

# Test endpoints
curl http://localhost:1337/health
curl -X POST -F "file=@test.pdf" http://localhost:1337/api/v1/classify
curl -X POST -F "file=@test.pdf" http://localhost:1337/api/v1/extract
```

### Local Development

```bash
# Install
pip install -e ".[dev,service,tesseract]"

# Run service
uvicorn service.main:app --host 0.0.0.0 --port 1337 --reload

# Run tests
pytest
pytest --cov=src/text_extraction --cov-report=html
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |
| `/api/v1/classify` | POST | Classify PDF type |
| `/api/v1/extract` | POST | Extract text with OCR |

### Extract Quality Options

| Quality | Behavior |
|---------|----------|
| `fast` | Direct extraction only, no OCR |
| `balanced` | OCR for image pages only (default) |
| `accurate` | OCR verification for all pages |

---

## Environment Variables

```bash
# Langdock API (for Claude/GPT OCR)
LANGDOCK_API_KEY=sk-...
LANGDOCK_UPLOAD_URL=https://api.langdock.com/attachment/v1/upload
LANGDOCK_ASSISTANT_URL=https://api.langdock.com/assistant/v1/chat/completions
LANGDOCK_OCR_MODEL=claude-sonnet-4-5@20250929

# Gemini API (for Google Gemini OCR)
GEMINI_API_KEY=AIza...
GEMINI_OCR_MODEL=gemini-2.5-flash

# Tesseract (optional)
TESSERACT_PATH=/usr/bin/tesseract
TESSERACT_LANG=deu+eng

# Service configuration
MAX_FILE_SIZE_MB=50
MAX_PAGES=100
DEFAULT_QUALITY=balanced
```

---

## File Locations

### Source Files

| File | Purpose |
|------|---------|
| `src/text_extraction/detector.py` | PDF type detection |
| `src/text_extraction/backends/base.py` | Abstract OCR backend |
| `src/text_extraction/backends/langdock.py` | LLM OCR via Claude/GPT (Langdock) |
| `src/text_extraction/backends/gemini.py` | LLM OCR via Google Gemini |
| `src/text_extraction/backends/tesseract.py` | Local OCR fallback |
| `src/text_extraction/json_repair.py` | JSON error recovery |
| `service/main.py` | FastAPI REST API |

### Infrastructure Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage Docker build |
| `docker-compose.yml` | Local development |
| `terraform/main.tf` | GCP Cloud Run deployment |
| `terraform/variables.tf` | Terraform variables |
| `.github/workflows/docker-build.yml` | CI: Build & push image |
| `.github/workflows/terraform-deploy.yml` | CD: Deploy to GCP |

### Documentation

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Claude Code guidance |
| `README.md` | User documentation |
| `docs/TEXT_EXTRACTION_SERVICE_ARCHITECTURE.md` | Architecture design |
| `docs/QUICK_REFERENCE.md` | This file |

---

## OCR Backend Selection (Model-Based Routing)

```
get_processor(model=...)
        │
        ▼
model starts with "gemini-"?
    │ Yes                          │ No
    ▼                              ▼
┌───────────────────┐   ┌───────────────────┐
│ GeminiBackend     │   │ LangdockBackend   │
│ (Google Gemini)   │   │ (Claude/GPT)      │
└─────────┬─────────┘   └─────────┬─────────┘
          │                       │
          ▼                       ▼
┌───────────────────┐   ┌───────────────────┐
│ TesseractBackend  │   │ TesseractBackend  │
│ (Fallback)        │   │ (Fallback)        │
└─────────┬─────────┘   └─────────┬─────────┘
          │                       │
          ▼                       ▼
    Direct extraction only
```

### Backend Comparison

| Backend | Quality | Speed | Cost | Offline | EU Data Residency |
|---------|---------|-------|------|---------|-------------------|
| Langdock (Claude) | Excellent | ~25s/page | API | No | Yes |
| Gemini (Google) | Excellent | ~5s/page | API | No | No |
| Tesseract | Good | ~2s/page | Free | Yes | Yes |

---

## CI/CD Workflows

### docker-build.yml

**Triggers**: Push to `main`/`develop`, PR to `main`

**Jobs**:
1. `lint-test`: Run ruff, pytest
2. `build`: Build Docker image, push to Artifact Registry
3. `test-container`: Health check deployed container
4. `notify`: Create summary

**Required GitHub Variables**:
```
GCP_PROJECT_ID
WIF_PROVIDER
WIF_SERVICE_ACCOUNT
```

### terraform-deploy.yml

**Triggers**: Push to `main` (terraform/), PR

**Jobs**:
1. `validate`: Format check, terraform validate
2. `plan`: Generate and upload plan, comment on PR
3. `apply`: Apply changes (main only)
4. `health-check`: Verify Cloud Run service
5. `notify`: Create summary

---

## Code Examples

### Classify PDF

```python
from text_extraction import PDFTypeDetector, PDFType

detector = PDFTypeDetector()
result = detector.classify_pdf("document.pdf")

print(f"Type: {result.pdf_type}")  # PURE_TEXT, PURE_IMAGE, HYBRID
print(f"Text pages: {result.text_pages}")
print(f"Image pages: {result.image_pages}")
```

### Use OCR Backend

```python
from text_extraction.backends import LangdockBackend, GeminiBackend, TesseractBackend
from pathlib import Path

# LLM OCR via Langdock
langdock = LangdockBackend()
if langdock.is_available():
    result = langdock.extract_text(Path("scan.pdf"), page_number=1)
    print(result.text)

# LLM OCR via Gemini
gemini = GeminiBackend()
if gemini.is_available():
    result = gemini.extract_text(Path("scan.pdf"), page_number=1)
    print(result.text)

# Local OCR
tesseract = TesseractBackend()
if tesseract.is_available():
    result = tesseract.extract_text(Path("scan.pdf"), page_number=1)
    print(result.text)
```

### Custom Backend Template

```python
from text_extraction.backends.base import BaseOCRBackend, OCRResult, ExtractionMethod
from pathlib import Path
from typing import Optional

class CustomBackend(BaseOCRBackend):
    def __init__(self):
        super().__init__(name="CustomBackend")

    def is_available(self) -> bool:
        return True

    def extract_text(
        self,
        file_path: Path,
        page_number: Optional[int] = None,
        **kwargs
    ) -> OCRResult:
        # Your implementation
        return OCRResult(
            text="extracted text",
            confidence=0.95,
            method=ExtractionMethod.CUSTOM,
            page_number=page_number
        )
```

---

## Known Issues & Gotchas

| Problem | Solution |
|---------|----------|
| PyMuPDF import | Use `import fitz` not `import pymupdf` |
| Langdock model name | Must include version: `claude-sonnet-4-5@20250929` |
| Langdock API payload | Requires `assistant.name` field |
| Gemini Developer API | No dedicated EU endpoint; use Vertex AI for strict EU residency |
| Gemini model routing | Models starting with `gemini-` auto-route to GeminiBackend |
| Docker non-root | Use `--chown=appuser:appuser` in COPY |
| Empty PDF pages | Treated as image pages (need OCR) |

---

## Success Criteria

- [x] PDFTypeDetector working (99%+ accuracy)
- [x] LangdockBackend fully functional
- [x] GeminiBackend fully functional (model-based routing)
- [x] TesseractBackend working as fallback
- [x] FastAPI service with /health, /classify, /extract
- [x] Docker build working
- [x] CI/CD pipelines ready
- [ ] TwoPassProcessor implementation
- [ ] Test coverage >= 90%
- [ ] Async job queue for large PDFs

---

*Quick Reference Version: 2.0*
*Last Updated: 2026-01-08*
