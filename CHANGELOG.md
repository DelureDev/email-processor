# Changelog

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
