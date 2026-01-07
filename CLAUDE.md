# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Text Extraction Service** is a standalone library and optional API service for extracting text from PDF and image files. It was extracted from the `list-eingangsrechnungen` invoice processing system.

## Key Features

- **PDF Type Detection**: Classify PDFs as PURE_TEXT, PURE_IMAGE, HYBRID using PyMuPDF block detection
- **Two-Pass OCR**: LLM-based OCR for scanned documents (Claude Sonnet 4.5 / GPT-4o)
- **Multi-Backend Support**: Langdock (LLM), Tesseract (local), Cloud Vision (GCP)
- **Optional FastAPI Service**: REST API wrapper for the library

## Project Structure

```
text-extraction-service/
├── src/text_extraction/      # Core library
│   ├── detector.py           # PDF Type Detection (from list-eingangsrechnungen)
│   ├── processor.py          # Two-Pass OCR Processor (TODO)
│   ├── router.py             # Content Router (TODO)
│   ├── json_repair.py        # JSON error recovery
│   └── backends/             # OCR Backend implementations
│       ├── base.py           # BaseOCRBackend abstract class
│       ├── langdock.py       # Langdock LLM backend (TODO)
│       └── tesseract.py      # Local Tesseract (TODO)
├── service/                  # FastAPI service wrapper (TODO)
├── tests/                    # Test suites
├── docs/                     # Architecture documentation
├── examples/                 # Original code from list-eingangsrechnungen
└── pyproject.toml            # Package configuration
```

## Development Guidelines

### Code Style
- Python 3.10+ with type hints
- Maximum 400 lines per file
- Use Pydantic for data validation
- Use dataclasses for simple data structures

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/text_extraction --cov-report=html

# Run specific test category
pytest -m unit
pytest -m integration
```

### Package Installation
```bash
# Development install
pip install -e ".[dev]"

# With all optional dependencies
pip install -e ".[all]"
```

## Key Files

### Core Implementation
| File | Purpose | Status |
|------|---------|--------|
| `src/text_extraction/detector.py` | PDF Type Detection using PyMuPDF | ✅ Ready |
| `src/text_extraction/backends/base.py` | Abstract OCR backend class | ✅ Ready |
| `src/text_extraction/json_repair.py` | JSON error recovery utilities | ✅ Ready |
| `src/text_extraction/processor.py` | Two-Pass OCR logic | 📋 TODO |
| `src/text_extraction/backends/langdock.py` | Langdock LLM backend | 📋 TODO |
| `src/text_extraction/backends/tesseract.py` | Local Tesseract backend | 📋 TODO |

### Reference Code (examples/)
Original implementations from list-eingangsrechnungen for reference:
- `examples/two_pass_ocr_processor_original.py`
- `examples/langdock_inline_client_original.py`
- `examples/assistant_config_original.py`

## API Design

### Library Usage
```python
from text_extraction import PDFTypeDetector, PDFType

detector = PDFTypeDetector()
result = detector.classify_pdf("document.pdf")
# result.pdf_type: PURE_TEXT | PURE_IMAGE | HYBRID
# result.confidence: 0.0 - 1.0
```

### Service Usage (TODO)
```
POST /api/v1/extract
POST /api/v1/extract/async
GET /api/v1/jobs/{id}
GET /api/v1/health
```

## Dependencies

### Core
- `pymupdf>=1.23.0` - PDF processing
- `requests>=2.28.0` - HTTP client
- `pydantic>=2.0.0` - Data validation
- `tenacity>=8.0.0` - Retry logic

### Optional
- `fastapi>=0.104.0` - API service
- `pytesseract>=0.3.10` - Local OCR fallback

## Origin

Extracted from https://github.com/Unfuture/list-eingangsrechnungen
- Issue: https://github.com/Unfuture/list-eingangsrechnungen/issues/5
- Original success rate: 100% (42/42 PDFs)

## Environment Variables

```bash
# Langdock API
LANGDOCK_API_KEY=sk-...
LANGDOCK_MODEL=claude-sonnet-4-5

# Tesseract
TESSERACT_PATH=/usr/bin/tesseract
TESSERACT_LANG=deu+eng
```
