# Issue #7 - Implementation Log

**GitHub**: https://github.com/Unfuture/text-extraction-service/issues/7
**Started**: 2026-02-11
**Status**: Complete - Fixed critical retry bug, all requirements verified

## Implementation Steps

1. Verified `GeminiBackend` implementation in `src/text_extraction/backends/gemini.py` (203 lines)
2. Verified 19 unit tests in `tests/unit/test_backends_gemini.py` (all passing)
3. Verified `pyproject.toml` has `gemini` optional dependency group
4. Verified `backends/__init__.py` exports `GeminiBackend`
5. Verified model-based routing in `service/main.py` (`_is_gemini_model()` + `get_processor()`)
6. Verified `.env.example` includes `GEMINI_API_KEY` and `GEMINI_OCR_MODEL`
7. **QA Review**: Found critical retry bug - fixed with `GeminiRetryableError`
8. Added 2 retry behavior tests (21 total)
9. Final: 208/208 unit tests passing, ruff clean

## Key Changes

### Logic/Workflow Changes
- New `GeminiBackend` class extending `BaseOCRBackend` with:
  - `google-genai` SDK for native multimodal content generation
  - Direct PIL Image support (no base64 encoding)
  - Lazy client initialization (`_get_client()`)
  - Tenacity retry for rate limits only (5 attempts, exponential backoff 5-60s)
- `GeminiRetryableError` for retry-specific error handling (matches `LangdockRetryableError` pattern)
- Model-based routing: `gemini-*` models -> GeminiBackend, others -> LangdockBackend
- Fallback chain: GeminiBackend -> TesseractBackend -> direct extraction

### Infrastructure/Configuration
- `pyproject.toml`: Added `gemini` optional dependency group
- `.env.example`: Added `GEMINI_API_KEY`, `GEMINI_OCR_MODEL`

### Permission/Security Updates
- EU Data Residency: Gemini Developer API has no dedicated EU endpoint
  - Documented as known limitation in CLAUDE.md
  - Recommendation: Use Vertex AI for strict EU compliance

## Attempted Solutions

### Retry Logic (BUG-1 - Critical)
- **Problem**: Original `@retry(retry=retry_if_exception_type(Exception))` retried ALL errors including auth failures (401), bad requests (400), making non-transient errors wait up to ~2.5 minutes
- **Fix**: Created `GeminiRetryableError` class, only wrap 429/RESOURCE_EXHAUSTED errors, matching the `LangdockRetryableError` pattern from langdock.py

## Verification Results

| Check | Result |
|-------|--------|
| Unit tests (21 Gemini) | 21/21 PASSED |
| Unit tests (all 208) | 208/208 PASSED |
| Ruff lint | Clean |
| Backend export | GeminiBackend + GeminiRetryableError in `__all__` |
| Model routing | `_is_gemini_model()` tested for all cases |
| Env vars | `GEMINI_API_KEY`, `GEMINI_OCR_MODEL` documented |

## Important Notes

- Gemini Free Tier limits: Flash 20 req/day, Pro 0 req/day
- Gemini 3 Pro/Flash only available via Langdock API (not direct Gemini API)
- Model routing is string-based prefix match (`gemini-*`)
- Confidence hardcoded to 0.92 (consistent with other LLM backends)
