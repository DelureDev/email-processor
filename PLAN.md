# Clinic Detection — Implementation Plan

**Feature:** Automatically determine which clinic (Подразделение) each record belongs to, based on a configurable keyword lookup table (`clinics.yaml`), and add a `Клиника` column to all outputs.

---

## Step 1 — Schema & config

| # | Task | Status |
|---|------|--------|
| 1.1 | Create `clinics.yaml` with keyword → clinic name mapping (user fills in real data) | ⬜ |
| 1.2 | Add `Клиника` to `COLUMNS` in `writer.py` (after `Страхователь`, before `Источник файла`) | ⬜ |
| 1.3 | Add `COLUMN_WIDTHS` entry for `Клиника` in `writer.py` | ⬜ |

## Step 2 — Clinic matcher module

| # | Task | Status |
|---|------|--------|
| 2.1 | Create `clinic_matcher.py` — loads `clinics.yaml`, exposes `detect_clinic(filepath) -> str` | ⬜ |
| 2.2 | `detect_clinic()` reads entire xlsx/xls into text, searches for keywords (case-insensitive) | ⬜ |
| 2.3 | First keyword match wins → return clinic name. No match → return `"⚠️ Не определено"` | ⬜ |
| 2.4 | Log warning when no clinic matched for a file | ⬜ |

## Step 3 — Integrate into pipeline

| # | Task | Status |
|---|------|--------|
| 3.1 | In `main.py` `process_file()`: call `detect_clinic()` after parsing, inject `Клиника` into each record | ⬜ |
| 3.2 | Clinic detection runs once per file (file-level, not per-row) | ⬜ |
| 3.3 | `--test` mode: show detected clinic in console output | ⬜ |

## Step 4 — Outputs

| # | Task | Status |
|---|------|--------|
| 4.1 | `master.xlsx` — new column appears automatically (COLUMNS updated in step 1) | ⬜ |
| 4.2 | `master.csv` — same, follows COLUMNS | ⬜ |
| 4.3 | Email attachment xlsx/csv — same, follows COLUMNS | ⬜ |
| 4.4 | Network share daily + monthly CSV — same, follows COLUMNS | ⬜ |
| 4.5 | Email report body — include clinic in stats breakdown if relevant | ⬜ |

## Step 5 — Testing & docs

| # | Task | Status |
|---|------|--------|
| 5.1 | Add tests for `clinic_matcher.py` (match, no-match, case-insensitive, multiple keywords) | ⬜ |
| 5.2 | Test with `--test` on real files from `test_files/` to verify detection | ⬜ |
| 5.3 | Update `CLAUDE.md` — document clinic detection and `clinics.yaml` format | ⬜ |
| 5.4 | Update `README.md` — mention clinic column in schema table | ⬜ |

---

## Design decisions

- **Lookup, not parsing** — we don't rely on each insurer's file structure. Scan full file text for known keywords → works uniformly across all 15 formats.
- **File-level** — one clinic per file. If multiple keywords match, first match wins.
- **Config-driven** — `clinics.yaml` can be updated without code changes. Adding a new clinic = 1 yaml entry.
- **No match = visible warning** — `"⚠️ Не определено"` in the column + log warning. Nothing slips through silently.

## Blockers

- [ ] **User to fill `clinics.yaml`** with real clinic names and all keyword variations used by insurers
