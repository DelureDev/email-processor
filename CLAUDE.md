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
# Run test suite (50 tests)
pytest tests/ -v

# Run a single test file
pytest tests/test_utils.py -v
```

Tests in `tests/test_parsers.py` and `tests/test_detector.py` require fixture files in `test_files/` (gitignored — contains real data). Other test files are self-contained.

`.xls` → `.xlsx` conversion requires LibreOffice installed (`libreoffice --headless`).

Production VM: `adminos@n8n:~/email-processor`. Deploy via `git push` then `git pull` on VM.

## Architecture

**Pipeline flow (IMAP mode):**
`fetcher.py` → `detector.py` → `parsers/` → `writer.py` → `notifier.py`

1. **`fetcher.py` (`IMAPFetcher`)** — connects to Yandex IMAP, filters emails by subject keywords, downloads `.xlsx`/`.xls`/`.zip` attachments to `./temp/`. Tracks processed message IDs (RFC 2822 `Message-ID` only) in `processed_ids.json` (capped at 5000 entries) to avoid reprocessing. Two-pass logic: first collects all passwords from Zetta/Sber password emails, then extracts password-protected zips in a second pass.

2. **`zetta_handler.py`** — all logic for password-protected ZIPs (Zetta Insurance and Sberbank). Handles two Zetta password flows: monthly passwords from `parollpu@zettains.ru` and per-email passwords from `pulse.letter@zettains.ru`. `try_passwords()` tries cp866 then utf-8 encoding for each password. Zip Slip guard validates extracted paths stay inside extraction directory.

3. **`detector.py`** — two-stage format detection:
   - Stage 1: sender email → format name via `SENDER_FORMAT_MAP` (fast, skips file read)
   - Stage 2: content-based — reads first 25 rows, matches Russian keyword patterns (`'ресо-гарантия'`, `'югория'`, etc.)
   - Fallback: generic detection by column header patterns (`generic_fio`, `generic_fio_split`)

4. **`parsers/`** — one `.py` file per insurer, each exports a `parse(filepath) -> list[dict]` function. Registered in `parsers/__init__.py` as the `PARSERS` dict mapping format name → function. All parsers return records with the canonical 7-field schema: `ФИО`, `Дата рождения`, `№ полиса`, `Начало обслуживания`, `Конец обслуживания`, `Страховая компания`, `Страхователь`. (`Источник файла` and `Дата обработки` are added by `writer.py`.)

5. **`writer.py`** — appends records to `master.xlsx` (openpyxl). Creates styled file with header row if it doesn't exist; appends to existing. `load_existing_keys()` uses vectorized pandas ops with `usecols=` to load only the 4 dedup columns.

6. **`main.py`** — CLI entry point. Deduplication key is `(ФИО.upper(), № полиса, Начало обслуживания, Конец обслуживания)`. The `stats` dict is passed by reference through the pipeline and populated by `process_file()`.

## Adding a new insurer

1. Create `parsers/new_company.py` with `parse(filepath) -> list[dict]`
2. Add to `PARSERS` in `parsers/__init__.py`
3. Add sender entry to `SENDER_FORMAT_MAP` in `detector.py`
4. Add content-based keyword fallback in `detect_format()` in `detector.py`
5. Test: `python main.py --test ./folder_with_sample_file`

## Configuration

`config.yaml` holds IMAP/SMTP credentials, output path, skip rules, and dedup settings. **Never commit credentials** — load from env vars or keep `config.yaml` in `.gitignore`. The `skip_rules.filename_contains` list skips files whose names contain specific substrings (e.g. `_all.` for aggregate files). `processed_ids.json` persists processed message IDs across runs.

## Shared parser utilities

All parsers import from `parsers/utils.py`:
- `format_date(val)` — normalize any date to `DD.MM.YYYY`
- `find_header_row(df, keywords, max_rows)` — scan for header row by keyword tuple
- `build_header_map(df, header_row)` — build `{lowered_header: col_idx}` dict
- `find_col(headers, *keywords)` — find column index by keyword match
- `assemble_fio(df, row, col_f, col_i, col_o)` — combine split FIO columns
- `get_cell_str(df, row, col)` — safe cell-to-string with None handling

## Fix history

All issues tracked in `PLAN.md` (Priority 1–3, 10 items) are resolved as of 2026-03-17.

## Observability features (added 2026-03-17)

- **Confidence scoring** — `detector.py` emits `logger.warning` for generic-fallback detections (`GENERIC_FIO`, `GENERIC_FIO_SPLIT`). Sender-based and content-rule detections remain `INFO`. Watch for "Low-confidence detection" in logs to find insurers that need a proper rule added.

- **CSV backup** — `writer.py` exports `master.csv` (UTF-8 BOM) alongside `master.xlsx` after every successful write. No config needed.

- **Audit log** — `main.py` configures a separate `audit` logger writing to `./logs/audit.log`. Events logged (never the actual password value): `ZETTA_MONTHLY_PASSWORD_EXTRACTED`, `PASSWORD_EXTRACTED`, `ZIP_EXTRACT`. Audit log file path can be overridden via `config.yaml` → `logging.audit_file`.

- **Skipped-file breakdown in email report** — `notifier.py` now shows why files were skipped (by rule / unknown format / empty) as a breakdown on the summary line, and lists any xlsx files that hit a skip rule by name.

- **Daily delta email attachments** — email report attaches `records_YYYY-MM-DD.xlsx` (styled) and `records_YYYY-MM-DD.csv` with only this run's new records. No more full master.xlsx attachment.

- **Network share export** — `main.py` writes the daily delta CSV to a configured network folder after each run. Set `output.csv_export_folder` in `config.yaml` (e.g. `/mnt/storage`). Mount the share via `/etc/fstab` with CIFS credentials. `stats['new_records']` accumulates new records during the run and is consumed by both notifier and network export.
