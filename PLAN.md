# Clinic Detection — Implementation Plan

**Feature:** Automatically determine which clinic (Подразделение) each record belongs to, based on a configurable keyword lookup table (`clinics.yaml`), and add a `Клиника` column to all outputs.

---

## Step 1 — Schema & config ✅ DONE (2026-03-18)

| # | Task | Status |
|---|------|--------|
| 1.1 | Create `clinics.yaml` with keyword → clinic name mapping | ✅ |
| 1.2 | Add `Клиника` to `COLUMNS` in `writer.py` | ✅ |
| 1.3 | Add `COLUMN_WIDTHS` entry for `Клиника` in `writer.py` | ✅ |

## Step 2 — Clinic matcher module ✅ DONE (2026-03-18)

| # | Task | Status |
|---|------|--------|
| 2.1 | Create `clinic_matcher.py` — loads `clinics.yaml`, exposes `detect_clinic(filepath) -> str` | ✅ |
| 2.2 | `detect_clinic()` reads entire xlsx/xls into text, searches for keywords (case-insensitive) | ✅ |
| 2.3 | Keywords sorted longest-first to prevent partial matches | ✅ |
| 2.4 | No match → `"⚠️ Не определено"` + log warning | ✅ |

## Step 3 — Integrate into pipeline ✅ DONE (2026-03-18)

| # | Task | Status |
|---|------|--------|
| 3.1 | Inject `Клиника` into records in `main.py` `process_file()` | ✅ |
| 3.2 | Clinic detection runs once per file (file-level) | ✅ |
| 3.3 | `--test` mode shows detected clinic in console output | ✅ |

## Step 4 — Outputs ✅ DONE (2026-03-18)

| # | Task | Status |
|---|------|--------|
| 4.1 | `master.xlsx` — Клиника column added | ✅ |
| 4.2 | `master.csv` — follows COLUMNS | ✅ |
| 4.3 | Email attachment xlsx/csv — follows COLUMNS | ✅ |
| 4.4 | Network share daily + monthly CSV — follows COLUMNS | ✅ |

## Step 5 — Testing & docs

| # | Task | Status |
|---|------|--------|
| 5.1 | Tests for `clinic_matcher.py` | ⬜ |
| 5.2 | Tested with `--test` on real files — all 6 detections correct | ✅ |
| 5.3 | Update `CLAUDE.md` | ⬜ |
| 5.4 | Update `README.md` | ⬜ |

---

## Pending / future

- [ ] Multi-clinic files — one file covers patients for two clinics (post-call decision needed)
- [ ] Tests for `clinic_matcher.py`
- [ ] Docs update (CLAUDE.md, README.md)
