# Improvement Roadmap — email-processor

**Current score: 7.5/10** (code review 2026-03-16)

All original 41 fixes + post-fix improvements are deployed. Test suite (50 tests) is in place.
This roadmap targets the gap from 7.5 to 9+.

---

## Priority 1 — Reliability

| # | Item | Why |
|---|------|-----|
| 1 | IMAP retry logic (2-3 attempts on connect/fetch) | Network hiccups fail the entire run |
| 2 | SQLite for processed IDs | `processed_ids.json` isn't atomic; concurrent runs or crashes can corrupt it |
| 3 | Batch writes in writer.py | Opening/saving entire workbook per file slows down at 10k+ rows |
| 4 | Pin dependency versions in requirements.txt | A pandas update could silently change parsing behavior |

## Priority 2 — Maintainability

| # | Item | Why |
|---|------|-----|
| 5 | Data-driven detector.py | 15-insurer if/elif chain works now but won't scale to 30+ |
| 6 | Add type hints to fetcher.py, notifier.py, main.py | Consistency with parsers/utils.py; helps IDE and future contributors |
| 7 | Replace `_skip_rules_cache` global with `functools.lru_cache` | Module-level `global` is an anti-pattern |

## Priority 3 — Nice to have

| # | Item | Why |
|---|------|-----|
| 8 | Parser confidence scoring in detector.py | Log low-confidence format detections for monitoring |
| 9 | Master CSV backup (periodic export) | Human-readable safety net alongside .xlsx |
| 10 | Audit logging of password handling | Ensure no debug mode leaks actual password values |
