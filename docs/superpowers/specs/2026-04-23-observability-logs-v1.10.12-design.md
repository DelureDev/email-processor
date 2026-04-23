# v1.10.12 — Observability: run summary, email log tail, log-level audit

**Goal:** Make the VM log file self-sufficient for 5-minute triage, and make the email report carry a log excerpt when something goes wrong — without adding new infrastructure.

**Non-goals:**
- No push alerts (Telegram/SMS/Slack)
- No separate summary log file — the signal lives inside `processor.log`
- No structured JSON logs
- No log aggregation, dashboards, or retention changes
- No per-insurer heartbeat tracking

---

## Component 1 — `RUN_SUMMARY` line

### What it is

Every cron run ends with **one** log line at INFO level, emitted regardless of success, errors, or exceptions:

```
2026-04-23 15:30:23,456 [INFO] main: [RUN_SUMMARY] status=OK mode=imap files=5 records=120 errors=0 unknown=0 skip_rule=1 clinic_miss=0 smtp=OK network=OK duration=23s
2026-04-23 16:00:12,789 [INFO] main: [RUN_SUMMARY] status=FAIL mode=imap files=3 records=0 errors=1 unknown=0 skip_rule=0 clinic_miss=0 smtp=FAIL network=OK duration=5s
2026-04-23 16:30:05,102 [INFO] main: [RUN_SUMMARY] status=CRASH mode=imap exception=RuntimeError duration=12s
```

### Fields

| Field | Values | Notes |
|---|---|---|
| `status` | `OK` \| `FAIL` \| `CRASH` | `OK` = no errors and no surface-able issues; `FAIL` = `stats['errors']` non-empty OR `unknown_files`/`unmatched_clinics`/`missing_comments` non-empty; `CRASH` = uncaught exception reached the finally block |
| `mode` | `imap` \| `local` \| `test` | Matches CLI entry point |
| `files` | integer | `stats['files_processed']` |
| `records` | integer | `stats['total_records']` |
| `errors` | integer | `len(stats['errors'])` |
| `unknown` | integer | `len(stats['unknown_files'])` |
| `skip_rule` | integer | `len(stats['skipped_files'])` |
| `clinic_miss` | integer | `len(stats['unmatched_clinics'])` |
| `smtp` | `OK` \| `FAIL` \| `SKIP` | `OK` = delivered; `FAIL` = exception caught by `send_report`; `SKIP` = disabled or short-circuited by `only_if_new_records` |
| `network` | `OK` \| `FAIL` \| `SKIP` | `OK` = export succeeded; `FAIL` = exception or timeout; `SKIP` = no `csv_export_folder` configured or no new records |
| `duration` | `<seconds>s` | Wall clock from run start to RUN_SUMMARY emit |
| `exception` | `<ExceptionClassName>` | Only present when `status=CRASH` |

### Emission contract

- Emitted from `main.py` inside a `try/finally` wrapping `run_imap_mode` and `run_local_mode` bodies.
- Must survive: `SystemExit`, `KeyboardInterrupt`, `RuntimeError`, any `Exception`. Python's `finally` handles all three — we do NOT catch `BaseException` ourselves.
- Never raises. If computing a field fails, the field is omitted; the line still prints.
- `stats['smtp_status']` and `stats['network_status']` are populated at the respective call sites (notifier, network export) as `OK`/`FAIL`/`SKIP`. Default is `SKIP`.

### Operator workflow

On the VM:
```bash
grep RUN_SUMMARY logs/processor.log | tail -10
```
- All `status=OK` → healthy.
- `status=FAIL` → scan the email report OR read the preceding log lines.
- `status=CRASH` → unexpected — open the log for the exception traceback.
- **Missing runs** (e.g., last entry at 15:00 when it's now 16:15) → cron is dead.

---

## Component 2 — Email log tail on failure

### What it is

When the daily email report has `has_problems == True` (already computed in `notifier._build_message` at line ~77), append a collapsible HTML `<details>` block at the end of the email body containing the last log lines from this run.

### Rendering

```html
<details style="margin-top: 24px;">
  <summary style="cursor: pointer; color: #666;">Последние строки лога (для диагностики)</summary>
  <pre style="font-family: monospace; font-size: 11px; background: #f9f9f9; padding: 12px; overflow-x: auto; max-height: 400px;">
2026-04-23 15:30:00,123 [INFO] main: Starting IMAP fetch
2026-04-23 15:30:05,456 [ERROR] writer: Dedup columns missing from /home/.../master.xlsx: ['Клиника']
...
  </pre>
</details>
```

### Source and filter

- Source: the log file at `config['logging']['file']` (default `./logs/processor.log`).
- Filter: only lines whose leading timestamp is `>= stats['run_start']`.
- `stats['run_start']` is a `datetime` object set at the very top of `run_imap_mode` / `run_local_mode`.

### Size cap

- Max 20 KB of log text in the email (to avoid client truncation).
- If the current-run lines exceed 20 KB, keep the **tail** (most recent 20 KB) and prepend a one-line marker: `[... предыдущие строки пропущены, смотрите processor.log на VM ...]`.

### Safety

- If the log file can't be read (missing, permission, disk error), skip the block silently — don't break the email.
- HTML-escape every log line via `html.escape` before embedding.
- No credentials/passwords appear in logs today (verified in the 2026-04-23 review). If this changes, we'd need to sanitize before embedding — but it's not currently a risk.

### Rollout

- Only fires when `has_problems` is True. All-green runs get a concise email (current behavior).
- No config flag needed — always on for failure emails.

---

## Component 3 — Log-level audit

### Scope

Walk every `logger.error(` and `logger.warning(` call across `main.py`, `fetcher.py`, `writer.py`, `notifier.py`, `detector.py`, `clinic_matcher.py`, `parsers/*.py`, `zetta_handler.py`, `zetta_password_cache.py`. Approximately 40-50 call sites.

### Rules

| Level | Use when | Examples |
|---|---|---|
| `logger.error` | Event that should flip healthcheck red (ends up in `stats['errors']`). These are the incidents that require operator action. | "Cannot read master headers", "SMTP send failed", "IMAP SEARCH failed after retries", "Write batch failed, skipping processed_ids save" |
| `logger.warning` | User-visible but non-fatal. Pipeline continues, but the event is anomalous. | "Low-confidence format detection", "Zetta password cache corrupt, refreshing", "Sanitized formula-like cell value" |
| `logger.info` | Normal operation. | "Detected format: VSK (sender)", "Parsed 120 records from X", "Report sent to ..." |

### Process

For each call:
1. Decide the correct level per the rules above.
2. If currently `logger.error` but should be `logger.warning` (e.g., parser returned 0 rows from a known-empty notification file), downgrade.
3. If currently `logger.warning` but should be `logger.error` (e.g., "failed to connect" that abandons the pipeline), upgrade AND ensure the event is appended to `stats['errors']`.
4. If currently silent (swallowed) but should be visible, add a `logger.warning` or `logger.error` call.

### Invariant established by this audit

After v1.10.12, this command on the VM returns exactly the set of events that would flip healthcheck red for that day:
```bash
grep "\[ERROR\]" logs/processor.log | grep "^$(date +%Y-%m-%d)"
```

No mix of styles, no silent errors, no noise.

### Out of scope

- Do not rewrite error messages. Do not restructure try/except blocks.
- Do not add new logging calls for events that were intentionally silent (e.g., normal cron tick start — that's INFO already).
- If a level change requires also appending to `stats['errors']` to uphold the invariant, do that. Otherwise just the level change.

---

## Acceptance criteria

1. **RUN_SUMMARY present:** `grep RUN_SUMMARY logs/processor.log | wc -l` after a week of cron runs equals the number of cron invocations that reached Python (crashes included, cron-skipped-entirely not counted).
2. **CRASH captured:** a deliberate exception injected mid-run produces a `status=CRASH exception=...` RUN_SUMMARY line.
3. **Email log tail:** a run with a failure scenario produces an email whose HTML source contains a `<details>` block with `[ERROR]` lines from that run.
4. **Log-level invariant:** `grep "\[ERROR\]" logs/processor.log` within a test run equals the count of entries in `stats['errors']`.
5. **No regressions:** existing test suite (currently 158 pass / 17 skip) still green.

---

## File map

| File | Change |
|---|---|
| `main.py` | Add `run_start = datetime.now()` at top of each mode; wrap mode body in `try/finally`; emit `[RUN_SUMMARY]`; populate `stats['smtp_status']` / `stats['network_status']` defaults; small level audit on existing logger calls |
| `notifier.py` | In `_build_message`, if `has_problems`, call a new `_build_log_tail_html(log_path, run_start)` helper and append to body; populate `stats['smtp_status']` in success/failure branches |
| `fetcher.py`, `writer.py`, `detector.py`, `clinic_matcher.py`, `parsers/*.py`, `zetta_handler.py`, `zetta_password_cache.py` | Level audit only, mechanical edits |
| `tests/test_run_summary.py` | New — unit tests for summary-line emitter and crash path |
| `tests/test_notifier.py` | New tests — log tail block rendered on failure, missing log file handled gracefully, size cap enforced |

---

## Testing approach

- **RUN_SUMMARY emitter:** pure function given `stats` + `run_start` + `status` + optional `exception`, returns the log string. Tested with table of input/output.
- **Crash path:** mock a step inside `run_imap_mode` to raise; assert the finally block emitted `status=CRASH exception=...`.
- **Log tail helper:** pass a sample log file and a `run_start`, assert returned string contains only lines from after that timestamp, respects 20 KB cap.
- **Email assembly:** extend `test_notifier.py` to verify the `<details>` block presence and absence based on `has_problems`.
- **Full run integration:** run `python main.py --local <fixture-dir>` in a test, verify the produced log file ends with a valid `RUN_SUMMARY` line.

---

## Release

- Patch bump: **v1.10.12**.
- Deploy: standard `git pull` on VM (no migration needed).
- Rollback: safe to revert single commit; no state changes.

---

## Known caveats

- **`test` mode** (`--test`) currently doesn't write anything; adding RUN_SUMMARY there is still useful for parity, so it ships too.
- **Log file path variations:** `config['logging']['file']` defaults to `./logs/processor.log` but can be overridden. The email log-tail helper accepts the configured path — if it's wrong/unreachable, the block is silently omitted.
- **Timezone:** `run_start` uses `datetime.now()` (system local time) to match existing timestamp format in the log. No timezone handling added here — consistent with rest of the codebase.
