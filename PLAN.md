# Project Status

Current version: **v1.8.3** | Tests: **103** (87 pass, 16 fixture-dependent skip)

---

## Version history

| Version | Date | Summary |
|---------|------|---------|
| v1.0.0 | 2026-03-17 | Initial release — 15 parsers, IMAP, SMTP, ZIP, dedup, CSV export, SQLite, security |
| v1.0.1–1.0.3 | 2026-03-17 | Security cleanup, CSV delimiter `;`, `Дата обработки` fix |
| v1.1.0 | 2026-03-18 | Monthly master CSV on network share |
| v1.2.0–1.2.4 | 2026-03-18 | Clinic detection (`Клиника` column, `clinics.yaml`), config fixes |
| v1.3.0–1.3.2 | 2026-03-18 | Monthly xlsx email, date-only format, `ё`→`е` dedup normalization |
| v1.4.0–1.4.1 | 2026-03-18 | IMAP email move to "Обработанные", `Клиника` in dedup key |
| v1.5.0–1.5.1 | 2026-03-18 | `Комментарий в полис` extractor, clinic/comment failure reporting |
| v1.6.0–1.6.3 | 2026-03-19 | Code review v1 fixes: IMAP UIDs, `first_col()`, clinic sort, per-row try/except, formula injection, FIO casing, dead code cleanup (23 issues) |
| v1.7.0–1.7.1 | 2026-03-19 | Code review v2 fixes: cross-run dedup, network CSV `_safe()`, per-email error handling, UID EXPUNGE, file handle leaks, zip bomb guard, BOM fix (24 issues) |
| v1.8.0 | 2026-03-19 | Code review v3 fixes: `disconnect()` crash, password retry, double I/O, `_safe()` tests, col_familia guards, cumulative zip limit + 37 new tests (15 issues) |
| v1.8.3 | 2026-03-19 | Full project audit: security fixes, diagnostic.py overhaul, .gitignore cleanup, dead code removal |

---

## Code review history

Five review rounds + full audit, **74+ issues found and fixed**, codebase now clean.

| Round | Date | Issues found | Fixed | Key themes |
|-------|------|-------------|-------|------------|
| v1 | 2026-03-18 | 23 | 23 | IMAP UIDs, `find_col()` col-0 bug, clinic sort, formula injection, dead code |
| v2 | 2026-03-19 | 24 | 23 | Cross-run dedup order, per-email error handling, file handle leaks, zip bomb |
| v3 | 2026-03-19 | 15 | 15 | `disconnect()` crash, password retry, `_safe()` tests, col_familia guards |
| v4 | 2026-03-19 | 2 | 0 | Codebase clean — 1 cosmetic skip, 1 low-priority open |
| v5 | 2026-03-19 | 6 | 0 | Codebase clean — docs-only fixes, observations for future |
| Audit | 2026-03-19 | 14 | 8 | Full project audit — security, code quality, docs, .gitignore |

### Skipped / deferred (by design)

| # | Issue | Reason |
|---|-------|--------|
| 45 | Inconsistent `dtype=str` in 6 parsers | Low risk, would touch many files for minimal gain |
| 67 | 2-space indent in fetcher.py fetch loop | Internally consistent, reindenting 130 lines is risky |

### False positives rejected (v4)

- "Zip Slip guard broken" — `os.path.realpath() + os.sep` is correct
- "Float-to-int >2^53" — policy numbers are not 16-digit floats
- "Dedup key includes clinic = duplicates" — by design since v1.4.1
- "Generic parser 'фио' matches 'обслуживание'" — wrong, no substring match
- "IMAP SEARCH `[0]` bounds check" — imaplib always returns `[b'']` for empty results

---

## Why did bugs keep appearing?

Root-cause analysis after reviews v1–v3 found ~70 issues:

1. **Built feature-first, not test-first.** v1.0.0 shipped 15 parsers + full pipeline with tests covering only utilities. ~70% of code had zero coverage.
2. **Fix waves added untested code paths.** v1.6.0–v1.7.1 fixed 47 issues but added zero tests for fetcher/notifier/clinic_matcher.
3. **`main.py` is a 655-line god module.** Config, CLI, stats, 3 modes, CSV export, healthcheck, monthly reports — hard to review, easy to miss interactions.
4. **No integration tests.** Unit tests cover record keys and writer, but nobody tests the full `process_file()` pipeline.

**The fix: write tests for the untested 70%.** v1.8.0 added 37 tests (50 → 103), covering `_safe()`, `zetta_handler`, `clinic_matcher`, and `detector` sender logic. Coverage is better but still has major gaps.

---

## Test coverage status

| Module | Lines | Coverage | Priority |
|--------|-------|----------|----------|
| `parsers/utils.py` | 98 | Good (6/7 functions, missing `first_col`) | Low |
| `writer.py` | 253 | Moderate (create, append, dedup, `_safe`) | Low |
| `zetta_handler.py` | 221 | Moderate (sender, passwords, zip ops) | Low |
| `clinic_matcher.py` | 141 | Good (detect, extract, edge cases) | Low |
| `detector.py` | 122 | Moderate (sender-based; content needs fixtures) | Medium |
| **`main.py`** | **655** | **Weak** (only `_record_key`) | **High** |
| **`fetcher.py`** | **426** | **Zero** | **High** |
| **`notifier.py`** | **299** | **Zero** | Medium |
| 15 parsers | ~900 | 4 tested (fixture-dependent, skip in CI) | Medium |

---

## Open items

### Code improvements (not urgent)

| # | Area | Description |
|---|------|-------------|
| 60 | `main.py` | God module — extract `_export_to_network()`, `_attach_monthly_if_last_day()` to separate modules |
| 61 | 8 parsers | Duplicate metadata extraction loops — extract to `parsers/utils.py` |
| 62 | Dependencies | No `requirements-dev.txt` for pytest; no lockfile |
| 63 | `writer.py` | Backward scan for last row — O(n), only matters at 100k+ rows |
| 64 | `writer.py` | Windows file locking is no-op (prod is Linux) |
| 65 | 6 parsers | Inconsistent `dtype=str` usage |
| 66 | `zetta_handler.py` | `passwords.index(pwd)` — use `enumerate()` instead |
| 68 | `main.py` + `writer.py` | `Дата обработки` stamped twice — diverges on midnight-crossing runs |
| 69 | `main.py` x2 + `writer.py` | `_norm_date()` duplicated 3x — extract to `parsers/utils.py` |
| 74 | `diagnostic.py` | ~~Still reads `processed_ids.json` instead of SQLite `.db`~~ **Fixed in v1.8.3** |

### Observations (no action needed)

| # | Note |
|---|------|
| 71 | `clinics.yaml` "Детская стоматология" is substring of "Детская стоматология №2" — handled by longest-first sort |
| 72 | `notifier.py` `_is_zetta_notification()` uses brittle `^11140` prefix — cosmetic only |

### Future features

- [ ] Multi-clinic files (one file = two clinics) — decide when needed
- [ ] Per-clinic comment column headers for different insurer formats
- [ ] **Test coverage push** — highest-ROI action: `process_file()`, `should_skip_file()`, `_build_message()`, `first_col()`, fetcher pure functions
