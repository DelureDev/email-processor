# Project Status

Current version: **v1.7.1**

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
| 6 | `fetcher.py:361,385` | Failed Zetta zips permanently marked processed — never retried | ✅ v1.6.2 |
| 7 | `main.py + fetcher.py` | Multi-file Zetta zip cleanup deletes files before they're processed | ✅ v1.6.2 |
| 8 | `writer.py:137` | `_export_csv()` doesn't apply `_safe()` — CSV formula injection | ✅ v1.6.1 |
| 9 | `notifier.py:268` | `_build_xlsx()` email attachment skips `_safe()` — formula injection | ✅ v1.6.1 |
| 10 | `writer.py:123` | `.bak` created but never auto-restored on write failure | ✅ v1.6.2 |
| 11 | `parsers/*` | No per-row try/except — one bad cell crashes entire parser | ✅ v1.6.1 |
| 12 | `parsers/utils.py:22` | `format_date()` silently returns unparseable strings — no warning | ✅ v1.6.2 |
| 13 | `main.py:326` | Daily CSV export overwrites silently on re-runs | ✅ v1.6.2 |
| 14 | `tests/test_writer.py` | Test assertions use 4-tuples vs 5-tuple keys — broken after Клиника added | ✅ v1.6.0 |

### Low — nice to have

| # | File | Issue | Status |
|---|------|-------|--------|
| 15 | `clinic_matcher.py` | `_clinics` cache never invalidated | ✅ v1.6.3 |
| 16 | `clinic_matcher.py:107` | 60-char header guard is arbitrary | ✅ v1.6.3 |
| 17 | `detector.py:92` | Only first sheet read for format detection | ✅ v1.6.3 |
| 18 | `fetcher.py:142` | No socket timeout on IMAP — can hang indefinitely | ✅ v1.6.3 |
| 19 | `fetcher.py:168` | Dead code: `if False` on MOVE command | ✅ v1.6.0 |
| 20 | `main.py:211` | Redundant import of `extract_policy_comment` | ✅ v1.6.3 |
| 21 | `notifier.py:278` | `_build_csv()` is dead code | ✅ v1.6.3 |
| 22 | `parsers/*` | Inconsistent FIO casing — 6 parsers uppercase, 10 don't | ✅ v1.6.3 |
| 23 | `CLAUDE.md` | Says v1.5.0, code is v1.5.1 | ✅ v1.6.3 |

---

## Code review findings v2 (2026-03-19)

### Medium

| # | File | Issue | Status |
|---|------|-------|--------|
| 24 | `main.py:197 vs 212` | Dedup runs before clinic injection — cross-run dedup broken, duplicates accumulate | ✅ v1.7.0 |
| 25 | `main.py:332,346` | Network share CSV `_export_to_network()` missing `_safe()` — formula injection | ✅ v1.7.0 |
| 26 | `main.py:299-301` | Monthly report `str.contains()` is substring match — use `str.endswith()` | ✅ v1.7.0 |
| 27 | `fetcher.py:242-364` | No per-email try/except in main fetch loop — one exception loses all results | ✅ v1.7.0 |
| 28 | `fetcher.py:222,257` | No guard on IMAP FETCH response shape — `msg_data[0][1]` crash on malformed | ✅ v1.7.0 |
| 29 | `fetcher.py:160-175` | `EXPUNGE` removes all `\Deleted` messages, not just ours | ✅ v1.7.0 |
| 30 | `clinic_matcher.py:53,111` | `pd.ExcelFile` not closed — file handle leak on Windows | ✅ v1.7.0 |
| 31 | `main.py:393,399` | `processed_imap_ids` initialized twice — shadowed variable | ✅ v1.7.0 |
| 32 | `zetta_handler.py:149-182` | Can't distinguish wrong password from correct-password-but-no-xlsx | ✅ v1.7.0 |
| 33 | `alfa.py:26-64` | Hardcoded column defaults; no fail-safe when header not found | ✅ v1.7.0 |

### Low

| # | File | Issue | Status |
|---|------|-------|--------|
| 34 | `writer.py:171` | `_safe()` prefixes legitimate negative numbers with apostrophe | ✅ v1.7.1 |
| 35 | `writer.py:155`, `main.py:328,342` | `utf-8-sig` append inserts BOM mid-file | ✅ v1.7.1 |
| 36 | `writer.py:124-141` | `.bak` never cleaned up after success | ✅ v1.7.1 |
| 37 | `notifier.py:253-274` | `_build_xlsx()` never calls `wb.close()` | ✅ v1.7.1 |
| 38 | `fetcher.py:13` | Unused `import json` (one-time migration only) | ✅ v1.7.1 |
| 39 | `fetcher.py:121-123` | `_save_processed_ids` re-inserts full set every call | ✅ v1.7.1 |
| 40 | `fetcher.py:207-271` | Pre-scan password emails never marked processed | ✅ v1.7.1 |
| 41 | `zetta_handler.py:150-165` | No decompressed size limit on zip entries (zip bomb) | ✅ v1.7.1 |
| 42 | `fetcher.py:320` | Filename sanitization missing null bytes / control chars | ✅ v1.7.1 |
| 43 | `utils.py:20` | `format_date()` missing `DD.MM.YYYY HH:MM:SS` format | ✅ v1.7.1 |
| 44 | `utils.py:88` | `get_cell_str()` returns `"123456.0"` for integer cells | ✅ v1.7.1 |
| 45 | Multiple parsers | Inconsistent `dtype=str` usage (6 of 16) | ⏭️ SKIP |
| 46 | absolut, reso, vsk, zetta, euroins, renins | No error log when FIO column not found | ✅ v1.7.1 |
| 47 | `main.py:382,459` | No graceful error if `config['output']['master_file']` missing | ✅ v1.7.1 |

---

## Pending / future

- [ ] Multi-clinic files (one file = two clinics) — post-call decision when needed
- [ ] Per-clinic comment column headers if other insurers use different header names
- [ ] Tests for `clinic_matcher.py`
