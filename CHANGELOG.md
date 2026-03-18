# Changelog

## [1.6.2] - 2026-03-19
### Fixed (Medium)
- **Zetta zip retry**: Zetta zip `message_id` no longer marked processed when extraction fails — failed zips will be retried on the next run (`fetcher.py`)
- **Multi-file zip cleanup**: `_extract_dir` now only set on the last result item from each zip, preventing premature directory deletion while other files from the same zip are still pending (`fetcher.py`)
- **Master backup restore**: `write_batch_to_master()` now catches `_append_to_existing()` failures and auto-restores `master.xlsx` from `.bak` before re-raising (`writer.py`)
- **`format_date()` silent fallback**: logs a `WARNING` when a date string matches no known format and is returned as-is (`parsers/utils.py`)
- **Daily network CSV append**: `_export_to_network()` daily delta file now appends across runs in the same day instead of silently overwriting (`main.py`)

## [1.6.1] - 2026-03-19
### Fixed (Medium)
- **Per-row try/except in all parsers**: all 15 parser data loops now catch per-row exceptions and skip bad rows with a warning instead of aborting the entire file — `alfa.py`, `kaplife.py` (both loops), `generic_parser.py` added; 13 parsers were already done in v1.6.0
- **CSV formula injection**: `_export_csv()` in `writer.py` now applies `_safe()` to each cell value before writing
- **Email attachment formula injection**: `_build_xlsx()` in `notifier.py` now applies `_safe()` to each cell value

## [1.6.0] - 2026-03-19
### Fixed (Critical)
- **IMAP UIDs**: all IMAP operations now use stable UIDs (`uid('SEARCH'/'FETCH'/'COPY'/'STORE')`) instead of volatile sequence numbers — prevents moving/deleting wrong emails
- **Processed IDs timing**: `_save_processed_ids()` moved from `fetch_attachments()` to `main.py` after successful batch write — emails can now be retried on crash
- **`find_col() or find_col()` column-zero bug**: added `first_col()` helper to `parsers/utils.py` and replaced all `or`-chained `find_col()` calls in 11 parsers — column at index 0 no longer silently falls through
- **Clinic keyword global sort**: `clinic_matcher.py` now builds a flat keyword list sorted globally by length (longest first) — cross-clinic partial matches no longer depend on YAML file order
### Fixed (Medium)
- **Password extraction crash**: added `if payload is None: continue` guard in per-email password extraction (`fetcher.py`) — malformed emails no longer crash the fetch loop
### Fixed (Tests)
- Updated `test_dedup.py` and `test_writer.py` to use 5-tuple dedup keys (including `Клиника` field added in v1.4.1)

## [1.5.1] - 2026-03-18
### Added
- Track `unmatched_clinics` and `missing_comments` in stats dict
- Email report shows clinic detection issues: files with no clinic match and files where comment extraction found nothing (with actionable hints on what to fix)
- Clinic issues included in health banner problem count and subject emoji
- `--test` mode shows warning when `extract_comment=True` but nothing extracted
- `clinic_matcher.py` logs a warning when `extract_policy_comment()` finds nothing, with a hint on what to add

## [1.5.0] - 2026-03-18
### Added
- `Комментарий в полис` column — universal policy comment extractor
- `extract_policy_comment()` in `clinic_matcher.py`: two strategies — column header scan (rows 0-19), then free-text row scan for program description keywords
- `extract_comment: true` flag in `clinics.yaml` enables per-clinic comment extraction (currently Гарибальди 36)
- `clinic_matcher.detect_clinic()` now returns `(clinic_name, extract_comment)` tuple
- Comment injected into all records for matching files; visible in `--test` output

## [1.4.1] - 2026-03-18
### Changed
- Added `Клиника` to dedup key — same patient, different clinic = separate record
- `load_existing_keys()` in `writer.py` updated with backward-compat fallback for master files without `Клиника` column

## [1.4.0] - 2026-03-18
### Added
- IMAP email move to configured folder after successful processing
- `move_to_folder()` method in `fetcher.py` using COPY + DELETE + EXPUNGE
- `processed_folder` setting in `config.yaml` (e.g. `"Обработанные"`)
- Only emails that produce new records are moved; runs in `finally` block before disconnect

## [1.3.2] - 2026-03-18
### Fixed
- Normalize `ё` → `е` in dedup key to prevent duplicate patients when insurance uses different spellings

## [1.3.1] - 2026-03-18
### Changed
- `Дата обработки` now date-only `DD.MM.YYYY` (removed time component) in all outputs

## [1.3.0] - 2026-03-18
### Added
- Monthly master xlsx email on last day of month
- `_attach_monthly_if_last_day()` reads master.xlsx, filters records for current month, attaches styled xlsx to email report
- `monthly_records` key added to stats dict

## [1.2.4] - 2026-03-18
### Changed
- Removed CSV attachment from email report — daily delta xlsx only; CSV available on network share

## [1.2.3] - 2026-03-18
### Fixed
- Renamed `Брянская` → `Гарибальди 36` in `clinics.yaml`
- Removed `Дентал Фэнтези` keyword (sub-brand, not needed)

## [1.2.2] - 2026-03-18
### Fixed
- `_load_clinics()` now caches `extract_comment` field in clinic dicts

## [1.2.0] - 2026-03-18
### Added
- Clinic detection — new `Клиника` column in all outputs
- `clinic_matcher.py` — scans xlsx content for keywords from `clinics.yaml`
- `clinics.yaml` — configurable clinic keyword lookup table
- Clinic shown in `--test` mode output
- No match → `⚠️ Не определено` with log warning

## [1.1.0] - 2026-03-18
### Added
- Monthly master CSV on network share (`master_YYYY-MM.csv`) — appended incrementally each run, new file each month; 1C-compatible

## [1.0.3] - 2026-03-17
### Fixed
- `Дата обработки` now populated in email attachment and network share CSVs (was empty)

## [1.0.2] - 2026-03-17
### Changed
- CSV delimiter changed from `,` to `;` for 1C import compatibility

## [1.0.1] - 2026-03-17
### Security
- Remove `output/master.xlsx.bak`, `diagnostic_report.json`, `processed_ids.json.bak` from git history (contained patient data and internal metadata)
- Update `.gitignore` to exclude `output/` directory and diagnostic files

## [1.0.0] - 2026-03-17
### Added
- Initial release — full automated DMS list processing pipeline
- 15 insurance company parsers (RESO, Yugoria, Zetta, Alfa, Sber, Soglasie, VSK, Absolut, PSB, KapLife, Euroins, Renins, Ingos, Luchi, Energogarant) + generic fallback
- Two-stage format detection: sender map → content keywords → generic
- ZIP password auto-extraction for Zetta (monthly + per-email) and Sberbank
- Deduplication by ФИО + policy + dates with date normalization
- Daily delta email report (HTML + styled xlsx + csv attachments)
- Network share (SMB/CIFS) CSV export for 1C integration
- SQLite tracking of processed message IDs (migrated from JSON)
- Batch writes — master.xlsx opened once per run
- File locking (fcntl) to prevent concurrent cron corruption
- Formula injection protection in xlsx output
- Audit log for password operations (no plaintext passwords logged)
- Credentials via environment variables (`${IMAP_PASSWORD}`, `${SMTP_PASSWORD}`)
- Healthcheck ping for cron monitoring
- Quarantine folder for files that fail parsing
- 50 automated tests (pytest)
- IMAP retry logic (3 attempts on connect + fetch)
