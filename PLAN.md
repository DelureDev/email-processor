# Improvement Roadmap — email-processor

**Current score: 7.5/10** (code review 2026-03-16)

---

## Priority 1 — Reliability ✅ DONE (2026-03-16)

| # | Item | Status |
|---|------|--------|
| 1 | IMAP retry logic (3x on connect + fetch) | ✅ |
| 2 | SQLite for processed IDs (atomic writes, auto-migrates JSON) | ✅ |
| 3 | Batch writes in writer.py (one open/save per run) | ✅ |
| 4 | Pin dependency version bounds in requirements.txt | ✅ |

## Priority 2 — Maintainability ✅ DONE (2026-03-16)

| # | Item | Status |
|---|------|--------|
| 5 | Data-driven detector.py (`CONTENT_RULES` list, one line per insurer) | ✅ |
| 6 | Type hints on fetcher.py, notifier.py, main.py | ✅ |
| 7 | Replace `_skip_rules_cache` global with `functools.lru_cache` | ✅ |

## Priority 3 — Nice to have ✅ DONE (2026-03-17)

| # | Item | Status |
|---|------|--------|
| 8 | Parser confidence scoring in detector.py | ✅ |
| 9 | Master CSV backup (periodic export) | ✅ |
| 10 | Audit logging of password handling | ✅ |
