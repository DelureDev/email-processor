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

## Priority 2 — Maintainability

| # | Item | Why |
|---|------|-----|
| 5 | Data-driven detector.py | 15-insurer if/elif chain won't scale to 30+ |
| 6 | Add type hints to fetcher.py, notifier.py, main.py | Consistency; helps IDE and future contributors |
| 7 | Replace `_skip_rules_cache` global with `functools.lru_cache` | Module-level `global` is an anti-pattern |

## Priority 3 — Nice to have

| # | Item | Why |
|---|------|-----|
| 8 | Parser confidence scoring in detector.py | Log low-confidence format detections for monitoring |
| 9 | Master CSV backup (periodic export) | Human-readable safety net alongside .xlsx |
| 10 | Audit logging of password handling | Ensure no debug mode leaks actual password values |
