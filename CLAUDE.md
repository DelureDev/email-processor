# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Test parsing on local files (no writing, safe to run)
python main.py --test ./some_folder

# Process local folder of xlsx files → write to master
python main.py --local ./some_folder

# Full IMAP pipeline → write master + send email report
python main.py

# IMAP pipeline without writing or sending (debug)
python main.py --dry-run

# Disable deduplication
python main.py --no-dedup

# Use alternate config
python main.py --config path/to/config.yaml
```

```bash
# Run test suite (104 pass, 16 skip without test_files/ fixtures)
pytest tests/ -v

# Run a single test file
pytest tests/test_utils.py -v
```

Tests in `tests/test_parsers.py` and `tests/test_detector.py` require fixture files in `test_files/` (gitignored — contains real data). Other test files are self-contained.

`.xls` → `.xlsx` conversion requires LibreOffice installed (`libreoffice --headless`).

Production VM: deploy via `git push` then `git pull` on VM.

## Architecture

**Pipeline flow (IMAP mode):**
`fetcher.py` → `detector.py` → `parsers/` → `clinic_matcher.py` → `writer.py` → `notifier.py`

1. **`fetcher.py` (`IMAPFetcher`)** — connects to IMAP, filters emails by subject keywords, downloads `.xlsx`/`.xls`/`.zip` attachments to `./temp/`. Skips own report emails (`"Обработка списков ДМС"` in subject). Tracks processed message IDs (RFC 2822 `Message-ID` only) in SQLite (capped at 5000 entries) to avoid reprocessing. Two-pass logic for password-protected zips: first resolves Zetta/Sber passwords (cache → IMAP pre-scan → main-loop capture), then extracts zips in a second pass. The Zetta monthly password is cached to disk (`imap.zetta_password_cache`, default `./zetta_password.json`, mode 0600) on first discovery; subsequent runs skip the IMAP pre-scan entirely while the cache is still valid. IMAP SEARCH and FETCH are wrapped with retry helpers (`_search_with_retry`, `_safe_fetch_rfc822`) to survive Yandex `[UNAVAILABLE]` errors, expunged UIDs, and transport-level disconnects. Cyrillic folder names (e.g. `Обработанные`) are encoded with modified UTF-7 (RFC 3501) via `imap_utf7_encode` before every `select()` / `COPY`. Emails are moved to `imap.processed_folder` only AFTER batch write succeeds — if the write fails, emails stay in INBOX for re-fetch and `_save_processed_ids()` is skipped too.

2. **`zetta_handler.py`** — all logic for password-protected ZIPs (Zetta Insurance and Sberbank). Handles two Zetta password flows: monthly passwords from `parollpu@zettains.ru` and per-email passwords from `pulse.letter@zettains.ru`. `try_passwords()` tries cp866 then utf-8 encoding for each password. Zip Slip guard validates extracted paths stay inside extraction directory.

3. **`detector.py`** — two-stage format detection:
   - Stage 1: sender email → format name via `SENDER_FORMAT_MAP` (fast, skips file read)
   - Stage 2: content-based — reads first 25 rows, matches Russian keyword patterns (`'ресо-гарантия'`, `'югория'`, etc.)
   - Fallback: generic detection by column header patterns (`generic_fio`, `generic_fio_split`)

4. **`parsers/`** — one `.py` file per insurer, each exports a `parse(filepath) -> list[dict]` function. Registered in `parsers/__init__.py` as the `PARSERS` dict mapping format name → function. All parsers return records with the canonical 7-field schema: `ФИО`, `Дата рождения`, `№ полиса`, `Начало обслуживания`, `Конец обслуживания`, `Страховая компания`, `Страхователь`. (`Клиника`, `Комментарий в полис`, `Источник файла`, `Дата обработки` are added by `main.py`/`writer.py`.)

5. **`clinic_matcher.py`** — runs once per file after parsing. `detect_clinic(filepath, subject=None)` returns `(clinic_name, extract_comment, clinic_id)`. Scans both the xlsx content (first 50 rows, lowercased) and the email subject against `clinics.yaml` keywords (longest-first to prevent partial matches). Subject scanning is essential for VSK where clinic name is in the email subject, not the file. No match → `"⚠️ Не определено"`. If `extract_comment=True`, `extract_policy_comment(filepath)` is also called — two strategies: (1) scan rows 0-19 for known column headers (`_COMMENT_COLUMNS`), take first non-empty data cell below; (2) scan all rows for free-text cells >20 chars containing program description keywords. Current `_COMMENT_COLUMNS` include `'группа, № договора'` (Alfa attachment format). Detachment/removal files (`открепляем`, `снятия с медицинского`, or `снять с медицинского` in content) return `('', False, '')` — empty clinic, no warning, no comment extraction.

6. **`clinics.yaml`** — configurable clinic lookup table. Each entry has `name`, `id` (for 1C), `keywords` list, and optional `extract_comment: true` flag. Keywords sorted longest-first automatically at load time. Add new clinics here without touching Python code.

7. **`writer.py`** — appends records to `master.xlsx` (openpyxl). Creates styled file with header row if it doesn't exist; appends to existing. Auto-migrates old-layout files (inserts missing `Клиника`/`Комментарий в полис` columns). `load_existing_keys()` uses `pd.read_excel(dtype=str)` with `usecols=` to load the 5 dedup columns — raises `RuntimeError` on failure to prevent silent mass duplication. CSV backup (`master.csv`) written inside the file lock alongside xlsx.

8. **`main.py`** — CLI entry point. `process_file(filepath, ..., sender=None, subject=None)` handles detection, parsing, clinic matching, and dedup for a single file. Deduplication key is `(ФИО.upper().replace('Ё','Е'), № полиса, Начало обслуживания, Конец обслуживания, Клиника)`. Execution order in IMAP mode: fetch → parse → write batch → move emails to processed → send email report → export to network share (with 10s timeout) → healthcheck ping. On last day of month, `_attach_monthly_if_last_day()` filters master.xlsx for current-month records and attaches as xlsx to the email report.

## Adding a new insurer

1. Create `parsers/new_company.py` with `parse(filepath) -> list[dict]`
2. Add to `PARSERS` in `parsers/__init__.py`
3. Add sender entry to `SENDER_FORMAT_MAP` in `detector.py`
4. Add content-based keyword fallback in `detect_format()` in `detector.py`
5. Test: `python main.py --test ./folder_with_sample_file`

## Configuration

`config.yaml` holds IMAP/SMTP credentials, output path, skip rules, and dedup settings. **Never commit credentials** — load from env vars or keep `config.yaml` in `.gitignore`. The `skip_rules.filename_contains` list skips files whose names contain specific substrings (e.g. `_all.` for aggregate files). Processed message IDs are tracked in SQLite (`processed_ids.db`).

Key config options added since v1.0:
- `imap.processed_folder` — folder name to move processed emails into (e.g. `"Обработанные"`)
- `output.csv_export_folder` — network share path for daily + monthly CSV export
- `output.network_timeout` — seconds to wait for network share accessibility probe (default: 10)
- `output.network_write_timeout` — seconds to wait for each CSV write before giving up (default: 30). Caps daemon-thread `join()` so a stalled CIFS write can't pin the process. See v1.10.15.
- `imap.zetta_password_cache` — path to the Zetta monthly-password disk cache (default: `./zetta_password.json`). Gitignored, mode 0600, auto-expires when `valid_to < today`. See CHANGELOG v1.10.8.
- `clinics.yaml` — separate file, not inside `config.yaml`

## Shared parser utilities

All parsers import from `parsers/utils.py`:
- `format_date(val)` — normalize any date to `DD.MM.YYYY`
- `find_header_row(df, keywords, max_rows)` — scan for header row by keyword tuple
- `build_header_map(df, header_row)` — build `{lowered_header: col_idx}` dict
- `find_col(headers, *keywords)` — find column index by keyword match
- `first_col(headers, *keyword_sets)` — try multiple keyword sets, return first match (replaces `find_col() or find_col()` chains that break on column 0)
- `assemble_fio(df, row, col_f, col_i, col_o)` — combine split FIO columns
- `get_cell_str(df, row, col)` — safe cell-to-string with None handling

## Versioning & releases

This project uses **semantic versioning** (`MAJOR.MINOR.PATCH`):
- `PATCH` (1.0.x) — bug fixes, parser tweaks, minor improvements
- `MINOR` (1.x.0) — new insurer added, new feature
- `MAJOR` (x.0.0) — breaking changes to schema or pipeline

### After making changes, always:

1. Update `__version__` in `main.py`
2. Add an entry to `CHANGELOG.md` under the new version
3. Commit, tag, and push — **always push to remote after committing** (don't wait to be asked):

```bash
git add -A
git commit -m "feat/fix/refactor: description"
git tag v1.2.3
git push origin main
git push origin v1.2.3
```

4. Deploy to VM — always include this step after pushing, without waiting to be asked:
```bash
# On VM:
git pull
```

### Changelog format (`CHANGELOG.md`):

```markdown
## [1.2.3] - YYYY-MM-DD
### Added / Fixed / Changed / Security
- Short description of change
```

**Never skip the tag step after meaningful changes.** Patch bumps are fine for small fixes — the important thing is that every pushed change has a corresponding version so the VM always runs a known, tagged release.

## VM terminal constraint

**Never give the user multiline code to paste into the VM terminal.** The SSH terminal adds leading spaces to every pasted line, causing `IndentationError` every time. This includes **any `python3 -c "..."` whose quoted body contains a newline** — even short lines break on paste.

Decision tree before posting a VM command:
1. Does the command contain a newline inside quotes? → **FORBIDDEN.** Write a script file instead.
2. Does `python3 -c` contain `:` (function/with/if block)? → **FORBIDDEN.** Python blocks can't be one physical line.
3. Shell pipeline on one physical line (grep, ls, ps, tail, cat)? → OK.
4. True one-expression `python3 -c "expr"` with no newline? → OK.

**Preferred path for VM Python checks:**
- Write a small `diag_*.py` in the repo, commit+push
- Tell user: `git pull && python3 diag_foo.py`
- Delete or move under `scripts/` when done

**For config reads, prefer shell over Python**: `grep '^smtp:' -A 20 config.yaml` beats any inline Python block.

## Fix history

See `CHANGELOG.md` for per-version details. Current version: **v1.10.16**.

## Security hardening

- **Credentials** — `config.yaml` uses `${IMAP_PASSWORD}` / `${SMTP_PASSWORD}` env vars. Never commit plaintext credentials.
- **Env-var validation (v1.10.7)** — `_expand_env()` raises `ValueError` on any unresolved `${VAR}` placeholder in config. Prevents IMAP account lockout from repeated failed login with literal `"${IMAP_PASSWORD}"`.
- **Formula injection** — `writer.py` sanitizes cell values starting with `=`, `+`, `-`, `@`, `\n`, `\t`, `\r`, `|` to prevent xlsx formula injection.
- **File locking** — `writer.py` acquires exclusive `fcntl` lock around master.xlsx and master.csv writes (prevents data corruption from overlapping cron runs).
- **SMTP timeout** — 30s timeout on all SMTP operations in `notifier.py`.
- **Audit log** — separate `audit` logger writing to `./logs/audit.log`. Events: `ZETTA_MONTHLY_PASSWORD_EXTRACTED`, `PASSWORD_EXTRACTED`, `ZIP_EXTRACT`. Never logs actual password values. Override path via `config.yaml` → `logging.audit_file`.
- **Zetta password cache mode 0600 (v1.10.8)** — atomic tmp+rename write, chmod 0600 on POSIX. Gitignored. Stores the current month's password + validity window.
- **Cyrillic folder UTF-7 encoding (v1.10.6)** — all IMAP `select()` / `COPY` calls route folder names through `imap_utf7_encode()` (RFC 3501 modified UTF-7). Previously failed silently on Cyrillic folders like `Обработанные`.

## Ops

- **Manual backup** — `bash backup.sh` creates a timestamped `tar.gz` of the project (excluding `.git`, `temp/`, `__pycache__/`, `*.pyc`) in `/home/adminos/backups/email-processor/`. Keeps the 10 most recent. Safe to run anytime.
- **Setup** — see `SETUP.md` for clean-VM onboarding.
- **Failure recovery** — see `RECOVERY.md` for runbooks (Yandex lockout, CIFS mount down, corrupt master, stale password cache, missed cron).

## Observability & output

- **Confidence scoring** — `detector.py` emits `logger.warning` for generic-fallback detections. Watch for "Low-confidence detection" in logs.
- **CSV backup** — `writer.py` incrementally appends to `master.csv` (UTF-8 BOM) after every write.
- **Log rotation** — `processor.log` and `audit.log` use `RotatingFileHandler` (10 MB × 5 backups = 50 MB max each). No manual logrotate needed.
- **Dedup normalization** — dates zero-padded (`1.1.2020` → `01.01.2020`) in dedup keys for consistent matching.
- **Skipped-file breakdown** — email report shows why files were skipped (by rule / unknown format / empty) and lists any xlsx files that hit a skip rule.
- **Daily delta email** — attaches `records_YYYY-MM-DD.xlsx` (styled) with only this run's new records. No CSV in email — available on network share instead.
- **Monthly master email** — on last day of month, email also attaches `master_YYYY-MM.xlsx` with all records for the current month.
- **Network share export** — writes daily delta CSV and monthly `master_YYYY-MM.csv` to configured folder. Set `output.csv_export_folder` in `config.yaml`. Network CSVs include an extra `ID Клиники` column (after `Клиника`) for 1C integration — configured via `id` field in `clinics.yaml`.
- **`ё` → `е` normalization** — applied in both dedup key (`main.py`) and `load_existing_keys()` (`writer.py`) to prevent false duplicates.
- **Clinic column** — `Клиника` populated for every record; `"⚠️ Не определено"` if no keyword match. Part of dedup key.
- **Policy comment** — `Комментарий в полис` extracted only when clinic has `extract_comment: true` in `clinics.yaml`.
- **Zetta password cache** — monthly password persisted to `./zetta_password.json`; skips IMAP pre-scan when valid. Watch for `Using cached Zetta monthly password` in the log.
- **IMAP SEARCH retry** — password pre-scan and main SEARCH both retry 3× with 3s backoff on non-OK Yandex responses. Main SEARCH raises on persistent failure (surfaces as `stats['errors']` + red healthcheck).
- **IMAP FETCH guards** — `_safe_fetch_rfc822()` retries on transport errors (`imaplib.IMAP4.abort`, `ssl.SSLError`, `OSError`) and returns `None` for expunged UIDs.
- **Write-failure protection** — if `write_batch_to_master` fails, `_save_processed_ids()` is skipped AND emails stay in INBOX. Next run re-fetches.
- **Process-level lock** — `main.py` holds an fcntl exclusive lock on `./logs/main.lock` at startup. Prevents concurrent cron + manual runs from producing duplicate writes or duplicate email reports.
