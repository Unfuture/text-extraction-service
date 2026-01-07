# Text Extraction Service

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A standalone text extraction library and service for PDF and image files with intelligent OCR routing.

## Features

- **PDF Type Detection**: Automatically classify PDFs as `PURE_TEXT`, `PURE_IMAGE`, or `HYBRID`
- **Two-Pass OCR Strategy**: Optimized extraction for scanned documents
- **Multi-Backend Support**: LLM OCR (Claude, GPT-4o), Tesseract, Cloud Vision
- **Intelligent Routing**: Route pages to the optimal extraction method
- **Structured Output**: JSON responses with confidence scores
- **GDPR Compliant**: No persistent storage, configurable data retention

## Installation

### As a Library

```bash
pip install text-extraction
```

### With Optional Dependencies

```bash
# With FastAPI service
pip install text-extraction[service]

# With Tesseract fallback
pip install text-extraction[tesseract]

# Full installation
pip install text-extraction[all]
```

### From Source

```bash
git clone https://github.com/Unfuture/text-extraction-service.git
cd text-extraction-service
pip install -e ".[dev]"
```

## Quick Start

### PDF Classification

```python
from text_extraction import PDFTypeDetector, PDFType

detector = PDFTypeDetector()
result = detector.classify_pdf("invoice.pdf")

print(f"Type: {result.pdf_type}")        # PURE_TEXT, PURE_IMAGE, or HYBRID
print(f"Confidence: {result.confidence}")  # 0.0 - 1.0
print(f"Text pages: {result.text_pages}")  # [1, 3, 5]
print(f"Image pages: {result.image_pages}")  # [2, 4]
```

### Text Extraction (Coming Soon)

```python
from text_extraction import TextExtractor
from text_extraction.backends import LangdockBackend

extractor = TextExtractor(
    backend=LangdockBackend(api_key="...")
)

result = extractor.extract("document.pdf")
print(result.text)
```

## API Service

### Run the Service

```bash
# Using uvicorn
uvicorn text_extraction.service:app --host 0.0.0.0 --port 8000

# Using Docker
docker-compose up -d
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/extract` | POST | Synchronous text extraction |
| `/api/v1/extract/async` | POST | Async extraction (large files) |
| `/api/v1/jobs/{id}` | GET | Get async job status |
| `/api/v1/health` | GET | Health check |

### Example Request

```bash
curl -X POST "http://localhost:8000/api/v1/extract" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf" \
  -F "options={\"quality_preference\": \"balanced\"}"
```

### Example Response

```json
{
  "success": true,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_name": "document.pdf",
  "classification": {
    "type": "HYBRID",
    "confidence": 0.87,
    "total_pages": 5
  },
  "pages": [
    {
      "page_number": 1,
      "text": "Extracted text content...",
      "extraction_method": "direct",
      "confidence": 1.0,
      "word_count": 245
    }
  ],
  "metadata": {
    "processing_time_ms": 2340,
    "backend_used": "langdock"
  }
}
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              text-extraction (pip package)                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Core Modules                                            │    │
│  │  ├── detector.py     (PDF Type Detection)               │    │
│  │  ├── processor.py    (Two-Pass OCR)                     │    │
│  │  └── backends/       (Langdock, Tesseract, CloudVision) │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │   Direct Usage  │             │  Service Mode   │
    │   (pip import)  │             │  (FastAPI)      │
    └─────────────────┘             └─────────────────┘
```

## Configuration

### Environment Variables

```bash
# Langdock API (primary OCR backend)
LANGDOCK_API_KEY=sk-...
LANGDOCK_MODEL=claude-sonnet-4-5

# Tesseract (fallback)
TESSERACT_PATH=/usr/bin/tesseract
TESSERACT_LANG=deu+eng

# Service configuration
MAX_FILE_SIZE_MB=50
MAX_PAGES=100
DEFAULT_QUALITY=balanced
```

### Quality Preferences

| Quality | Description | Speed | Cost |
|---------|-------------|-------|------|
| `fast` | Direct extraction only, no LLM | Fastest | Lowest |
| `balanced` | LLM for image pages only | Medium | Medium |
| `accurate` | LLM verification for all pages | Slowest | Highest |

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/Unfuture/text-extraction-service.git
cd text-extraction-service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dev dependencies
pip install -e ".[dev]"
```

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
ruff check src/

# Type checking
mypy src/

# Format
ruff format src/
```

## Project Structure

```
text-extraction-service/
├── src/
│   └── text_extraction/
│       ├── __init__.py       # Public API
│       ├── detector.py       # PDF Type Detection
│       ├── processor.py      # Two-Pass OCR (TODO)
│       ├── router.py         # Content Router (TODO)
│       ├── json_repair.py    # JSON error recovery
│       ├── schemas.py        # Pydantic models (TODO)
│       └── backends/
│           ├── base.py       # BaseOCRBackend
│           ├── langdock.py   # LLM OCR (TODO)
│           └── tesseract.py  # Local OCR (TODO)
├── service/                  # FastAPI service (TODO)
│   ├── main.py
│   └── routes/
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   ├── TEXT_EXTRACTION_SERVICE_ARCHITECTURE.md
│   └── TEXT_EXTRACTION_DECISION_MATRIX.md
├── examples/                 # Original code from list-eingangsrechnungen
├── pyproject.toml
└── README.md
```

## Origin

This library was extracted from the [list-eingangsrechnungen](https://github.com/Unfuture/list-eingangsrechnungen) invoice processing system, where it achieved **100% success rate** on 42 test PDFs.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

Made with ❤️ by [Unfuture](https://unfuture.de)
