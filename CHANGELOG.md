# Changelog

## [1.9.5] - 2026-03-20
### Security
- **Dedup key float mismatch**: `load_existing_keys()` now reads with `dtype=str` — previously pandas could read policy numbers as floats (`12345` → `"12345.0"`), causing dedup to silently fail and accumulate duplicates.
- **CSV backup inside file lock**: `_export_csv()` now runs inside `_master_lock`, preventing interleaved/corrupted rows from overlapping cron runs.

### Fixed
- **`load_existing_keys` raises on error**: previously returned empty set on read failure, causing entire master to be duplicated on next write. Now raises `RuntimeError` to abort the run.
- **Batch write before email move**: emails are now moved to Обработанные and IDs saved only AFTER `write_batch_to_master` succeeds — prevents data loss if write fails.
- **`detect_clinic`/`extract_policy_comment` crash-safe**: wrapped in try/except inside `process_file()` — a corrupted file no longer kills the entire pipeline.

## [1.9.4] - 2026-03-20
### Fixed
- **Alfa parser missing dates for открепление**: recognizes `"Дата открепления с"` / `"Дата открепления по"` as single-cell date headers, and `"Дата открепления"` / `"Дата прикрепления"` as end/start date columns.
- **VSK clinic not detected**: `detect_clinic()` now also scans the email subject line for clinic keywords — VSK always includes the clinic name in the subject (e.g. `"ВСК _ открепление _ ... _ ООО «Детский Госпиталь»"`). Subject is passed through the pipeline via `process_file(subject=...)`.

## [1.9.3] - 2026-03-20
### Fixed
- **Dead network mount blocks email report**: `_export_to_network()` now checks mount accessibility with a 10s timeout before writing — prevents `os.path.exists()` hanging on dead NFS mounts. Email report and healthcheck always sent first, network export runs last.
- **Re-ingestion of own report emails**: fetcher now skips emails with "Обработка списков ДМС" in subject to prevent parsing yesterday's attached `records_*.xlsx` as new data.
- **Auto-migrate old master.xlsx layout**: writer detects missing `Клиника`/`Комментарий в полис` columns and inserts them automatically (shifts Источник/Дата обработки right). Previously wrote data into wrong columns.
- **Test mode crash**: `run_test_mode` unpacked 2 values from `detect_clinic()` which now returns 3 (since v1.9.0).

## [1.9.2] - 2026-03-19
### Fixed
- **Network CSV backward compatibility**: existing CSV files on network share (daily + monthly) are automatically migrated when `ID Клиники` column is missing — inserts new column after `Клиника` with empty values for old rows, then appends new data normally. No manual deletion needed.

## [1.9.1] - 2026-03-19
### Fixed
- **IMAP move to Cyrillic folder**: `move_to_folder()` now encodes folder names as IMAP modified UTF-7 (RFC 3501 §5.1.3) — fixes `'ascii' codec can't encode` crash when moving emails to `"Обработанные"`. Emails were processed correctly but never moved out of INBOX.

## [1.9.0] - 2026-03-19
### Added
- **`ID Клиники` column in network CSVs**: new column for 1C integration, appears right after `Клиника` in both daily delta (`records_YYYY-MM-DD.csv`) and monthly master (`master_YYYY-MM.csv`) on the network share
- **`id` field in `clinics.yaml`**: each clinic can now have an `id` (e.g. `"000000001"`) that maps to the `ID Клиники` CSV column; empty string if no match or no id configured
- **`detect_clinic()` returns 3-tuple**: `(clinic_name, extract_comment, clinic_id)` — backward-compatible via unpacking
- **Test**: `test_clinic_id_returned` verifies clinic ID flows from yaml through detection (88 pass, 16 skip)

### Notes
- `master.xlsx`, `master.csv` backup, and email report xlsx are **unchanged** — `ID Клиники` is CSV-only for 1C
- No impact on dedup key

## [1.8.4] - 2026-03-19
### Fixed (Refactoring — audit follow-up)
- **Shared dedup key (#69/#78)**: extracted `record_key()`, `clean_dedup_val()`, `norm_date_pad()` to `parsers/utils.py` — eliminates 3x duplication across `main.py` and `writer.py`; single source of truth for dedup logic
- **Shared xlsx builder (#79)**: extracted `build_styled_xlsx_bytes()` to `writer.py`, `notifier.py:_build_xlsx()` now delegates to it — eliminates duplicated styled xlsx creation code
- **Column order validation (#77)**: `_append_to_existing()` now validates that the existing master file's headers match expected `COLUMNS` order and logs a warning on mismatch
- **`passwords.index()` → `enumerate()` (#66)**: `zetta_handler.py:try_passwords()` no longer uses O(n) list scan for audit log
- **`csv_mod` alias (#82)**: removed unnecessary `import csv as csv_mod` in `_export_to_network()`

### Security
- **Env var warning (#75)**: `_expand_env()` now logs a warning when a `${VAR}` placeholder has no matching environment variable — previously silent passthrough
- **Healthcheck URL validation (#76)**: `_ping_healthcheck()` now requires `https://` scheme — blocks potential SSRF via config tampering
- **Clinic matcher memory (#80)**: `_file_to_text()` now reads max 50 rows per sheet instead of entire xlsx — prevents memory exhaustion on large files

### Changed
- **Unused imports removed**: `openpyxl`, `io` imports removed from `notifier.py` (now delegated to `writer.py`)

## [1.8.3] - 2026-03-19
### Security
- **`diagnostic.py` env var expansion**: config now expands `${VAR}` placeholders — previously used literal strings, which could encourage putting plaintext passwords in config
- **`diagnostic.py` SSL context**: IMAP connection now uses `ssl.create_default_context()` + 60s timeout (matching `fetcher.py`)
- **`_safe()` DDE injection**: formula injection guard now also prefixes cells starting with `|` (pipe) to block DDE payloads
- **Filename length truncation**: attachment filenames in `fetcher.py` now truncated to 200 chars to prevent OS path limit issues

### Fixed
- **`diagnostic.py` SQLite migration**: `load_processed_ids()` now reads from SQLite `processed_ids.db` (with JSON fallback) — was stuck on deprecated `processed_ids.json` since v1.6.0
- **`diagnostic.py` UID SEARCH**: IMAP search now uses `uid('SEARCH')` / `uid('FETCH')` for stable UIDs (matching `fetcher.py`)
- **Dead `company` variable**: removed always-None `company` variable and its dead fallback in `generic_parser.py`
- **Redundant import**: removed duplicate `sys` import in `main.py:run_test_mode()` (already at module level)

### Changed
- **`.gitignore` cleanup**: added `processed_ids.db` (was missing since SQLite migration in v1.6.0)

## [1.8.2] - 2026-03-19
### Fixed
- **Network share clutter**: documented that `master_file` must stay local — lock file, empty xlsx, and CSV backup were leaking to network share when `master_file` pointed there. Updated `config.example.yaml` with clear comments explaining the two-file contract (`records_*.csv` + `master_*.csv`)

## [1.8.0] - 2026-03-19
### Fixed (Critical — code review v3)
- **`disconnect()` crash (#48)**: `fetcher.disconnect()` no longer crashes with `AttributeError` when `connect()` never succeeded — added `hasattr(self, 'mail')` guard
- **Password email processed too early (#49)**: password emails only marked as processed when extraction actually succeeds — failed extractions will be retried next run (both pre-scan and main loop)

### Fixed (High — code review v3)
- **IMAP re-download loop (#50)**: emails producing only duplicate records are now moved to processed folder — previously re-downloaded and re-parsed every run
- **Double master.xlsx read (#51)**: `load_existing_keys()` reads column headers once and reuses, instead of opening the file twice
- **col_familia guard (#53/#54)**: 5 parsers (psb, sber, soglasie, kaplife, yugoriya) now return `[]` with error log when 'Фамилия' column not found — prevents silent 0-record output
- **Cumulative zip size limit (#55)**: zip extraction now tracks cumulative extracted size and stops at 500MB total (in addition to existing 100MB per-entry limit)

### Fixed (Medium — code review v3)
- **Monthly report date filter (#56)**: dates now zero-padded before month matching — `1.3.2026` correctly matches `03.2026` suffix
- **Sender detection hardened (#57)**: `detect_by_sender()` now uses exact email match or `@domain` suffix check for full-email sender keys — substring-only matching limited to partial keys like `spiskirobot`
- **Config validation (#58)**: `load_config()` now validates required keys (`imap.server`, `imap.username`, `imap.password`, `processing.temp_folder`, `processing.processed_ids_file`) on startup with clear error messages

### Added (Tests — code review v3)
- **`_safe()` tests (#52)**: 13 tests for formula injection prevention — covers `=`, `+`, `@`, `\t`, `\r`, `-` prefixes, negative numbers, None, empty string
- **`zetta_handler` tests (#59)**: 17 tests for sender detection, monthly/per-email password extraction, zip extraction, zip slip blocking, invalid zip handling
- **`clinic_matcher` tests (#59)**: 9 tests for clinic keyword matching, longest-keyword-wins, extract_comment flag, missing clinics.yaml, policy comment extraction
- **Dedup edge case tests (#59)**: `ё`→`е` normalization, date zero-padding, clinic-in-key differentiation
- **Sender detection tests (#59)**: 8 tests for exact match, domain match, partial key, case insensitivity, all known senders
- Test count: 50 → 103 (87 self-contained + 16 fixture-dependent)

## [1.7.1] - 2026-03-19
### Fixed (Low — code review v2)
- **`_safe()` negative numbers (#34)**: `-500` no longer gets formula-injection prefix — only prefixes `-` when not followed by a digit
- **BOM mid-file (#35)**: `utf-8-sig` encoding only used for new CSV files; appends use plain `utf-8` — fixes BOM bytes appearing mid-file (writer.py, main.py x2)
- **`.bak` cleanup (#36)**: `master.xlsx.bak` removed after successful write — prevents stale backup accumulation
- **`wb.close()` (#37)**: `_build_xlsx()` in notifier.py now closes workbook in `finally` block
- **`import json` (#38)**: moved from top-level to local import in fetcher.py migration path (only used once)
- **Efficient processed IDs (#39)**: `_save_processed_ids()` now only inserts newly-added IDs (diff from snapshot) instead of re-inserting entire set
- **Pre-scan password marking (#40)**: password-only emails now marked as processed during pre-scan pass
- **Zip bomb guard (#41)**: 100MB per-entry size limit before extraction in zetta_handler.py
- **Filename sanitization (#42)**: control characters stripped from attachment filenames in fetcher.py
- **`format_date` datetime formats (#43)**: added `DD.MM.YYYY HH:MM:SS` and `DD/MM/YYYY HH:MM:SS` format support
- **`get_cell_str` float-to-int (#44)**: `123456.0` now renders as `"123456"` instead of `"123456.0"`
- **FIO column guard (#46)**: 6 parsers (absolut, reso, vsk, euroins, renins, zetta) now return `[]` with error log when FIO column not found
- **Config graceful default (#47)**: `config['output']['master_file']` uses `.get()` with `'./output/master.xlsx'` default in both `run_imap_mode` and `run_local_mode`
- Updated test for `.bak` cleanup behavior
- **Test mode encoding**: fixed `--test` crash on Windows (cp1252 console) — replaced emoji with ASCII, force utf-8 stdout

## [1.7.0] - 2026-03-19
### Fixed (Medium — code review v2)
- **Cross-run dedup broken (#24)**: clinic detection now runs BEFORE the dedup filter in `process_file()` — previously `Клиника` was always empty in the dedup key for incoming records, so duplicates were never detected against the master
- **Network share formula injection (#25)**: `_export_to_network()` now applies `_safe()` to all CSV cell values (daily delta + monthly master)
- **Monthly report month filter (#26)**: changed `str.contains()` to `str.endswith()` for precise month matching — prevents false matches on malformed dates
- **Per-email error handling (#27)**: main fetch loop now wrapped in per-email try/except — one malformed email no longer aborts the entire run and loses all collected results
- **IMAP FETCH response guard (#28)**: structural check on `msg_data` shape before indexing — prevents crash on malformed/expunged responses
- **UID EXPUNGE (#29)**: `move_to_folder()` now uses `UID EXPUNGE` (RFC 4315) to only expunge our UIDs, with fallback to plain EXPUNGE
- **File handle leak (#30)**: `_file_to_text()` and `extract_policy_comment()` in `clinic_matcher.py` now use `with pd.ExcelFile()` — prevents file handle leaks on Windows
- **Shadowed variable (#31)**: removed duplicate `processed_imap_ids = []` initialization in `run_imap_mode()`
- **Zetta no-xlsx detection (#32)**: `try_passwords()` now checks if zip contains xlsx files before trying passwords — prevents infinite retry on zips with no xlsx content
- **Alfa header fail-safe (#33)**: `alfa.py` now returns `[]` with error log when header row is not found, instead of silently parsing with hardcoded column indices

## [1.6.3] - 2026-03-19
### Changed / Fixed (Low)
- **FIO casing**: all 10 parsers that weren't uppercasing FIO now do — consistent `UPPERCASE` in master.xlsx across all 15 parsers
- **IMAP socket timeout**: 60-second timeout added to `IMAP4_SSL` — prevents indefinite hang on unresponsive server
- **`_clinics` cache**: added `reload_clinics()` helper to invalidate module-level cache (useful in tests)
- **Header length guard**: replaced magic `60` with named constant `_MAX_HEADER_LEN` in `clinic_matcher.py`
- **Detector sheet comment**: added comment explaining why only sheet 0 is scanned for format detection
- **Redundant import**: removed inline `from clinic_matcher import extract_policy_comment` in `main.py` (already imported at module level)
- **Dead code**: deleted unused `_build_csv()` function and orphaned `import csv` from `notifier.py`
- **Dead code (#19)**: `if False` on MOVE command was already removed in v1.6.0 IMAP UID migration — marked resolved
- **CLAUDE.md version**: updated from v1.5.0 to v1.6.3

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
