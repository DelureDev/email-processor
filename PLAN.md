# Project Status

Current version: **v1.5.1**

---

## Completed features

| Version | Feature | Status |
|---------|---------|--------|
| v1.0.0 | Initial pipeline — 15 parsers, detection, dedup, email, network share, SQLite, security | ✅ |
| v1.0.1 | Security cleanup — private data removed from git history, `.gitignore` hardened | ✅ |
| v1.0.2 | CSV delimiter `,` → `;` for 1C import | ✅ |
| v1.0.3 | `Дата обработки` populated in email and share CSVs | ✅ |
| v1.1.0 | Monthly master CSV on network share (`master_YYYY-MM.csv`) | ✅ |
| v1.2.0 | Clinic detection — `Клиника` column, `clinic_matcher.py`, `clinics.yaml` | ✅ |
| v1.2.2–1.2.3 | Clinic config fixes (`Гарибальди 36`, remove Дентал Фэнтези) | ✅ |
| v1.2.4 | Remove CSV from email attachment | ✅ |
| v1.3.0 | Monthly master xlsx on last day of month (email attachment) | ✅ |
| v1.3.1 | `Дата обработки` — date-only `DD.MM.YYYY` (removed time) | ✅ |
| v1.3.2 | `ё` → `е` normalization in dedup key | ✅ |
| v1.4.0 | IMAP email move to "Обработанные" after successful processing | ✅ |
| v1.4.1 | `Клиника` added to dedup key — same patient, different clinic = separate record | ✅ |
| v1.5.0 | `Комментарий в полис` universal extractor (column header + free-text strategies) | ✅ |
| v1.5.1 | Clinic/comment extraction failure reporting in email + logs | ✅ |

---

## Code review findings (2026-03-18)

### Critical — fix before production

| # | File | Issue | Status |
|---|------|-------|--------|
| 1 | `fetcher.py` | IMAP sequence numbers used instead of UIDs — could move/delete wrong emails | ✅ v1.6.0 |
| 2 | `fetcher.py` | Processed IDs saved before data is written — data loss on crash | ✅ v1.6.0 |
| 3 | 10+ parsers | `find_col() or find_col()` — column index 0 treated as falsy, wrong column selected | ✅ v1.6.0 |
| 4 | `clinic_matcher.py` | Cross-clinic keyword overlap depends on fragile YAML ordering | ✅ v1.6.0 |

### Medium — fix soon

| # | File | Issue | Status |
|---|------|-------|--------|
| 5 | `fetcher.py:295` | Missing `payload is None` check in password extraction — crash on malformed email | ✅ v1.6.0 |
| 6 | `fetcher.py:361,385` | Failed Zetta zips permanently marked processed — never retried | ⬜ |
| 7 | `main.py + fetcher.py` | Multi-file Zetta zip cleanup deletes files before they're processed | ⬜ |
| 8 | `writer.py:137` | `_export_csv()` doesn't apply `_safe()` — CSV formula injection | ⬜ |
| 9 | `notifier.py:268` | `_build_xlsx()` email attachment skips `_safe()` — formula injection | ⬜ |
| 10 | `writer.py:123` | `.bak` created but never auto-restored on write failure | ⬜ |
| 11 | `parsers/*` | No per-row try/except — one bad cell crashes entire parser | ⬜ |
| 12 | `parsers/utils.py:22` | `format_date()` silently returns unparseable strings — no warning | ⬜ |
| 13 | `main.py:326` | Daily CSV export overwrites silently on re-runs | ⬜ |
| 14 | `tests/test_writer.py` | Test assertions use 4-tuples vs 5-tuple keys — broken after Клиника added | ✅ v1.6.0 |

### Low — nice to have

| # | File | Issue | Status |
|---|------|-------|--------|
| 15 | `clinic_matcher.py` | `_clinics` cache never invalidated | ⬜ |
| 16 | `clinic_matcher.py:107` | 60-char header guard is arbitrary | ⬜ |
| 17 | `detector.py:92` | Only first sheet read for format detection | ⬜ |
| 18 | `fetcher.py:142` | No socket timeout on IMAP — can hang indefinitely | ⬜ |
| 19 | `fetcher.py:168` | Dead code: `if False` on MOVE command | ⬜ |
| 20 | `main.py:211` | Redundant import of `extract_policy_comment` | ⬜ |
| 21 | `notifier.py:278` | `_build_csv()` is dead code | ⬜ |
| 22 | `parsers/*` | Inconsistent FIO casing — 6 parsers uppercase, 10 don't | ⬜ |
| 23 | `CLAUDE.md` | Says v1.5.0, code is v1.5.1 | ⬜ |

---

## Pending / future

- [ ] Multi-clinic files (one file = two clinics) — post-call decision when needed
- [ ] Per-clinic comment column headers if other insurers use different header names
- [ ] Tests for `clinic_matcher.py`
