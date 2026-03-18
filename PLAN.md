# Project Status

All planned work is complete as of 2026-03-18. Current version: **v1.5.0**

---

## Completed features

| Version | Feature | Status |
|---------|---------|--------|
| v1.0.0 | Initial pipeline — 15 parsers, detection, dedup, email, network share, SQLite, security | ✅ |
| v1.0.1 | Security cleanup — private data removed from git history, `.gitignore` hardened | ✅ |
| v1.0.2 | CSV delimiter `,` → `;` for 1C import | ✅ |
| v1.0.3 | `Дата обработки` populated in email and share CSVs | ✅ |
| v1.1.0 | Monthly master CSV on network share (`master_YYYY-MM.csv`) | ✅ |
| v1.2.0 | Clinic detection — `Клиника` column, `clinic_matcher.py`, `clinics.yaml` | ✅ |
| v1.2.2–1.2.3 | Clinic config fixes (`Гарибальди 36`, remove Дентал Фэнтези) | ✅ |
| v1.2.4 | Remove CSV from email attachment | ✅ |
| v1.3.0 | Monthly master xlsx on last day of month (email attachment) | ✅ |
| v1.3.1 | `Дата обработки` — date-only `DD.MM.YYYY` (removed time) | ✅ |
| v1.3.2 | `ё` → `е` normalization in dedup key | ✅ |
| v1.4.0 | IMAP email move to "Обработанные" after successful processing | ✅ |
| v1.4.1 | `Клиника` added to dedup key — same patient, different clinic = separate record | ✅ |
| v1.5.0 | `Комментарий в полис` universal extractor (column header + free-text strategies) | ✅ |

---

## Pending / future

- [ ] Tests for `clinic_matcher.py`
- [ ] Multi-clinic files (one file = two clinics) — post-call decision when needed
- [ ] Per-clinic comment column headers if other insurers use different header names
