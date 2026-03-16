# Fix Plan — email-processor

**STATUS: ALL PHASES COMPLETE** (deployed 2026-03-16)

41 issues fixed across 4 phases. See git history for details.

---

## Completed phases

| Phase | Items | Description |
|-------|-------|-------------|
| Phase 0 | 13 | Critical: Zip Slip, IMAP dedup, filename sanitization, parser bugs |
| Phase 1 | 11 | Data integrity: date misassignment, dedup edge cases, column detection |
| Phase 2 | 6 | Security: sender spoofing, HTML injection, TLS, attachment limits |
| Phase 3 | 16 parsers | Refactoring: `parsers/utils.py` extracted, -678 net lines |
| Phase 4 | 9 | Robustness: temp cleanup, processed_ids cap, config fixes, writer safety |

## Post-fix improvements (deployed 2026-03-16)

- Master file backup (`master.xlsx.bak`) before every write
- Quarantine folder for files that fail parsing
- Healthcheck ping (healthchecks.io compatible)
- `break` → `continue` in all parser footer detection
- `${VAR_NAME}` env var expansion in config.yaml
- `config.yaml` removed from git tracking

---

## Future work

- **Tests** — pytest + fixture .xlsx files per insurer. Biggest remaining risk.
- **SQLite for processed IDs** — replace `processed_ids.json` with timestamped DB for replay/audit.
- **Master → CSV backup** — periodic human-readable export as safety net.
- **Parser confidence scoring** — log low-confidence format detections in `detector.py`.
