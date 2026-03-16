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

## Phase 2: Security hardening (DONE)
*Deployed 2026-03-16*

- [x] **2.1 — `fetcher.py:77,228` — sender domain check bypassable via display name
Substring match on full `From` header matches display names.
**Fix:** Use `email.utils.parseaddr()` to extract addr-only, then match domain after `@`.

- [x] **2.2 — `notifier.py:113,120,129,141` — unsanitized values in HTML email
Company names, filenames, errors from untrusted sources injected raw into HTML.
**Fix:** Wrap all f-string values with `html.escape()`.

- [x] **2.3 — `fetcher.py:221` — no attachment size limit
Arbitrarily large attachment loaded into memory. Zip bomb risk in zetta extraction.
**Fix:** Check payload size before writing (e.g., 50MB max configurable). Check `zf.getinfo(name).file_size` before extracting.

- [x] **2.4 — `fetcher.py:119,163,186` — monthly password `break` after first MIME part
If password is in HTML (second part), it's missed for all 3 monthly-password extraction blocks.
**Fix:** Remove `break`, try both plain and HTML parts.

- [x] **2.5 — `zetta_handler.py:81-95` — monthly password extraction too permissive
**NEW** Any stray text line after the "period" line accepted as password → wrong password → all Zetta zips silently dropped.
**Fix:** Validate candidate matches password-like pattern (alphanumeric, 4-20 chars). Add more negative-keyword filters.

- [x] **2.6 — `fetcher.py:58`, `notifier.py:187` — no explicit TLS context
STARTTLS path has no `context=ssl.create_default_context()`.
**Fix:** Pass explicit SSL context to both IMAP4_SSL and smtp.starttls().

---

## Phase 3: Parser refactoring (DONE)
*Deployed 2026-03-16*

- [x] **3.1** Extract `format_date()` to `parsers/utils.py`
- [x] **3.2** Extract `build_header_map()` + `find_col()` to `parsers/utils.py`
- [x] **3.3** Extract `find_header_row()` to `parsers/utils.py`
- [x] **3.4** Extract `assemble_fio()` + `get_cell_str()` to `parsers/utils.py`
- [x] **3.5** Remove redundant `_ensure_xlsx` from `kaplife.py` and `renins.py` (main.py handles conversion)
- [x] **3.6** Extract `_extract_monthly_pwd_from_msg()` in `fetcher.py` (done in Phase 2)
- [x] All 16 parsers refactored: reso, vsk, absolut, sber, yugoriya, psb, euroins, zetta, alfa, soglasie, kaplife, renins, ingos, luchi, energogarant, generic_parser

---

## Phase 4: Robustness & cleanup (DONE)
*Deployed 2026-03-16*

- [x] **4.1** Remove redundant try/except in `try_passwords` (`zetta_handler.py`)
- [x] **4.2** Remove `_ensure_xlsx` from `kaplife.py`, `renins.py` (done in Phase 3)
- [x] **4.3** Remove fragile `filepath + 'x'` path construction (done in Phase 3)
- [x] **4.4** Use per-zip `tempfile.mkdtemp` instead of shared `zetta_extracted/` dir, clean up after processing (`fetcher.py`, `main.py`)
- [x] **4.5** Cap `processed_ids.json` to 5000 entries to prevent unbounded growth (`fetcher.py`)
- [x] **4.6** Precompute lowercased skip rules once via `_build_skip_rules` cache (`main.py`)
- [x] **4.7** Deduplicate .xls+.xlsx by stem in local/test mode — prefer .xlsx (`main.py`)
- [x] **4.8** Clean up converted .xlsx and Zetta extract dirs in IMAP mode (`main.py`)
- [x] **4.9** Fix config key mismatch: `server`/`username` fallbacks + `master_file` lookup (`diagnostic.py`)
- [x] **4.10** Raise clear error if "Данные" sheet missing instead of silent fallback (`writer.py`)
- [x] **4.11** Copy records before adding metadata fields to avoid mutating caller's dicts (`writer.py`)
