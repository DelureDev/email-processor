# Improvement Roadmap — email-processor

**Current score: 8/10** (code review 2026-03-17)

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

## Priority 4 — Security & robustness (code review 2026-03-17)

| # | Item | Severity | Status |
|---|------|----------|--------|
| 11 | Move credentials to env vars (`${IMAP_PASSWORD}` etc.), remove plaintext from config.yaml | CRITICAL | ✅ |
| 12 | Add file lock around master.xlsx writes (prevent concurrent cron corruption) | CRITICAL | ✅ |
| 13 | Sanitize xlsx cell values against formula injection (`=`, `+`, `-`, `@` prefix) | HIGH | ✅ |
| 14 | Close workbook in finally block in writer.py (`_create_new`, `_append_to_existing`) | HIGH | ✅ |
| 15 | Stop re-reading master for CSV backup — pass records directly to `_export_csv()` | MEDIUM | ✅ |
| 16 | Add timeout to SMTP operations in notifier.py | MEDIUM | ✅ |
| 17 | Normalize dates in dedup key (zero-pad `1.1.2020` → `01.01.2020`) | MEDIUM | ✅ |
