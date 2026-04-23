# Cleanup Follow-up Plan (tomorrow)

**Goal:** Address the two highest-ROI cleanup items from the multi-perspective review (consensus score 8.0/10, grade A−). Both flagged by all 3 reviewers as "do this before the next feature."

**When:** 2026-04-24 or later — not blocking production launch.

**Tech stack:** Python 3.12. No new dependencies.

---

## Task 1: Split `main.py` (currently 803 lines, doing too much)

**Why:** Flagged by all three reviewers. `main.py` mixes CLI parsing, config loading, pipeline orchestration, network CSV export, monthly attachment logic, healthcheck, pidfile, logging setup. Every future change has to navigate it. Agent 3 summary: *"kitchen drawer... that's where solo projects tip over."*

**Target layout:**

```
main.py          — CLI + config + logging setup + pidfile + dispatch to mode (~150 lines)
pipeline.py      — run_imap_mode(), run_local_mode(), run_test_mode(), process_file()
exports.py       — _export_to_network(), _migrate_csv_header(), _attach_monthly_if_last_day(), _ping_healthcheck()
```

Keep `_expand_env`, `load_config`, `make_stats`, `setup_logging` in `main.py` for now (they're CLI-adjacent).

### Steps

- [ ] **Step 1: Create `pipeline.py`** — move `run_imap_mode`, `run_local_mode`, `run_test_mode`, `process_file`, `should_skip_file`, `convert_xls_to_xlsx`, `_dedup_xls_xlsx`, `_quarantine`. Import anything they need (fetcher, detector, parsers, writer, clinic_matcher, notifier, pandas). Leave `_record_key` — decide where it lives once you see the imports.

- [ ] **Step 2: Create `exports.py`** — move `_export_to_network`, `_migrate_csv_header`, `_attach_monthly_if_last_day`, `_ping_healthcheck`. These are all "after-batch-write" concerns.

- [ ] **Step 3: Update `main.py`** — at the `if __name__ == '__main__':` block, import from the new modules. Test count should stay at 148 passing — if any test fails with an `ImportError`, fix the import in the test file (they currently `from main import ...` for things that have moved).

- [ ] **Step 4: Run full suite**
  ```bash
  python -m pytest tests/ -v 2>&1 | tail -5
  ```
  Expected: 148 passed / 17 skipped (unchanged).

- [ ] **Step 5: Commit**
  ```bash
  git commit -am "refactor: split main.py into main/pipeline/exports modules"
  ```

**Risk:** tests may break because they import helpers directly from `main`. Fix is mechanical — update test imports to the new module. No behavior changes.

**Estimated time:** 2–3 hours including test-import cleanup.

---

## Task 2: Move diagnostic scripts out of repo root

**Why:** Repo root currently has `check_zetta_password.py`, `dump_zetta_password_email.py`, `diagnostic.py` sitting alongside production modules. Agent 1: *"right now the repo root doesn't tell you what's 'the system' vs. 'ad-hoc debug aid' — that confusion compounds over years."*

### Steps

- [ ] **Step 1: Create `scripts/` directory**
  ```bash
  mkdir scripts
  ```

- [ ] **Step 2: Move diagnostic scripts**
  ```bash
  git mv check_zetta_password.py scripts/
  git mv dump_zetta_password_email.py scripts/
  git mv diagnostic.py scripts/
  ```

- [ ] **Step 3: Fix imports in the moved scripts** — they currently `from main import _expand_env` etc. which works from repo root. After the move, they need `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` at the top, OR run them as modules: `python -m scripts.diagnostic`. Simpler option: keep the path hack at the top.

- [ ] **Step 4: Update `RECOVERY.md`** — section 6 references `python3 dump_zetta_password_email.py`. Change to `python3 scripts/dump_zetta_password_email.py`.

- [ ] **Step 5: Delete stale artifacts at repo root**
  ```bash
  rm -f tmp.db.db processed_ids.json.bak diagnostic_report.json
  ```
  (All gitignored already — they're just visual clutter in `ls`.)

- [ ] **Step 6: Create `scripts/README.md`** — one-paragraph index:
  ```markdown
  # Diagnostic Scripts

  Ad-hoc tools for investigating pipeline issues. Not part of the production pipeline.

  - `diagnostic.py` — cross-references inbox vs master, reports gaps
  - `dump_zetta_password_email.py` — prints body of Zetta monthly password emails
  - `check_zetta_password.py` — quick inbox scan for password emails
  ```

- [ ] **Step 7: Run suite + commit**
  ```bash
  python -m pytest tests/ -v 2>&1 | tail -5
  git commit -am "refactor: move diagnostic scripts to scripts/ subdirectory"
  ```

**Risk:** almost none. Scripts are ops tools, not imported by production code.

**Estimated time:** 30 minutes.

---

## After both: release v1.10.11

- [ ] Bump `__version__` in `main.py` to `1.10.11`
- [ ] CHANGELOG entry under `### Refactored`
- [ ] `git tag v1.10.11 && git push origin v1.10.11`
- [ ] VM deploy: `git pull && python3 main.py --dry-run`

---

## Deferred (for later, not tomorrow)

- **Declarative parser schema** (Agent 3's biggest future-proofing recommendation) — 19 parsers are ~80% the same. A `Parser(company, date_format, columns={...})` spec would turn "new insurer" from a Python PR into a YAML entry. Large scope, not urgent. Revisit in ~2 months when you've added insurer #14 manually and it annoys you enough.
- **Commit synthetic test fixtures** — replace the 16 skipped tests with fixtures that don't contain real PII. Agent 1 flagged. ~3 hours, unlocks CI confidence.
- **`last_run.json` status file** — Agent 2's observability suggestion. 30 min, useful for ops. Pick up whenever you have a slow hour.
- **Clean-VM SETUP.md dry-run** — Agent 2 wanted one teammate to execute SETUP.md fresh. Valuable but not code work.

---

## Tomorrow's pick-up notes

- Start with Task 1 (split main.py). Do it cold — don't try to "improve" anything while splitting, just move code.
- Test after each step. If pytest breaks, fix imports one-by-one.
- If you're short on time, stop after Task 1 + release v1.10.11. Task 2 can wait.

Good night.
