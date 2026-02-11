# Text Extraction Service

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

A standalone text extraction library and REST API service for PDF files with intelligent OCR routing.

## Features

- **PDF Type Detection**: Automatically classify PDFs as `PURE_TEXT`, `PURE_IMAGE`, or `HYBRID`
- **Multi-Backend OCR**: LLM OCR (Claude via Langdock, Gemini via Google API) + Tesseract fallback
- **Model-Based Routing**: `gemini-*` models route to Gemini API, others to Langdock
- **Intelligent Routing**: Route pages to the optimal extraction method
- **FastAPI Service**: REST API with Swagger documentation
- **Docker Ready**: Multi-stage build with Tesseract pre-installed
- **GCP Deployment**: Terraform for Cloud Run deployment

## Quick Start

### Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/Unfuture/text-extraction-service.git
cd text-extraction-service

# Configure environment
cp .env.example .env
# Edit .env and set LANGDOCK_API_KEY (optional, for OCR)

# Build and run
docker-compose up --build

# Test
curl http://localhost:1337/health
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev,service,tesseract]"

# Configure environment
cp .env.example .env

# Run service
uvicorn service.main:app --host 0.0.0.0 --port 1337 --reload

# Open Swagger docs
open http://localhost:1337/docs
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info and links |
| `/health` | GET | Health check (for container orchestration) |
| `/docs` | GET | Swagger UI documentation |
| `/api/v1/classify` | POST | Classify PDF type |
| `/api/v1/extract` | POST | Extract text from PDF |

### Classify PDF

```bash
curl -X POST "http://localhost:1337/api/v1/classify" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "success": true,
  "file_name": "document.pdf",
  "pdf_type": "HYBRID",
  "total_pages": 5,
  "text_pages": [1, 3, 5],
  "image_pages": [2, 4],
  "hybrid_pages": [],
  "confidence": 0.87,
  "processing_time_ms": 123.45
}
```

### Extract Text

```bash
curl -X POST "http://localhost:1337/api/v1/extract" \
  -F "file=@document.pdf" \
  -F "quality=balanced"
```

Quality options:
- `fast`: Direct extraction only, no OCR
- `balanced`: OCR for image pages only (default)
- `accurate`: OCR verification for all pages

Response:
```json
{
  "success": true,
  "file_name": "document.pdf",
  "pdf_type": "HYBRID",
  "total_pages": 5,
  "text": "--- Page 1 ---\nExtracted text...\n\n--- Page 2 (OCR: Langdock) ---\n...",
  "word_count": 1234,
  "confidence": 0.95,
  "processing_time_ms": 5678.90,
  "extraction_method": "hybrid (direct + Langdock)"
}
```

## Library Usage

```python
from text_extraction import PDFTypeDetector, PDFType

# Classify PDF
detector = PDFTypeDetector()
result = detector.classify_pdf("document.pdf")

print(f"Type: {result.pdf_type}")        # PURE_TEXT, PURE_IMAGE, or HYBRID
print(f"Confidence: {result.confidence}")  # 0.0 - 1.0
print(f"Text pages: {result.text_pages}")  # [1, 3, 5]
print(f"Image pages: {result.image_pages}")  # [2, 4]
```

### OCR Backends

```python
from text_extraction.backends import LangdockBackend, GeminiBackend, TesseractBackend
from pathlib import Path

# LLM-based OCR via Langdock (Claude, GPT models)
langdock = LangdockBackend()
if langdock.is_available():
    result = langdock.extract_text(Path("scan.pdf"), page_number=1)
    print(result.text)

# LLM-based OCR via Google Gemini (native multimodal)
gemini = GeminiBackend()
if gemini.is_available():
    result = gemini.extract_text(Path("scan.pdf"), page_number=1)
    print(result.text)

# Local OCR fallback (offline, free)
tesseract = TesseractBackend(lang="deu+eng")
if tesseract.is_available():
    result = tesseract.extract_text(Path("scan.pdf"), page_number=1)
    print(result.text)
```

## Configuration

### Environment Variables

```bash
# Langdock API (for Claude/GPT OCR via Langdock)
LANGDOCK_API_KEY=sk-your-api-key-here
LANGDOCK_UPLOAD_URL=https://api.langdock.com/attachment/v1/upload
LANGDOCK_ASSISTANT_URL=https://api.langdock.com/assistant/v1/chat/completions
LANGDOCK_OCR_MODEL=claude-sonnet-4-5@20250929

# Gemini API (for Google Gemini OCR)
GEMINI_API_KEY=your-gemini-api-key
GEMINI_OCR_MODEL=gemini-2.5-flash

# Tesseract (optional)
TESSERACT_PATH=/usr/bin/tesseract
TESSERACT_LANG=deu+eng

# Service configuration
MAX_FILE_SIZE_MB=50
MAX_PAGES=100
DEFAULT_QUALITY=balanced
```

## Project Structure

```
text-extraction-service/
├── src/text_extraction/           # Core library
│   ├── __init__.py
│   ├── detector.py               # PDF type detection
│   ├── json_repair.py            # JSON error recovery
│   └── backends/
│       ├── base.py               # Abstract backend
│       ├── langdock.py           # LLM OCR (Claude/GPT via Langdock)
│       ├── gemini.py             # LLM OCR (Gemini via Google API)
│       └── tesseract.py          # Local OCR
├── service/                       # FastAPI service
│   └── main.py                   # API endpoints
├── terraform/                     # GCP infrastructure
│   ├── main.tf                   # Cloud Run, Artifact Registry
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

## Deployment

### GCP Cloud Run (via Terraform)

1. **Prerequisites**:
   - GCP project with billing enabled
   - Workload Identity Federation configured for GitHub Actions
   - GCS bucket for Terraform state

2. **Configure GitHub Secrets**:
   ```
   GCP_PROJECT_ID       = your-gcp-project-id
   WIF_PROVIDER         = projects/123/locations/global/workloadIdentityPools/github/providers/github
   WIF_SERVICE_ACCOUNT  = github-actions@your-project.iam.gserviceaccount.com
   ```

3. **Deploy**:
   ```bash
   cd terraform
   terraform init
   terraform plan -var="project_id=your-project-id"
   terraform apply
   ```

4. **Set Langdock API Key**:
   ```bash
   echo -n "sk-your-api-key" | gcloud secrets versions add langdock-api-key-dev --data-file=-
   ```

### CI/CD Workflows

- **docker-build.yml**: Builds Docker image on push to `main`/`develop`, pushes to Artifact Registry
- **terraform-deploy.yml**: Plans on PR, applies on merge to `main`

## Development

### Run Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit -v

# With coverage
pytest --cov=src/text_extraction --cov-report=html
```

### Code Quality

```bash
# Linting
ruff check src/ service/

# Type checking
mypy src/

# Format
ruff format src/ service/
```

## OCR Backend Comparison

| Backend | Quality | Speed | Cost | Offline | EU Data Residency |
|---------|---------|-------|------|---------|-------------------|
| Langdock (Claude) | Excellent | ~25s/page | API costs | No | Yes (EU endpoint) |
| Gemini (Google) | Excellent | ~5s/page | API costs | No | No (Developer API) |
| Tesseract | Good | ~2s/page | Free | Yes | Yes (local) |

### Model-Based Routing

The service routes OCR requests based on the model name:
- `gemini-*` models (e.g. `gemini-2.5-flash`, `gemini-2.5-pro`) → **GeminiBackend**
- All other models (e.g. `claude-sonnet-4-5@20250929`) → **LangdockBackend**
- Fallback for both: **TesseractBackend** (if installed)

```bash
# Use Gemini for OCR
curl -X POST -F "file=@scan.pdf" -F "quality=balanced" \
  "http://localhost:1337/api/v1/extract?model=gemini-2.5-flash"

# Use Langdock/Claude for OCR (default)
curl -X POST -F "file=@scan.pdf" -F "quality=balanced" \
  http://localhost:1337/api/v1/extract
```

## Origin

This library was extracted from the [list-eingangsrechnungen](https://github.com/Unfuture/list-eingangsrechnungen) invoice processing system, where it achieved **100% success rate** on 42 test PDFs.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

Made with care by [Unfuture](https://unfuture.de)
