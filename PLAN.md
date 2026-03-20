# Project Status

Current version: **v1.9.5** | Tests: **104** (88 pass, 16 fixture-dependent skip) | Production-ready

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
| v1.6.0–1.6.3 | 2026-03-19 | Code review v1: IMAP UIDs, `first_col()`, clinic sort, formula injection (23 issues) |
| v1.7.0–1.7.1 | 2026-03-19 | Code review v2: cross-run dedup, per-email error handling, zip bomb guard (24 issues) |
| v1.8.0 | 2026-03-19 | Code review v3: `disconnect()` crash, password retry, col_familia guards + 37 new tests (15 issues) |
| v1.8.3 | 2026-03-19 | Full audit: diagnostic.py overhaul, security fixes, .gitignore cleanup (8 fixes) |
| v1.8.4 | 2026-03-19 | Shared dedup key, shared xlsx builder, env var warnings, healthcheck validation (10 fixes) |
| v1.9.0 | 2026-03-19 | New feature: `ID Клиники` column in network share CSVs for 1C integration |
| v1.9.1 | 2026-03-19 | Fix IMAP move crash on Cyrillic folder name (Обработанные) |
| v1.9.2 | 2026-03-19 | Auto-migrate existing network CSVs for ID Клиники column |
| v1.9.3 | 2026-03-20 | Dead network mount timeout, email-before-export order, self-ingestion guard, xlsx column migration |
| v1.9.4 | 2026-03-20 | Alfa открепление dates, VSK clinic from email subject |
| v1.9.5 | 2026-03-20 | Code review v7: dedup dtype=str, CSV inside lock, load_existing_keys raises on error, write-before-move |

**Total: 7 review rounds, 100+ issues found and fixed.**

---

## Nice-to-have improvements

None of these are blockers. All are code quality / maintainability improvements to tackle when convenient.

### 1. Split `main.py` god module (~655 lines)

**Why:** Config, CLI, 3 run modes, CSV export, healthcheck, monthly reports all in one file. Hard to review, easy to miss interactions. Biggest maintainability concern in the codebase.

**How:** Extract to 2–3 focused modules:
- `exporter.py` — `_export_to_network()`, `_attach_monthly_if_last_day()`
- `pipeline.py` — `process_file()`, `_dedup_xls_xlsx()`, `should_skip_file()`
- Keep `main.py` as thin CLI entry point + config loading

**Effort:** Medium. Need to carefully manage the `stats` dict passed between functions.

### 2. Test coverage for fetcher / notifier / main (~1380 untested lines)

**Why:** `fetcher.py` (426 lines) and `notifier.py` (299 lines) have zero test coverage. `main.py` only tests `_record_key()`. These are the highest-risk modules — IMAP/SMTP interactions, file I/O, email construction.

**How:** Mock `imaplib` and `smtplib` for unit tests. Test pure functions first (`should_skip_file()`, `_build_message()`, `_export_to_network()`). Add 1–2 integration tests for `process_file()` with synthetic xlsx fixtures.

**Effort:** High. Biggest ROI improvement for long-term reliability.

### 3. Deduplicate parser metadata extraction (8 parsers)

**Why:** 8 parsers repeat near-identical loops to extract company name, dates, and strahovatel from the first 20 rows. If the pattern changes, all 8 need manual updates.

**How:** Add `extract_metadata(df, max_rows=20) -> dict` to `parsers/utils.py`. Returns `{company, strahovatel, start_date, end_date}`. Each parser calls it instead of inline loops.

**Effort:** Medium. Touch 8 files but each change is mechanical.

### 4. Minor cleanup (low effort, do anytime)

| Item | Why | How |
|------|-----|-----|
| `requirements-dev.txt` | New devs don't know to install pytest | Add file: `pytest>=7.0` |
| `os.makedirs()` permissions | Default umask may be too permissive on shared Linux | Add `mode=0o750` to `makedirs()` calls for temp/logs/quarantine |
| `Дата обработки` stamped twice | `main.py` stamps it, then `writer.py` stamps it again — diverges on midnight runs | Pick one location, remove the other |
| Inconsistent `dtype=str` in 6 parsers | Some parsers pass `dtype=str` to `read_excel`, some don't — `load_existing_keys` fixed in v1.9.5 | Add `dtype=str` to remaining parsers that lack it |

---

## Observations (no action needed)

- `clinics.yaml` substring overlap ("Детская стоматология" vs "Детская стоматология №2") — handled by longest-first sort
- `_clinics` singleton not thread-safe — app is single-threaded
- Zip passwords in plaintext memory — acceptable for server-side processing
- `fetcher.py` fetch loop uses 2-space indent — internally consistent, reindenting 130 lines is risky

## Future features (when needed)

- Multi-clinic files (one file = two clinics)
- Per-clinic comment column headers for different insurer formats
- Windows file locking (`portalocker`) for dev/testing parity with prod
