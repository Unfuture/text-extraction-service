# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Text Extraction Service is a Python library (with FastAPI wrapper) for extracting text from PDFs and images. Extracted from the `list-eingangsrechnungen` invoice processing system.

**Core capability**: Classify PDFs by content type (text/image/hybrid) and route pages to appropriate extraction methods including LLM-based OCR.

## Commands

```bash
# Install for development (all extras needed for local dev)
pip install -e ".[dev,service,tesseract]"

# Install with eval system
pip install -e ".[eval,dev]"

# Run all tests
pytest

# Run by marker (unit, integration, performance, regression, slow, api, eval)
pytest -m unit -v
pytest -m integration -v
pytest -m eval -v

# Run single test file
pytest tests/unit/test_detector.py -v

# Run with coverage
pytest --cov=src/text_extraction --cov-report=html

# Lint (include service/ and eval/ directories)
ruff check src/ service/ eval/

# Type check
mypy src/

# Format
ruff format src/ service/ eval/

# Test a PDF directly
python -m text_extraction.detector path/to/file.pdf

# Run FastAPI service locally
uvicorn service.main:app --host 0.0.0.0 --port 1337 --reload

# Docker development
docker-compose up --build

# Test API endpoints
curl http://localhost:1337/health
curl -X POST -F "file=@test.pdf" http://localhost:1337/api/v1/classify
curl -X POST -F "file=@test.pdf" -F "quality=balanced" http://localhost:1337/api/v1/extract

# Async extraction (for large PDFs)
curl -X POST -F "file=@large.pdf" -F "quality=balanced" http://localhost:1337/api/v1/extract/async
curl http://localhost:1337/api/v1/jobs/{job_id}
curl http://localhost:1337/api/v1/jobs/{job_id}/result

# OCR Evaluation System
python -m eval download                                      # Download all datasets
python -m eval download --dataset german_invoices             # Download one dataset
python -m eval run --limit 5 --backend direct --quality fast  # Quick test run
python -m eval run --limit 10                                 # All backends + qualities
python -m eval compare eval/output/a.json eval/output/b.json  # Compare reports
```

## Architecture

### Processing Pipeline

```
PDF Input → PDFTypeDetector.classify_pdf()   (detector.py)
                    ↓
         analyze_page() per page
         (count text blocks vs image blocks)
                    ↓
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
PURE_TEXT       HYBRID          PURE_IMAGE
    ↓               ↓               ↓
ContentRouter.create_routing_plan()          (router.py)
    ↓               ↓               ↓
DIRECT_ONLY    OCR_SELECTIVE    OCR_ALL
    ↓               ↓               ↓
TwoPassProcessor.process()                   (processor.py)
    ↓               ↓               ↓
Direct text    text→direct      LLM OCR
extraction     image→OCR        for all pages
```

The three core classes form a pipeline: **Detector** classifies, **Router** decides strategy + estimates cost, **Processor** executes extraction with fallback support.

### OCR Backend Selection (Model-Based Routing)

```
get_processor(model=...)
        ↓
model starts with "gemini-"?
    ↓ Yes                          ↓ No
GeminiBackend                  LangdockBackend
(google-genai SDK,             (Langdock API,
 ~5s/page)                      ~25s/page)
    ↓                              ↓
Fallback: TesseractBackend     Fallback: TesseractBackend
(~2s/page, free)               (~2s/page, free)
    ↓                              ↓
Last resort: Direct extraction only (no OCR)
```

### Key Concepts

**Block-Type Detection** (`detector.py`): Uses PyMuPDF's `block['type']` property:
- `type=0`: Text block, `type=1`: Image block
- Page with `text_blocks >= 2` → text-dominant
- Page with `image_blocks >= 1` → image-dominant
- Empty pages → treated as image pages (need OCR)

**OCR Backend Pattern** (`backends/base.py`): All backends implement `extract_text(file_path, page_number) → OCRResult`, `is_available() → bool`, and `extract_document()` for batch processing.

**Langdock OCR** (`backends/langdock.py`): Uploads PDF pages as PNG to Langdock API. Supports multiple models via `LANGDOCK_OCR_MODEL` env var: Claude (Sonnet 4.5, Opus 4.5/4.6), Gemini (2.5/3 Flash/Pro), GPT (5.1/5.2). Default: `claude-sonnet-4-5@20250929`. Returns markdown-formatted text preserving tables and headers.

**Gemini OCR** (`backends/gemini.py`): Uses Google Gemini API via `google-genai` SDK. Converts PDF pages to PIL Images and sends directly (no base64 needed). Has tenacity retry logic for rate limits (5 attempts, exponential backoff). Free Tier limits: Flash 20 req/day, Pro 0 req/day.

**Content Router** (`router.py`): Maps quality levels to routing strategies (DIRECT_ONLY/OCR_SELECTIVE/OCR_ALL). Provides cost estimation in EUR and time estimates.

**Lazy Backend Initialization**: `service/main.py` initializes OCR backends lazily on first request, not at startup. This means the service starts fast even without API keys configured.

**Async Job Queue** (`service/jobs.py`): For large PDFs (50+ pages), use the async endpoint to avoid HTTP timeouts. Jobs run in background threads via `asyncio.run_in_executor`. Uses `InMemoryJobStore` (development); extend with `RedisJobStore` for production persistence. Jobs expire after 24 hours. Optional webhook notifications via `callback_url` parameter.

**JSON Repair** (`json_repair.py`): Fixes common LLM JSON errors: missing commas, trailing commas, unescaped quotes. Always use this before parsing LLM-generated JSON.

### Quality Levels for /api/v1/extract

| Quality | Strategy | Behavior |
|---------|----------|----------|
| `fast` | DIRECT_ONLY | Direct text extraction only, no OCR |
| `balanced` | OCR_SELECTIVE | OCR for image pages only (default) |
| `accurate` | OCR_ALL | OCR verification for all pages |

## Testing

Tests create PDFs programmatically via fixtures in `tests/conftest.py` - no actual PDF files are committed to the repo. Available pytest markers: `unit`, `integration`, `performance`, `regression`, `slow`, `api`, `eval`. Uses `pytest-asyncio` with `asyncio_mode = "auto"`.

## OCR Evaluation System

### Overview

The `eval/` package is an independent benchmarking framework for comparing OCR backends and quality levels using real-world datasets and standardized metrics (CER, WER, assertion-based). It is **not** part of the `text_extraction` library — it's a standalone tool with its own CLI and dependencies.

### Architecture

```
eval/
├── __init__.py              # Package init, public exports
├── __main__.py              # CLI: python -m eval {download,run,compare}
├── config.py                # EvalConfig, DatasetConfig dataclasses
├── models.py                # EvalSample, GroundTruth, EvalResult, BenchmarkReport
├── metrics.py               # CER, WER, Jaccard, TokensFound/Added, TSR, ANLS*, assertions
├── runner.py                # EvalRunner — orchestrates evaluation
├── processor_factory.py     # Backend processor creation (extracted from runner.py)
├── llm_judge.py             # LLM-as-Judge evaluation via Langdock API
├── datasets/
│   ├── __init__.py          # Registry: DATASET_REGISTRY, get_adapter(), download_all()
│   ├── base.py              # DatasetAdapter ABC + convert_image_to_pdf() helper
│   ├── german_invoices.py   # Aoschu/German_invoices_dataset (97 samples, CER/WER)
│   ├── olmocr_bench.py      # allenai/olmOCR-bench (1403 PDFs, assertion-based)
│   └── ocr_benchmark.py     # getomni-ai/ocr-benchmark (text + JSON accuracy)
├── reports/
│   ├── __init__.py
│   ├── json_report.py       # Timestamped JSON output to eval/output/
│   └── console_report.py    # Terminal table + report comparison
tests/eval/
└── test_eval_metrics.py     # 51 tests for all metric functions (@pytest.mark.eval)
```

### Evaluation Pipeline

```
python -m eval download
        ↓
HuggingFace datasets → local PDFs + ground truth (eval/data/)
        ↓
python -m eval run
        ↓
EvalRunner.run()
    ↓ for each dataset
    DatasetAdapter.load_samples() → list[EvalSample]
        ↓ for each sample × backend × quality
        TwoPassProcessor.extract(pdf, quality) → ExtractionResult
            ↓
        Compute metrics based on GroundTruth type:
            full_text → CER, WER, Jaccard, TokensFound, TokensAdded, TSR
            must_contain/must_not_contain → pass/fail assertions (rapidfuzz)
            fields → field_accuracy + ANLS* (partial credit)
        ↓
BenchmarkReport → Console table + JSON file (eval/output/)
```

### Datasets

| Dataset | Source | Samples | Ground Truth Type | Metrics |
|---------|--------|---------|-------------------|---------|
| `german_invoices` | Aoschu/German_invoices_dataset | 97 | `full_text` (transcriptions) | CER, WER, Jaccard, TknF, TknA, TSR |
| `olmocr_bench` | allenai/olmOCR-bench | 1403 | `must_contain` / `must_not_contain` | Pass rate (rapidfuzz) |
| `ocr_benchmark` | getomni-ai/ocr-benchmark | ~1000 | `full_text` + `fields` (JSON) | CER, WER, TknF, TknA, TSR, field accuracy, ANLS* |

### Unified Ground Truth Format

```python
@dataclass
class GroundTruth:
    full_text: str | None = None              # For CER/WER (German Invoices, OCR Benchmark)
    fields: dict[str, str] | None = None      # For field accuracy (OCR Benchmark)
    must_contain: list[str] | None = None     # For pass/fail (olmOCR-bench)
    must_not_contain: list[str] | None = None # For pass/fail (olmOCR-bench)
```

### Metrics (eval/metrics.py)

| Function | Input | Output | Library |
|----------|-------|--------|---------|
| `calculate_cer(extracted, reference)` | Two strings | 0.0 (perfect) - 1.0+ | jiwer |
| `calculate_wer(extracted, reference)` | Two strings | 0.0 (perfect) - 1.0+ | jiwer |
| `calculate_jaccard(extracted, reference)` | Two strings | 0.0 - 1.0 (word overlap) | built-in |
| `calculate_tokens_found(extracted, reference)` | Two strings | 0.0 - 1.0 (content recall) | built-in |
| `calculate_tokens_added(extracted, reference)` | Two strings | 0.0 - 1.0 (hallucination rate) | built-in |
| `calculate_token_set_ratio(extracted, reference)` | Two strings | 0.0 - 1.0 (order-independent) | rapidfuzz |
| `check_assertions(text, must_contain, must_not_contain)` | Text + assertion lists | (bool, failures) | rapidfuzz |
| `calculate_field_accuracy(extracted, expected)` | Two dicts | 0.0 - 1.0 (exact match) | built-in |
| `calculate_anls_star(extracted, expected)` | Two dicts | 0.0 - 1.0 (partial credit) | anls-star |

All metrics normalize text first (lowercase, markdown stripping, German thousands dots, whitespace collapse, strip).

### LLM-as-Judge (eval/llm_judge.py)

Optional metric activated with `--metrics llm_judge`. Uses Langdock API to evaluate on 4 dimensions (0-10 each): completeness, accuracy, structure, hallucination. Costs API tokens per sample. Configure judge model via `LANGDOCK_JUDGE_MODEL` env var (default: `gemini-2.5-flash`).

### CLI Usage

```bash
# Download datasets
python -m eval download                          # All 3 datasets
python -m eval download --dataset german_invoices # Single dataset
python -m eval download --data-dir /custom/path   # Custom location

# Run evaluation
python -m eval run --limit 5                      # Quick: 5 samples, all backends
python -m eval run --backend direct --quality fast # Direct extraction only
python -m eval run --backend langdock --quality balanced --limit 10
python -m eval run --dataset german_invoices --dataset olmocr_bench
python -m eval run --metrics llm_judge --limit 5  # With LLM-as-Judge (costs tokens)

# Compare reports
python -m eval compare eval/output/eval_A.json eval/output/eval_B.json
```

### Benchmark Results (2026-02-09)

Evaluation on 10 German invoices (scanned images), `balanced` quality, all via Langdock API:

| Modell | CER ↓ | WER ↓ | Jaccard ↑ | Avg Time | Bemerkung |
|--------|-------|-------|-----------|----------|-----------|
| **Gemini 3 Pro** (`gemini-3-pro-preview`) | **35.5%** | **66.1%** | **0.58** | 35.3s | Beste Qualität, aber langsam |
| Claude Opus 4.6 (`claude-opus-4-6@default`) | 38.8% | 74.6% | 0.45 | 13.7s | Schnell, aber niedrigster Jaccard |
| Gemini 3 Flash (`gemini-3-flash-preview`) | 39.3% | 70.1% | 0.55 | 13.5s | Bestes Preis-Leistungs-Verhältnis |
| Claude Sonnet 4.5 (`claude-sonnet-4-5@20250929`) | 40.7% | 68.7% | 0.55 | 14.6s | Solide, bisheriger Default |

**Hinweise zu den Metriken:**
- CER/WER sind relativ hoch weil die Ground Truth des Datasets selbst OCR-Artefakte enthält (z.B. `PaufhunglMayeholerlesi234SFeberg` statt einer echten Adresse)
- Jaccard misst Wort-Overlap unabhängig von Reihenfolge -- niedrigere Werte deuten auf Halluzinationen oder starke Formatierungsabweichungen hin
- Gemini 3 Pro/Flash können **nicht** über die direkte Gemini API (Free Tier) genutzt werden (`limit: 0`), nur über Langdock oder Paid Tier

**Verfügbare Modelle via Langdock API:**
`claude-sonnet-4-5@20250929`, `claude-opus-4-5@20251101`, `claude-opus-4-6@default`, `claude-haiku-4-5@20251001`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3-pro-preview`, `gemini-3-flash-preview`, `gpt-5.1`, `gpt-5.2`, `gpt-5.2-pro`, `gpt-5-mini-eu`

### Cost Control

- `--limit N` flag limits samples per dataset (default: 10)
- Use `--backend direct --quality fast` for zero-cost runs
- Langdock/Gemini backends incur API costs per page
- Gemini Free Tier: 20 requests/day for Flash models, 0 for Pro models

### Dependencies

Installed via `pip install -e ".[eval]"`:
- `datasets` — HuggingFace dataset loading
- `jiwer` — CER/WER calculation
- `rapidfuzz` — Fuzzy string matching (token_set_ratio, partial_ratio for assertions)
- `anls-star` — ANLS* metric for partial-credit field comparison
- `tabulate` — Console table formatting
- `tqdm` — Progress bars
- `pillow` — Image handling for image→PDF conversion

## Environment Variables

See `.env.example` for all required variables. Key ones:

```bash
LANGDOCK_API_KEY=sk-...                    # Required for LLM OCR via Langdock
LANGDOCK_OCR_MODEL=claude-sonnet-4-5@20250929  # Default; see benchmark for alternatives
GEMINI_API_KEY=AIza...                     # Required for direct Gemini OCR (Free Tier: 20 req/day Flash, 0 Pro)
GEMINI_OCR_MODEL=gemini-2.5-flash          # Default Gemini model (direct API)
```

**Model override for eval runs:**
```bash
LANGDOCK_OCR_MODEL=gemini-3-pro-preview python -m eval run --backend langdock --limit 10
LANGDOCK_OCR_MODEL=claude-opus-4-6@default python -m eval run --backend langdock --limit 10
```

## Code Style

- Python 3.10+ with type hints (mypy strict)
- Max 400 lines per file - split if exceeded
- Pydantic for validation, dataclasses for simple structures
- Line length: 100 chars (ruff)
- Build system: hatchling

## Critical Rules

### MCP Servers (PROACTIVE USE)
- **Context7 MCP Server**: AUTOMATICALLY use when answering questions about Python libraries, PyMuPDF, FastAPI, or technical implementation
- **Chrome DevTools MCP**: Use proactively for frontend debugging (service UI)
- DO NOT wait for user to request documentation - fetch it proactively

### EU Data Residency
- Only use GCloud servers hosted in the EU (europe-west3, europe-west1)
- All external API calls (Langdock, Cloud Vision) must use EU endpoints
- **Gemini Developer API**: No dedicated EU endpoint available. For strict EU data residency, use Vertex AI instead. Current setup uses Developer API key directly.

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
| PyMuPDF import name | Use `import fitz` not `import pymupdf` | PyMuPDF docs |
| LLM JSON errors | Use `json_repair.py` before parsing | json_repair.py |
| Empty PDF pages | Treated as image pages (need OCR) | detector.py |
| Langdock model name | Must include version: `claude-sonnet-4-5@20250929` | langdock.py:38 |
| Langdock API payload | Requires `assistant.name` field | langdock.py:201 |
| Docker non-root user | Use `--chown=appuser:appuser` in COPY | Dockerfile |
| Gemini Developer API | No dedicated EU endpoint; for strict EU residency use Vertex AI | gemini.py |
| Gemini model routing | Models starting with `gemini-` are auto-routed to GeminiBackend | service/main.py |
| Eval package import | Use `from eval.X import Y`, not `from text_extraction.eval` | eval/__init__.py |
| olmOCR-bench download | Uses `huggingface_hub.snapshot_download` (Git LFS, ~357MB) | olmocr_bench.py |
| Image→PDF conversion | German Invoices + OCR Benchmark convert images via `convert_image_to_pdf()` | datasets/base.py |
| Eval data not committed | `eval/data/`, `eval/results/`, `eval/output/` are gitignored | .gitignore |
| German Invoices ground truth | HF dataset stores transcriptions as Python list strings; adapter parses with `ast.literal_eval` | german_invoices.py |
| Gemini Free Tier limits | Flash: 20 req/day, Pro: 0 req/day. Use Langdock API for Pro models | gemini.py |
| Gemini 429 retries | GeminiBackend has tenacity retry (5 attempts, exponential backoff 5-60s) | gemini.py |
| Eval page headers | `strip_page_headers()` removes `--- Page N ---` markers before metric comparison | metrics.py |
| Langdock model names | Must match exactly; use error response to discover available models | langdock.py |
| Async jobs in-memory | Jobs lost on restart; use Redis-backed store for production | service/jobs.py |
| Async progress granularity | Only 0/10/100% - TwoPassProcessor has no per-page callback | service/jobs.py |

## TODO

- Redis-backed JobStore for production async job persistence
- Eval: CI integration with baseline regression check
- Eval: Test with olmOCR-bench and ocr-benchmark datasets
- Eval: Run full 97-sample evaluation on German invoices (currently limited to 10)
- Eval: Add `--model` CLI flag to override model per-run without env vars

## Origin

Extracted from https://github.com/Unfuture/list-eingangsrechnungen (Issue #5)
