# Changelog

## [1.10.11] - 2026-04-23
### Fixed
- **C1 — Healthcheck honesty**: `notifier.send_report` now appends `"SMTP send failed: ..."` to `stats['errors']` on any SMTP exception, so `_ping_healthcheck` correctly flips to `/fail`. Previously SMTP failures were logged only, leaving healthcheck green while reports silently stopped.
- **C2 — Mass duplication guard**: `writer.load_existing_keys` now raises `RuntimeError` when master.xlsx lacks the `Клиника` column. Previous silent fallback to 4-field dedup caused every historical row to re-insert on the next write because new records carried 5-field keys. Defensive fix — master files since v1.9 already have the column. Path is logged (not embedded in the exception) to avoid leaking it via the email report.
- **C3 — Formula injection**: `writer._safe` tightened — only values matching `^-?\d+(\.\d+)?$` (pure signed numbers) bypass the apostrophe prefix. Previously `-1+cmd|'/C calc'!A1` passed through unescaped because `s[1].isdigit()` was True. Applies to both xlsx and CSV writes.
- **C4 — VSK Страхователь column**: `parsers/vsk.py` now reads `Страхователь` from `Холдинг` (preferred) with fallback to `Место работы`. Previously all VSK records had the workplace string in the Страхователь field. Legacy records in master.xlsx remain wrong until the same insured is re-sent.
- **C5 — RESO false positives**: removed the overly broad content rule `('reso', ('ресо',))` from `detector.CONTENT_RULES`. The remaining `('ресо-гарантия',)` rule covers real RESO files; the bare substring was silently mis-routing any file mentioning 'ресо' (e.g. 'Ресорс-М') to the RESO parser.

### Added
- `tests/test_vsk_strahovatel.py` — 2 tests for Холдинг-over-workplace preference and fallback.
- `tests/test_writer.py::TestSafe` — 5 new tests (dash+digit formula, dash+digit+@, dash+digits+letters, negative int, negative decimal).
- `tests/test_writer.py::TestLoadExistingKeys::test_raises_if_klinika_column_missing` — schema regression guard.
- `tests/test_notifier.py::test_smtp_failure_recorded_in_stats_errors` — SMTP → healthcheck signal.
- `tests/test_detector.py::test_reso_not_matched_on_bare_substring` — RESO substring regression.
- `docs/superpowers/plans/2026-04-23-critical-bugs-c1-c5.md` — implementation plan for this release.

## [1.10.10] - 2026-04-23
### Fixed
- Pidfile lock (`main.py`) now distinguishes `BlockingIOError` (another instance running — harmless, exit 0) from `PermissionError` (lockfile owned by another UID — exit 2 with stderr). Previously `EACCES` was silently treated as "already running" so a leftover-root lockfile would make cron silently no-op forever.
- Zetta extract dirs now tracked up front in `run_imap_mode` and cleaned in `finally`, so a `process_file` exception mid-loop no longer leaks temp dirs for files in the same zip.
- `SETUP.md` and `.env.example` no longer reference a `HEALTHCHECK_URL` env var — the code reads `healthcheck_url` directly from `config.yaml`; docs updated to match.
- `CLAUDE.md` version stamp bumped to v1.10.10 (was still showing v1.10.8 post-v1.10.9 release).

## [1.10.9] - 2026-04-23
### Fixed
- Pidfile lock on `main.py` (`./logs/main.lock`, fcntl, non-blocking) prevents concurrent cron + manual runs from producing duplicate email reports or stale-dedup writes.
- Parsers (`ingos.py`, `luchi.py`) raise `HeaderNotFoundError` on missing required columns; `main.py` quarantines the file and surfaces the error (was: silent empty result → mass data loss on insurer template change).
- Zetta extraction temp directories are cleaned on password failure (was: disk leak `./temp/zetta_*` accumulating).
- `_safe_fetch_rfc822` retries on `imaplib.IMAP4.abort`, `ssl.SSLError`, `OSError` transport failures; main fetch loop now uses the helper (consolidation; removes inline retry divergence).
- `clean_dedup_val` collapses internal whitespace (tabs, `\xa0`, multiple spaces) so `"ИВАНОВ  ИВАН"` and `"ИВАНОВ ИВАН"` dedup as the same person.
- Zetta password SEARCH failure-after-retry logged at WARNING (was DEBUG — invisible in production INFO).
- `diagnostic.py` now raises `ValueError` on unresolved `${VAR}` (consistent with `main.py` since v1.10.7).
- `TestWriteBatchFailure::test_imap_mode_survives_write_failure` now also asserts `_save_processed_ids` is skipped (was passing for a different reason).

### Added
- `tests/test_header_not_found.py` — 3 tests for `HeaderNotFoundError` parser path.
- `tests/test_utils.py::TestCleanDedupVal` — 5 direct tests for whitespace / NaN handling.
- `tests/test_pipeline_resilience.py::TestMonthlyAttachmentHappyPath` — 2 tests for last-day-of-month logic.
- `tests/test_healthcheck.py` — 8 tests for `_ping_healthcheck` (empty/missing/https-guard/success/fail/trailing-slash/error/POST body).
- `tests/test_network_export.py` — 3 smoke tests for `_export_to_network` (empty/happy/timeout).
- `SETUP.md` — clean-VM onboarding guide.
- `RECOVERY.md` — 6 failure-scenario runbooks (Yandex lockout, CIFS down, master.xlsx corrupt, processed_ids.db corrupt, missed cron, stale Zetta password).
- `.env.example` — credential env-var template; `.env` added to `.gitignore`.
- `config.example.yaml` now includes `imap.zetta_password_cache`, `output.csv_export_folder`, `output.network_timeout` with explanatory comments.
- `clinics.yaml` now has a detailed usage header documenting schema, matching rules, detachment keywords, and how to add a new clinic.
- `CLAUDE.md` updated for v1.10.8 changes — password cache, SEARCH/FETCH retry helpers, UTF-7 encoding, env-var validation, pidfile lock, new Ops section, merged duplicate "Versioning & releases" heading.

### Housekeeping
- Completed plan documents (4) and stale `PLAN.md` moved to `docs/historical/`.
- Test suite: 148 passed / 17 skipped (was 124 / 17 at v1.10.8).

## [1.10.8] - 2026-04-23
### Added
- Zetta monthly password now cached to `./zetta_password.json` (gitignored, mode 0600) on successful extraction. On subsequent runs the pipeline loads the cache and skips the IMAP pre-scan entirely, making Zetta ZIP extraction immune to Yandex's intermittent `[UNAVAILABLE]` rejections of the `FROM "parollpu@zettains.ru"` filter. Cache expires automatically when `valid_to < today`. Cache save also triggers from the main-search loop's monthly-password branches, not only the pre-scan.
- New config key `imap.zetta_password_cache` (default: `./zetta_password.json`) to customize cache location.

## [1.10.7] - 2026-04-23
### Fixed
- Main IMAP SEARCH now retries up to 3× on `[UNAVAILABLE]` and raises on persistent failure (previously a single transient Yandex error produced a silent zero-records day)
- `_save_processed_ids()` is skipped when `write_batch_to_master` fails — prevents permanent loss of emails whose records didn't reach master.xlsx
- `load_config` raises `ValueError` on unresolved `${VAR}` in config instead of logging and passing the literal placeholder (prevents IMAP account lockout from repeated failed login with `"${IMAP_PASSWORD}"`)
- Zetta monthly-password FETCH guards against expunged UIDs (previously crashed at DEBUG level, silently losing the password)
- Zetta monthly password is only marked processed when `valid_to >= today` (prevents stale passwords from blocking re-reads after month boundary)
### Refactored
- Removed duplicate IMAP UTF-7 folder encoder; consolidated `_encode_imap_folder` static method into module-level `imap_utf7_encode` (also fixes a latent bug where the static method failed to escape `&` in folder names)

## [1.10.6] - 2026-04-23
### Fixed
- Cyrillic IMAP folder names (e.g. `Обработанные`) now encoded with IMAP modified UTF-7 (RFC 3501) before `select()` — previously `imaplib` raised `UnicodeEncodeError` and silently skipped the processed folder during Zetta password scan
- Added `import email.message` to `fetcher.py` — latent `AttributeError` on module import when imported outside `main.py`
- Zetta monthly password SEARCH now retries up to 3× on `[UNAVAILABLE]` server error before giving up — intermittent server failures were silently dropping the password and causing all Zetta ZIPs to fail
- UID from IMAP SEARCH decoded to str before `FETCH` — some servers reject raw bytes in the command argument
- `dump_zetta_password_email.py` made self-contained (no `fetcher` import), checks SEARCH response type, searches with `SINCE` date to avoid full-mailbox scan

## [1.10.3] - 2026-04-23
### Fixed
- `_print_summary` replaced `print()` with `logger.info()` — cron ASCII stdout was raising `UnicodeEncodeError` on Cyrillic error messages, silently killing the pipeline before email/export ran
- Each post-processing step (network export, monthly attach, notifier) now has its own `try/except` so one failure no longer silently prevents the others from running

## [1.10.2] - 2026-04-03
### Fixed
- Empty-date error message now includes FIO names of affected records (not just filename + count)

## [1.10.1] - 2026-04-03
### Fixed
- Zetta detachment letter format (`снять с медицинского обслуживания`) now recognized as detachment — no clinic assigned, no warning
- Zetta parser extracts `Дата открепления` as `Конец обслуживания` in detachment files (previously both dates were empty)
- Records with both start and end dates empty now emit a warning and surface in the email report errors section

## [1.10.0] - 2026-04-02
### Fixed
- Filter empty/blank recipients before SMTP send — `send_report()` and `_build_message()` both now strip falsy/whitespace-only entries from the recipients list
- Log rotation: `RotatingFileHandler` caps `processor.log` and `audit.log` at 50 MB total (10 MB × 5 backups)
- LibreOffice return code and output file size now checked in `convert_xls_to_xlsx` — exits with `None` on non-zero exit or zero-byte output
- Healthcheck ping failure now surfaces in email report `stats['errors']`
- Newline character added to formula injection guard in `_safe()`
- `format_date` now recognizes `DD-MM-YYYY` and `YYYY.MM.DD` date formats
- Generic parser labels unknown company as `'Неизвестна (generic)'` for traceability in email report
### Tests
- Detachment detection regression tests: PSB откр → empty clinic, PSB прикр → Гарибальди 15, Alfa snyat → empty clinic
- `test_safe_prefixes_newline`, `test_format_date_dash_separated`, `test_format_date_dot_year_first`, `test_generic_parser_unknown_sc_label`, `test_log_rotation_uses_rotating_handler`
### Notes
- `config.yaml` is gitignored — add `processed_folder: "Обработанные"` under `imap:` on the VM manually

## [1.9.15] - 2026-04-02
### Fixed
- **To: header included blank recipients** — `_build_message()` now applies the same empty/blank filter to `msg['To']` as `send_report()` uses for the SMTP envelope. Previously the `To:` header could contain empty strings from config.
- **Test robustness** — `test_notifier.py`: `from notifier import send_report` moved to module level; `mock_send.assert_called_once()` added before `call_args` access for a clear failure message if `_send` is never invoked.

## [1.9.14] - 2026-04-02
### Fixed
- **Detachment detection too broad — attachment files got empty clinic** — tightened keyword from `'открепл'` to `'открепляем'` (matches PSB "ОТКРЕПЛЯЕМЫХ С МЕДИЦИНСКОГО ОБСЛУЖИВАНИЯ" titles) plus `'снятия с медицинского'` (matches Alfa snyat titles). Column headers like "Дата открепления" in attachment files no longer trigger.
- **Гарибальди 15 not matched for PSB "Детская стоматология № 2"** — added space variant `'Детская стоматология № 2'` to clinics.yaml (PSB uses a space before the digit, existing keyword had no space).

## [1.9.13] - 2026-04-02
### Fixed
- **Detachment files no longer warn about missing clinic** — `detect_clinic()` now detects "открепл" keyword (открепление/открепляемых) in file content and returns empty clinic `''` with no warning. Applies to all insurers. Clinic column will be empty in master for these files, which is correct — they are removals only.

## [1.9.12] - 2026-04-02
### Fixed
- **Комментарий в полис not extracted for Alfa "Гарибальди 36" files** — added `'группа, № договора'` to `_COMMENT_COLUMNS` to match the column header used in Alfa's snyat/prikr file format.

## [1.9.11] - 2026-03-24
### Fixed
- **Critical: pipeline survives write failure** — `write_batch_to_master` wrapped in try/except in both IMAP and local modes. On failure: error in email report, healthcheck pings /fail, emails stay in INBOX for re-fetch, stats cleared to avoid phantom record counts.
- **`_attach_monthly_if_last_day` errors now in email report** — was only logging, same pattern as v1.9.10 CSV fix.
- **Zetta zip extraction failures now in email report** — "All passwords failed" and "no passwords found" were only in VM logs, now surfaced via `stats['errors']`.
- **Regression tests for Zetta password with `%?{}` characters** — the exact scenario from v1.9.9 now has test coverage (plaintext and HTML bold format).

## [1.9.10] - 2026-03-24
### Fixed
- **Network CSV export errors now in email report**: daily and monthly CSV write failures were only logged, not appended to `stats['errors']` — so the email report (moved before export in v1.9.8) still didn't show them. Now both are reported.

## [1.9.9] - 2026-03-24
### Fixed
- **Zetta monthly password regex too restrictive**: password `3RpNk%?}*t` was rejected because `%`, `?`, `{`, `}` weren't in the allowed charset. Replaced with `[\x21-\x7e]+` (any printable ASCII, no Cyrillic) — future-proof against password character changes.
- **Misleading "no xlsx found" log message**: when password fails but zip contains xlsx files, now logs "wrong password?" instead of "no xlsx found".

## [1.9.8] - 2026-03-24
### Fixed
- **Network export errors now visible in email report**: moved `_export_to_network()` before `send_report()` in both IMAP and local modes — previously export ran after email was sent, so timeouts/failures were only in VM logs and invisible to user. The 10s timeout still prevents hanging on dead mounts.

## [1.9.7] - 2026-03-21
### Fixed
- **Standardize `dtype=str` across all parsers**: 12 parsers were missing `dtype=str` in `pd.read_excel()`, risking float coercion of policy numbers (e.g. `12345` → `12345.0`)
- **Case-normalize `Клиника` in dedup key**: prevents false duplicates if clinic name casing ever varies
- **Sync clinic IDs with production**: `clinics.yaml` IDs updated to match 1C mapping on VM
- **CLAUDE.md version updated** to match actual release

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
