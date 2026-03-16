# Fix Plan — email-processor

Comprehensive fix plan organized by phase. Each phase can be deployed independently.
Items marked with `[x]` are already fixed.

---

## Phase 0: Critical (DONE)
*Deployed 2026-03-16*

- [x] **C1** Rotate Yandex password, purge from git history
- [x] **C2** Zip Slip guard in `zetta_handler.py` — validate extracted path stays inside target dir
- [x] **B1** Try cp866 then utf-8 for zip password encoding (`zetta_handler.py`)
- [x] **B2** `convert_xls_to_xlsx` returns `None` on failure (`main.py:86`)
- [x] **B3** Remove `nrows=100` from `parsers/zetta.py` — was silently truncating bulk files
- [x] **S1** Filename sanitization with `re.sub` + `os.path.basename` (`fetcher.py:218`)
- [x] **S3** Log password length only, not prefix chars (`zetta_handler.py`)
- [x] **B5** Use Message-ID only for dedup, not IMAP sequence numbers (`fetcher.py`)
- [x] **B7** Fix `strahovatel` leak across rows (`parsers/luchi.py`)
- [x] **B8** Fix `strahovatel` leak across rows (`parsers/energogarant.py`)
- [x] **B10** Guard `start_date` against overwrite in `parsers/soglasie.py`
- [x] **P1** Vectorized `load_existing_keys` with `usecols=` (`writer.py`)
- [x] **P2** Single file-open in `detector.py`, cleaner text blob

---

## Phase 1: Data integrity bugs (DONE)
*Deployed 2026-03-16*

- [x] **1.1 — `zetta_handler.py:154-160` — extracted path appended even on failure
**NEW** The `for encoding` loop appends `full_path` to `extracted` unconditionally. If both cp866 and utf-8 fail, a non-existent file path is returned, causing `FileNotFoundError` downstream.
**Fix:** Move `extracted.append(full_path)` inside the try block after successful `zf.extract()`, use a `success` flag.

- [x] **1.2 — `fetcher.py:221` — `get_payload(decode=True)` can return `None`
**NEW** Malformed MIME part → `TypeError` on `f.write(None)` → crashes entire email loop.
**Fix:** `payload = part.get_payload(decode=True); if payload is None: continue`

- [x] **1.3 — `main.py:139` — dedup truthy check on empty set
`and existing_keys:` is `False` for empty `set()`. Dedup silently skipped on first run with empty master.
**Fix:** Change to `and existing_keys is not None:`

- [x] **1.4 — `writer.py:115` — `ws.max_row` includes empty styled rows
Causes blank row gaps between batches. Autofilter range includes blanks.
**Fix:** Scan backwards from `max_row` to find last non-empty row.

- [x] **1.5 — `fetcher.py:100,124` — locale-dependent `%b` in strftime
**NEW** On Russian locale, `%b` → `"Мар"` instead of `"Mar"`. IMAP SEARCH fails silently (returns 0 results).
**Fix:** Use English month names manually: `MONTHS = ['Jan','Feb',...]; f"{d.day:02d}-{MONTHS[d.month-1]}-{d.year}"`

- [x] **1.6 — `parsers/soglasie.py:36-50` — открепление date assigned as start_date
**NEW** For detachment files, the detachment date is wrongly stored as `start_date`.
**Fix:** Check if keyword is `'открепление'` → assign to `end_date` instead.

- [x] **1.7 — `parsers/ingos.py:116` — contract end date used as patient end date
When `col_otkr` column not found, `dogovor_end` is assigned as personal end date for all patients.
**Fix:** Leave `end_date = None` when column not found (don't guess).

- [x] **1.8 — `parsers/reso.py:48` — `find_col('окончан')` too broad
Can match "Дата окончания договора" instead of the per-patient end column.
**Fix:** `find_col('оконч', 'обслуж')` to require both keywords.

- [x] **1.9 — `parsers/renins.py:64` — `'с '... ' по '` date detection too broad
Matches non-date Russian phrases. Can pick up INN/OGRN as fake dates.
**Fix:** Add `re.search(r'\d{2}\.\d{2}\.\d{4}', val_str)` guard.

- [x] **1.10 — `parsers/alfa.py:29-56` — hardcoded column indices
**NEW** Only parser without header-based detection. Silent data corruption if AlfaStrakhovanie changes layout.
**Fix:** Add `find_col()` header-based mapping like all other parsers.

- [x] **1.11 — `main.py:289` — test mode passes .xls after failed conversion
**NEW** After `convert_xls_to_xlsx` returns `None`, `or filepath` passes raw .xls → confusing error.
**Fix:** Print conversion failure and `continue`.

---

## Phase 2: Security hardening

### 2.1 — `fetcher.py:77,228` — sender domain check bypassable via display name
Substring match on full `From` header matches display names.
**Fix:** Use `email.utils.parseaddr()` to extract addr-only, then match domain after `@`.

### 2.2 — `notifier.py:113,120,129,141` — unsanitized values in HTML email
Company names, filenames, errors from untrusted sources injected raw into HTML.
**Fix:** Wrap all f-string values with `html.escape()`.

### 2.3 — `fetcher.py:221` — no attachment size limit
Arbitrarily large attachment loaded into memory. Zip bomb risk in zetta extraction.
**Fix:** Check payload size before writing (e.g., 50MB max configurable). Check `zf.getinfo(name).file_size` before extracting.

### 2.4 — `fetcher.py:119,163,186` — monthly password `break` after first MIME part
If password is in HTML (second part), it's missed for all 3 monthly-password extraction blocks.
**Fix:** Remove `break`, try both plain and HTML parts.

### 2.5 — `zetta_handler.py:81-95` — monthly password extraction too permissive
**NEW** Any stray text line after the "period" line accepted as password → wrong password → all Zetta zips silently dropped.
**Fix:** Validate candidate matches password-like pattern (alphanumeric, 4-20 chars). Add more negative-keyword filters.

### 2.6 — `fetcher.py:58`, `notifier.py:187` — no explicit TLS context
STARTTLS path has no `context=ssl.create_default_context()`.
**Fix:** Pass explicit SSL context to both IMAP4_SSL and smtp.starttls().

---

## Phase 3: Parser refactoring (extract `parsers/utils.py`)
*Biggest maintainability win — eliminates ~400 lines of duplication*

### 3.1 — Extract `_format_date()` to `parsers/utils.py`
Identical 10-14 line function duplicated in all 15 parsers + generic_parser.

### 3.2 — Extract `build_header_map()` + `find_col()` to `parsers/utils.py`
Same header-building loop + closure in every parser.

### 3.3 — Extract `find_header_row()` to `parsers/utils.py`
Same 5-line loop checking `range(min(25, len(df)))` for keywords in every parser.

### 3.4 — Extract `assemble_fio()` to `parsers/utils.py`
FIO combination with `pd.notna` guards repeated in 7 parsers (sber, yugoriya, soglasie, psb, kaplife, ingos, luchi).

### 3.5 — Consolidate `convert_xls_to_xlsx`
Three implementations: `main.py:66`, `kaplife.py:18`, `renins.py:20`. `main.py` already calls it before dispatching to parsers — parser copies are redundant.

### 3.6 — Extract `_extract_monthly_password_from_msg()` in `fetcher.py`
Same password-extraction block copy-pasted 3 times (lines 104-120, 154-165, 177-187).

---

## Phase 4: Robustness & cleanup

### 4.1 — `zetta_handler.py:180-185` — redundant try/except in `try_passwords`
`unzip_with_password` already catches all exceptions internally. Outer wrap is dead code.
**Fix:** Remove try/except, call directly.

### 4.2 — `kaplife.py:22`, `renins.py:24` — subprocess not wrapped for FileNotFoundError
If LibreOffice not installed, unhandled `FileNotFoundError` crashes the parser.
**Fix:** Wrap in `try/except (FileNotFoundError, subprocess.TimeoutExpired)`.

### 4.3 — `kaplife.py:26` — fragile `filepath + 'x'` path construction
Works by coincidence for `.xls` but not `.XLS`. Redundant after Phase 3.5.
**Fix:** Remove once `convert_xls_to_xlsx` is consolidated.

### 4.4 — `fetcher.py:255` — shared `zetta_extracted/` dir never cleaned
Files accumulate across runs. Same-named file from different zip overwrites previous.
**Fix:** Use `tempfile.mkdtemp(dir=self.temp_folder)` per zip, delete after processing.

### 4.5 — `fetcher.py:46-54` — `processed_ids.json` grows unbounded
Every email ID ever seen is stored. Gets slow over months.
**Fix:** Cap to last 30-60 days of IDs on save. Or switch to SQLite.

### 4.6 — `main.py:52-60` — `should_skip_file` rebuilds lowercase lists per call
**Fix:** Precompute lowercased lists once at startup, pass them in or store on config.

### 4.7 — `main.py:256,275` — glob may double-process .xls + .xlsx
If a `.xls` was converted to `.xlsx` in a previous run, both appear in the glob.
**Fix:** Deduplicate by stem name; prefer `.xlsx` when both exist.

### 4.8 — `main.py:103-104` — original .xls leaked in temp after conversion
**NEW** Original `.xls` path is never deleted after successful conversion in IMAP mode.
**Fix:** Save original path, delete after successful conversion.

### 4.9 — `diagnostic.py:87-90` — config key mismatch
**NEW** Uses `host`/`user` but config has `server`/`username`.
**Fix:** Add correct fallback keys.

### 4.10 — `writer.py:113` — silent fallback to active sheet
**NEW** If "Данные" sheet is missing (manual rename), falls back to active sheet silently.
**Fix:** Raise clear error instead of silent fallback.

### 4.11 — `writer.py:68-70` — mutates caller's record dicts
**NEW** Adds `Источник файла` and `Дата обработки` to original dicts in place.
**Fix:** Copy records before mutation, or document the contract.

---

## Recommended order

| Session | Phase | Effort | Impact |
|---------|-------|--------|--------|
| 1 | Phase 1 (1.1–1.5) | ~30 min | Fixes crashes + silent data loss |
| 2 | Phase 1 (1.6–1.11) | ~30 min | Fixes parser data integrity |
| 3 | Phase 2 (2.1–2.6) | ~30 min | Security hardening |
| 4 | Phase 3 (3.1–3.4) | ~45 min | Parser utils extraction (biggest refactor) |
| 5 | Phase 3 (3.5–3.6) | ~15 min | Consolidate remaining duplication |
| 6 | Phase 4 (4.1–4.11) | ~30 min | Cleanup and robustness |
