# Project Status

Current version: **v1.8.0**

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

## Why do bugs keep appearing after every code review?

Honest root-cause analysis — three reviews, ~70 issues found across them:

1. **The project was built feature-first, not test-first.** v1.0.0 shipped 15 parsers, IMAP, SMTP, ZIP handling, dedup, CSV export — a huge surface area — with tests only covering utilities and a handful of parsers. Every review catches bugs that tests would have caught at write-time. ~70% of the codebase has zero test coverage. That's the #1 reason.

2. **Each fix wave introduces new code paths that aren't tested either.** v1.6.0–v1.7.1 fixed 47 issues but added zero tests for fetcher, notifier, clinic_matcher, or zetta_handler. The fixes are correct, but the *surrounding* code is still unverified, so the next review finds more.

3. **`main.py` is a god module.** 622 lines orchestrating config, CLI, stats, 3 execution modes, CSV export, healthcheck, and monthly reports. Hard to review, hard to test, easy to miss interactions.

4. **No integration tests.** Unit tests exist for record keys and writer, but nobody tests the full `process_file()` pipeline with mocked IMAP/SMTP. Edge cases in the pipeline seams (dedup timing, clinic injection order, IMAP ID tracking) only surface under review.

**The fix isn't "review harder" — it's: write tests for the untested 70%, then bugs stop appearing because they get caught at commit time, not review time.**

---

## Code review findings v3 (2026-03-19)

### Critical — fix now

| # | File | Issue | How to fix | Status |
|---|------|-------|------------|--------|
| 48 | `fetcher.py:159` | `disconnect()` crashes with `AttributeError` if `connect()` never succeeded — `self.mail` doesn't exist | Add `if not hasattr(self, 'mail'): return` at top of `disconnect()` | ✅ v1.8.0 |
| 49 | `fetcher.py:238` | Password email marked processed even when extraction returns None — password lost forever, never retried | Move `self.processed_ids.add(message_id)` inside the `if monthly:` block | ✅ v1.8.0 |

### High — fix soon

| # | File | Issue | How to fix | Status |
|---|------|-------|------------|--------|
| 50 | `main.py:410` | Emails producing only duplicate records never moved to processed folder — re-downloaded every run, wasted bandwidth | Change condition: track `imap_id` whenever `process_file()` was called (not just when new records produced). Dedup already handles duplicates. | ✅ v1.8.0 |
| 51 | `writer.py:44` | `load_existing_keys()` reads master.xlsx twice (once for column check, once for data) — doubles I/O, TOCTOU race | Single `pd.read_excel(nrows=0)`, save columns, then `pd.read_excel(usecols=...)`. Wrap in try/except for corrupted files. | ✅ v1.8.0 |
| 52 | `writer.py:174` | `_safe()` formula injection — zero tests. Security-critical function never verified. | Add test cases: `=CMD()`, `+IMPORT()`, `@SUM()` blocked; `-500` preserved; `None`→`''`; `\t` blocked. | ✅ v1.8.0 |
| 53 | 5 parsers | `psb.py`, `sber.py`, `soglasie.py`, `kaplife.py`, `yugoriya.py` — no `if col_familia is None: return []` guard before data loop. If column not found, entire file silently produces 0 records. | Add explicit check after `find_col()`: `if col_familia is None: logger.error(...); return []` — same pattern as ingos.py and luchi.py already use. | ✅ v1.8.0 |
| 54 | `parsers/utils.py:76` | `assemble_fio(col_familia=None)` crashes with TypeError — caught by per-row except, but entire file silently returns 0 records | Either add None guard in `assemble_fio()`, or rely on #53 fix (preferred — fail early, not per-row). | ✅ v1.8.0 (via #53) |
| 55 | `zetta_handler.py:148-160` | No cumulative zip extraction size limit — individual entries capped at 100MB but a zip with 10x100MB entries consumes 1GB disk | Add `total_extracted` counter, abort if cumulative exceeds 500MB configurable limit. | ✅ v1.8.0 |

### Medium — improve

| # | File | Issue | How to fix | Status |
|---|------|-------|------------|--------|
| 56 | `main.py:300` | Monthly report date filter uses `str.endswith(month_suffix)` but dates may not be zero-padded consistently | Use same `norm_date()` logic as `_record_key()` before filtering, or parse dates properly with `pd.to_datetime()`. | ✅ v1.8.0 |
| 57 | `detector.py:41` | Sender detection uses substring `in` — `fake@notpsbins.ru` matches `psbins.ru` | Change to exact email match or `sender_lower.endswith('@' + domain)` check. | ✅ v1.8.0 |
| 58 | `main.py:71` | Config has no schema validation — missing keys crash with unhelpful `KeyError` deep in pipeline | Add `_validate_config(config)` after load: check required keys exist (`imap.server`, `imap.username`, `output.master_file`, etc.). Return clear error. | ✅ v1.8.0 |
| 59 | Tests | 0% coverage for fetcher, notifier, clinic_matcher, zetta_handler. No mocking. CI silently skips fixture-dependent tests. | Priority: (1) `_safe()` tests, (2) `zetta_handler` password extraction tests (pure functions, easy), (3) `clinic_matcher` tests with temp clinics.yaml, (4) `fetcher` + `notifier` with mocked IMAP/SMTP. | ✅ v1.8.0 (partial: _safe, zetta, clinic_matcher, detector sender) |
| 60 | `main.py` | 622-line god module — config, CLI, stats, 3 modes, CSV export, healthcheck, monthly reports all in one file | Extract `_export_to_network()` and `_attach_monthly_if_last_day()` to separate module. Consider `PipelineOrchestrator` class for `process_file()`. Not urgent but prevents future bug density. | |
| 61 | 8 parsers | Metadata extraction from upper rows (dates, company name) duplicated with identical nested loops | Extract to `extract_file_metadata(df, max_rows=20) -> dict` in `parsers/utils.py`. Return `{strahovatel, start_date, end_date}`. | |

### Low — nice to have

| # | File | Issue | How to fix | Status |
|---|------|-------|------------|--------|
| 62 | `requirements.txt` | No lockfile — `pip install` may pull different versions on different machines | Add `requirements.lock` via `pip freeze`. Add `requirements-dev.txt` for pytest. | |
| 63 | `writer.py:232-237` | `_append_to_existing()` scans backwards from `max_row` to find last data row — O(n) on large files | Accept openpyxl's `max_row` as-is (it's reliable for non-styled rows). Only matters at 100k+ rows. | |
| 64 | `writer.py:20-22` | Windows file locking is no-op — concurrent writes on Windows corrupt master.xlsx | Implement via `msvcrt.locking()` or document single-instance requirement. Low priority since prod is Linux. | |
| 65 | 6 parsers | Inconsistent `dtype=str` — ingos, luchi, energogarant, generic use it, others don't | Standardize to `dtype=str` in all parsers. Prevents pandas date auto-parsing surprises. | |
| 66 | `zetta_handler.py:207` | `passwords.index(pwd)` logs wrong index if password appears multiple times in list | Use `enumerate()` in `try_passwords()` loop and log iteration count. | |

---

## Code review findings v4 (2026-03-19)

**Result: codebase is clean.** Only 1 real (minor) issue found after 3 prior rounds that fixed ~70 bugs total.

### Medium

| # | File | Issue | How to fix | Status |
|---|------|-------|------------|--------|
| 67 | `fetcher.py:259` | Indentation inconsistency — `try/except` block uses 2-space indent inside 4-space code | Internally consistent (try/body/except all use 2-space). Reindenting 130 lines is risky for a cosmetic fix. | ⏭️ SKIP |

### Low

| # | File | Issue | How to fix | Status |
|---|------|-------|------------|--------|
| 68 | `main.py:246` + `writer.py:116` | `Дата обработки` stamped twice — once in `process_file()` for stats, again in `write_batch_to_master()`. Only diverges on midnight-crossing runs | Pass timestamp as parameter instead of calling `datetime.now()` twice. Low priority — date-only format means this only matters at exactly midnight | |

### False positives rejected

- "Zip Slip guard broken" — `os.path.realpath() + os.sep` is correct
- "Float-to-int >2^53" — insurance policy numbers are not 16-digit floats
- "Dedup key includes clinic = allows duplicates" — by design since v1.4.1
- "Generic parser 'фио' matches 'обслуживание'" — wrong, no substring match

---

## Pending / future

- [ ] Multi-clinic files (one file = two clinics) — post-call decision when needed
- [ ] Per-clinic comment column headers if other insurers use different header names
- [ ] **Test coverage push** — the single highest-ROI action to stop the bug treadmill
