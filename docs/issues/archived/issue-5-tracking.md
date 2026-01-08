# Issue #5 - Implementation Log

**GitHub**: https://github.com/Unfuture/text-extraction-service/issues/5
**Title**: refactor: Extract ContentRouter class from service/main.py
**Started**: 2026-01-08
**Completed**: 2026-01-08

## Summary

Extract the content routing logic from `service/main.py` into a reusable `ContentRouter` class in `src/text_extraction/router.py`.

## Implementation Steps

- [x] Phase 1: Project architecture analysis (system-architect)
- [x] Phase 2: Documentation analysis (requirements-analyst)
- [x] Phase 3: Ticket analysis (solution-engineer)
- [x] Phase 5: Implementation planning
- [x] Create `RoutingDecision`, `RoutingStrategy`, `CostEstimate` dataclasses
- [x] Implement `ContentRouter` class
- [x] Implement cost estimation logic
- [x] Create unit tests (98% coverage - exceeded >90% requirement)
- [x] Update `__init__.py` exports
- [x] Final verification and cleanup

## Key Changes

### Logic/Workflow Changes

1. **New `RoutingStrategy` enum** with values:
   - `DIRECT_ONLY` - No OCR, direct text extraction only
   - `OCR_ALL` - OCR for all pages
   - `OCR_SELECTIVE` - OCR for specific pages only

2. **New `CostEstimate` dataclass** for cost/time predictions:
   - `ocr_cost_eur` - Cost for LLM OCR
   - `ocr_time_seconds` / `direct_time_seconds`
   - Auto-calculated `total_cost_eur` and `total_time_seconds`

3. **New `RoutingDecision` dataclass** with:
   - `pdf_type`, `strategy`
   - `direct_pages`, `ocr_pages` (1-indexed page lists)
   - `estimated_cost`, `estimated_time_seconds`
   - `quality`, `total_pages`, `reasoning`

4. **New `ContentRouter` class** with methods:
   - `route(classification, quality)` -> `RoutingDecision`
   - `estimate_cost(ocr_page_count, direct_page_count)` -> `CostEstimate`
   - `has_ocr_backend()` -> bool
   - `_determine_strategy()`, `_select_pages()`, `_generate_reasoning()`

### Infrastructure/Configuration

- No infrastructure changes required
- No new environment variables needed

### Permission/Security Updates

- No permission changes required

## Files Created/Modified

| File | Action | Lines |
|------|--------|-------|
| `src/text_extraction/router.py` | Created | 323 |
| `tests/unit/test_router.py` | Created | 530 |
| `src/text_extraction/__init__.py` | Modified | +4 exports |

## Test Results

- **68 unit tests** covering all functionality
- **98% code coverage** (exceeds 90% requirement)
- All linting checks pass (ruff)

## Routing Logic Matrix (Implemented)

| PDF Type | Quality=fast | Quality=balanced | Quality=accurate |
|----------|--------------|------------------|------------------|
| PURE_TEXT | Direct all | Direct all | Direct all |
| PURE_IMAGE | Direct all | OCR all | OCR all |
| HYBRID | Direct all | OCR image pages | OCR image+hybrid |
| UNKNOWN | Direct all | Direct all | Direct all |

## Important Notes

### Design Decisions
- Used dataclasses instead of Pydantic (simpler structures)
- ContentRouter is standalone, optional integration with TwoPassProcessor
- Automatic fallback to DIRECT_ONLY when no OCR backend available
- Default cost assumption: 0.005 EUR/page for LLM OCR (Claude Sonnet)

### Integration Notes
- TwoPassProcessor can optionally use ContentRouter for routing decisions
- service/main.py does NOT need changes - routing is internal to processor
- All new classes exported via `text_extraction.__init__`

## References

- Parent Issue: #1
- Depends on: #4 (TwoPassProcessor) - COMPLETED
