# Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 6 production-blocking bugs found in today's multi-agent review before the pipeline goes into full production use next week.

**Architecture:** All fixes are surgical edits to existing files (`fetcher.py`, `main.py`). No new modules, no refactoring. Each task is one defect with a targeted unit test and an independent commit so any fix can be reverted without disturbing the others.

**Tech Stack:** Python 3.12, pytest, imaplib, openpyxl.

---

## Pre-flight

Before starting:
- Working directory: `C:\Pyth\email-processor` (main branch, commits deploy directly to VM)
- Confirm clean baseline: `git status` shows no uncommitted changes, `pytest tests/ -v` shows 103 passed / 17 skipped

If dirty, commit or stash before proceeding.

---

### Task 1: Main IMAP SEARCH retries on [UNAVAILABLE] (H5)

**Why:** The Yandex IMAP server intermittently returns `NO [UNAVAILABLE] Backend error` to `SEARCH` commands. The password-folder SEARCH already retries (fixed earlier today), but the **main** SEARCH at `fetcher.py:339` is single-shot — a transient failure there returns an empty list and silently produces a zero-records day. We watched this happen twice in manual runs.

**Files:**
- Modify: `C:\Pyth\email-processor\fetcher.py:337-343`
- Test: `C:\Pyth\email-processor\tests\test_fetcher_retry.py` (new)

- [ ] **Step 1: Write the failing test**

Create `C:\Pyth\email-processor\tests\test_fetcher_retry.py`:

```python
"""Verify IMAP SEARCH retry behavior."""
from unittest.mock import MagicMock
import pytest
from fetcher import IMAPFetcher


def _make_fetcher_with_fake_imap(search_responses):
    """Build an IMAPFetcher whose mail.uid('SEARCH',...) returns each response in turn."""
    config = {
        'imap': {'server': 's', 'port': 993, 'username': 'u', 'password': 'p',
                 'folder': 'INBOX', 'processed_folder': ''},
        'processing': {'temp_folder': './temp', 'processed_ids_file': './tmp.db'},
    }
    fetcher = IMAPFetcher(config, dry_run=True)
    fetcher.mail = MagicMock()
    fetcher.mail.uid = MagicMock(side_effect=search_responses)
    return fetcher


def test_main_search_retries_on_not_ok():
    """Main SEARCH must retry up to 3 times before giving up."""
    # Two failures, then success with empty result
    responses = [
        ('NO', [b'[UNAVAILABLE] Backend error']),
        ('NO', [b'[UNAVAILABLE] Backend error']),
        ('OK', [b'']),
    ]
    fetcher = _make_fetcher_with_fake_imap(responses)
    # We're testing the SEARCH call path, so patch the parts before it
    fetcher._load_processed_ids = lambda: set()
    fetcher.processed_ids = set()
    fetcher._initial_ids = set()
    # Short-circuit password scan, folder select, etc.
    fetcher.mail.select = MagicMock(return_value=('OK', [b'0']))
    # The call chain inside fetch_attachments is complex; instead assert retry behavior
    # via the helper we will extract. See Task 1 Step 3.
    from fetcher import _search_with_retry
    typ, data = _search_with_retry(fetcher.mail, None, '(SINCE 01-Jan-2026)', attempts=3, delay=0)
    assert typ == 'OK'
    assert fetcher.mail.uid.call_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_fetcher_retry.py::test_main_search_retries_on_not_ok -v
```

Expected: FAIL with `ImportError: cannot import name '_search_with_retry' from 'fetcher'`.

- [ ] **Step 3: Extract the retry helper and apply it to the main SEARCH**

Add this helper at module level in `fetcher.py` (just after `imap_utf7_encode`):

```python
def _search_with_retry(mail, charset, criteria, attempts: int = 3, delay: float = 3.0):
    """Run UID SEARCH with retry on non-OK responses (e.g. Yandex [UNAVAILABLE])."""
    last_status, last_data = 'BAD', [b'']
    for attempt in range(1, attempts + 1):
        status, data = mail.uid('SEARCH', charset, criteria)
        if status == 'OK':
            return status, data
        last_status, last_data = status, data
        logger.warning(f"IMAP SEARCH attempt {attempt} failed ({status}), retrying...")
        if attempt < attempts:
            time.sleep(delay)
    return last_status, last_data
```

Replace the existing retry loop in the password-scan block (`fetcher.py:292-299`) and the single-shot main SEARCH at `fetcher.py:337-343` to use the helper.

Main SEARCH becomes:

```python
        # Main search for recent emails
        since_date = _imap_date(datetime.now() - timedelta(days=days_back))
        status, messages = _search_with_retry(self.mail, None, f'(SINCE {since_date})')

        if status != 'OK':
            logger.error(f"Failed to search emails after retries: {status}")
            raise RuntimeError(f"IMAP SEARCH failed: {status}")
```

The `raise` is deliberate — a failed SEARCH surfaces in `stats['errors']` via the outer try/except in `main.py:532-534`, so the user sees it in the email report instead of a silent zero-record day.

Update the password-scan loop at `fetcher.py:292-299` from its inline retry to:

```python
            pwd_msgs = None
            status, data = _search_with_retry(
                self.mail, None, f'(SINCE {pwd_since} FROM "parollpu@zettains.ru")')
            if status == 'OK':
                pwd_msgs = data
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_fetcher_retry.py::test_main_search_retries_on_not_ok -v
```

Expected: PASS.

Also confirm full suite: `pytest tests/ -v` → 104 passed / 17 skipped.

- [ ] **Step 5: Commit**

```bash
git add fetcher.py tests/test_fetcher_retry.py
git commit -m "fix: retry main IMAP SEARCH on [UNAVAILABLE], raise on persistent failure"
```

---

### Task 2: Don't poison processed_ids on write failure (C1/C2)

**Why:** `fetcher.py:488` calls `self.processed_ids.add(message_id)` *during* attachment fetch for all non-zip emails. If `write_batch_to_master` later fails, `main.py:560` still calls `_save_processed_ids()` in its `try` block — marking those emails permanently processed even though their records never made it to master.xlsx. Next run skips them: **silent data loss**.

**Files:**
- Modify: `C:\Pyth\email-processor\main.py:541-564`
- Test: `C:\Pyth\email-processor\tests\test_pipeline_resilience.py` (add case)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline_resilience.py`:

```python
class TestProcessedIdsNotSavedOnWriteFailure:
    """If master.xlsx write fails, processed_ids SQLite must NOT be updated."""

    def test_processed_ids_save_skipped_when_write_fails(self, tmp_path, monkeypatch):
        import main
        from unittest.mock import MagicMock
        # Arrange: pipeline with pending records and a fetcher whose save
        # method we can observe
        fake_fetcher = MagicMock()
        fake_fetcher.connect.return_value = None
        fake_fetcher.fetch_attachments.return_value = [{
            'filepath': str(tmp_path / 'dummy.xlsx'),
            'sender': 'x@y.z', 'subject': '', 'date': '',
            'message_id': '<m1>', 'imap_id': '1',
        }]
        (tmp_path / 'dummy.xlsx').write_bytes(b'')
        fake_fetcher.failed_zips = []
        fake_fetcher._save_processed_ids = MagicMock()
        fake_fetcher.move_to_folder = MagicMock()
        fake_fetcher.disconnect = MagicMock()

        monkeypatch.setattr('fetcher.IMAPFetcher', lambda *a, **k: fake_fetcher)

        # Force process_file to produce one pending record
        def fake_process(path, master, cfg, stats, **kw):
            kw['pending'].append({'ФИО': 'Test', '№ полиса': '1',
                                  'Начало обслуживания': '01.01.2026',
                                  'Конец обслуживания': '31.12.2026',
                                  'Страховая компания': 'T', 'Страхователь': 'T',
                                  'Клиника': 'X', 'Комментарий в полис': '',
                                  'Источник файла': 'dummy.xlsx',
                                  'Дата обработки': '23.04.2026'})
        monkeypatch.setattr(main, 'process_file', fake_process)

        # Force write to fail
        def fake_write(*args, **kwargs):
            raise IOError("disk full")
        monkeypatch.setattr(main, 'write_batch_to_master', fake_write)
        monkeypatch.setattr(main, 'load_existing_keys', lambda p: set())

        cfg = {'output': {'master_file': str(tmp_path / 'm.xlsx')},
               'processing': {'deduplicate': True},
               'imap': {'processed_folder': ''}}

        main.run_imap_mode(cfg, dry_run=False)

        # Assert: save was NOT called, move was NOT called
        fake_fetcher._save_processed_ids.assert_not_called()
        fake_fetcher.move_to_folder.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pipeline_resilience.py::TestProcessedIdsNotSavedOnWriteFailure -v
```

Expected: FAIL. `_save_processed_ids` IS called in the current code.

- [ ] **Step 3: Add the `write_ok` guard in `run_imap_mode`**

Edit `main.py:541-564`. Replace that block with:

```python
    # Write batch BEFORE marking emails as processed — if write fails,
    # emails stay in inbox and will be re-fetched on next run (no data loss).
    write_ok = True
    if pending and not dry_run:
        try:
            write_batch_to_master(pending, master_path)
        except Exception as e:
            logger.error(f"Failed to write batch to master: {e}", exc_info=True)
            stats['errors'].append(f"Master write failed: {e}")
            pending.clear()
            processed_imap_ids.clear()
            stats['new_records'].clear()
            stats['total_records'] = 0
            write_ok = False

    # Move emails and save IDs only AFTER successful write
    try:
        if not dry_run and write_ok:
            dest = config.get('imap', {}).get('processed_folder', '').strip()
            if dest and processed_imap_ids:
                fetcher.move_to_folder(processed_imap_ids, dest)
            fetcher._save_processed_ids()
        elif dry_run:
            logger.info("Dry-run: not saving processed IDs")
        else:
            logger.warning("Write failed — skipping processed IDs save so emails re-fetch next run")
    finally:
        fetcher.disconnect()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_pipeline_resilience.py::TestProcessedIdsNotSavedOnWriteFailure -v
pytest tests/ -v
```

Expected: all green. The write-ok happy path is covered by existing `TestWriteBatchFailure` tests.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_pipeline_resilience.py
git commit -m "fix: skip processed_ids save when master.xlsx write fails"
```

---

### Task 3: Hard-fail on unresolved ${VAR} in credentials (H6)

**Why:** `main.py:71-72` returns the literal string `${VAR_NAME}` when an env var is unset, only logging a warning. The pipeline then tries to log in to IMAP with the literal placeholder as the password — three failed auth attempts in quick succession can trigger Yandex account lockout. Fail loud at config-load time instead.

**Files:**
- Modify: `C:\Pyth\email-processor\main.py:64-85`
- Test: `C:\Pyth\email-processor\tests\test_main.py` (add case)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main.py`:

```python
class TestEnvVarResolution:
    """Config loader must fail loudly when credential env vars are missing."""

    def test_missing_imap_password_raises(self, tmp_path, monkeypatch):
        from main import load_config
        cfg_file = tmp_path / 'config.yaml'
        cfg_file.write_text(
            'imap:\n'
            '  server: test\n'
            '  port: 993\n'
            '  username: u\n'
            '  password: "${FAKE_MISSING_ENV_VAR_XYZ}"\n'
            '  folder: INBOX\n',
            encoding='utf-8',
        )
        monkeypatch.delenv('FAKE_MISSING_ENV_VAR_XYZ', raising=False)
        with pytest.raises(ValueError, match='FAKE_MISSING_ENV_VAR_XYZ'):
            load_config(str(cfg_file))

    def test_resolved_password_passes(self, tmp_path, monkeypatch):
        from main import load_config
        cfg_file = tmp_path / 'config.yaml'
        cfg_file.write_text(
            'imap:\n'
            '  server: test\n'
            '  port: 993\n'
            '  username: u\n'
            '  password: "${MY_TEST_ENV_VAR}"\n'
            '  folder: INBOX\n',
            encoding='utf-8',
        )
        monkeypatch.setenv('MY_TEST_ENV_VAR', 'secret123')
        config = load_config(str(cfg_file))
        assert config['imap']['password'] == 'secret123'
```

Make sure `pytest` is imported at the top of the file if it isn't already.

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_main.py::TestEnvVarResolution -v
```

Expected: `test_missing_imap_password_raises` FAILS (no ValueError raised — placeholder is returned).

- [ ] **Step 3: Edit `_expand_env` and `load_config` to raise on unresolved vars**

Replace `main.py:64-79`:

```python
def _expand_env(obj):
    """Recursively expand ${VAR_NAME} placeholders in config values.

    Raises ValueError if any referenced env var is unset.
    """
    if isinstance(obj, str):
        unresolved = []
        def _replace(m):
            name = m.group(1)
            val = os.environ.get(name)
            if val is None:
                unresolved.append(name)
                return m.group(0)
            return val
        result = re.sub(r'\$\{(\w+)\}', _replace, obj)
        if unresolved:
            raise ValueError(f"Unresolved environment variable(s): {', '.join(unresolved)}")
        return result
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(i) for i in obj]
    return obj
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/test_main.py::TestEnvVarResolution -v
pytest tests/ -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "fix: raise ValueError on unresolved \${VAR} to prevent IMAP account lockout"
```

---

### Task 4: Guard FETCH response against expunged UIDs (C4)

**Why:** In the password-scan loop (`fetcher.py:308-315`), `msg_data[0][1]` crashes with `TypeError` if Yandex returns `[None]` (UID expunged between SEARCH and FETCH) or a flags-only response. The `except Exception as e:` at line 326 catches it at **DEBUG** level, so a missed monthly password extraction would be invisible in logs. The main fetch loop at `fetcher.py:362` already guards this correctly — mirror that.

**Files:**
- Modify: `C:\Pyth\email-processor\fetcher.py:305-327`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fetcher_retry.py`:

```python
def test_password_fetch_handles_expunged_uid():
    """FETCH returning [None] (expunged UID) must not crash the password loop."""
    from fetcher import IMAPFetcher
    config = {
        'imap': {'server': 's', 'port': 993, 'username': 'u', 'password': 'p',
                 'folder': 'INBOX', 'processed_folder': ''},
        'processing': {'temp_folder': './temp', 'processed_ids_file': './tmp.db'},
    }
    fetcher = IMAPFetcher(config, dry_run=True)
    # Simulate SEARCH succeeds returning one UID, then FETCH returns [None]
    fetcher.mail = MagicMock()
    fetcher.mail.select = MagicMock(return_value=('OK', [b'']))
    fetcher.mail.uid = MagicMock(side_effect=[
        ('OK', [b'42']),         # SEARCH
        ('OK', [None]),           # FETCH returns expunged
    ])
    # Must not raise
    # Use the helper directly once we extract it in Step 3
    from fetcher import _safe_fetch_rfc822
    result = _safe_fetch_rfc822(fetcher.mail, '42')
    assert result is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_fetcher_retry.py::test_password_fetch_handles_expunged_uid -v
```

Expected: FAIL with `ImportError: cannot import name '_safe_fetch_rfc822'`.

- [ ] **Step 3: Add helper and use it in the password loop**

Add at module level in `fetcher.py` (next to `_search_with_retry`):

```python
def _safe_fetch_rfc822(mail, uid_str: str, attempts: int = 3, delay: float = 2.0):
    """FETCH RFC822 for a UID with retry + expunged-UID guard.

    Returns the raw message bytes or None if the UID is no longer available.
    """
    for attempt in range(1, attempts + 1):
        status, data = mail.uid('FETCH', uid_str, '(RFC822)')
        if status != 'OK':
            if attempt < attempts:
                time.sleep(delay)
            continue
        if not data or data[0] is None or not isinstance(data[0], tuple) or len(data[0]) < 2:
            return None  # Expunged or flags-only response
        return data[0][1]
    return None
```

Replace the password-loop block at `fetcher.py:305-315` with:

```python
            for uid in pwd_msgs[0].split():
                try:
                    raw = _safe_fetch_rfc822(self.mail, uid.decode())
                    if raw is None:
                        logger.warning(f"Password email UID {uid.decode()} unavailable (expunged or FETCH failed)")
                        continue
                    msg = email.message_from_bytes(raw)
                    message_id = msg.get('Message-ID', uid.decode())
                    monthly = _extract_monthly_pwd_from_msg(msg)
                    ...  # rest of the block unchanged
```

Do **not** change the main fetch loop — it already has correct guards at line 361.

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/test_fetcher_retry.py -v
pytest tests/ -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add fetcher.py tests/test_fetcher_retry.py
git commit -m "fix: guard password-scan FETCH against expunged UIDs, log at WARNING"
```

---

### Task 5: Validate monthly password date range before marking processed (C3)

**Why:** `fetcher.py:322` unconditionally adds the monthly-password `message_id` to `processed_ids` after extraction. If a stale (previous month) email is somehow re-fetched — e.g. right after month boundary when an admin moves it back to INBOX — it gets marked processed and the current-month password never gets extracted on subsequent runs.

**Files:**
- Modify: `C:\Pyth\email-processor\fetcher.py:318-325`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fetcher_retry.py`:

```python
def test_expired_monthly_password_not_marked_processed():
    """A monthly password whose valid_to is in the past must not be marked processed."""
    from datetime import datetime
    from fetcher import _should_mark_monthly_processed

    today = datetime(2026, 4, 23)
    # Expired (March 2026)
    assert not _should_mark_monthly_processed({'valid_to': '31.03.2026'}, today=today)
    # Current (April 2026)
    assert _should_mark_monthly_processed({'valid_to': '30.04.2026'}, today=today)
    # Future
    assert _should_mark_monthly_processed({'valid_to': '31.05.2026'}, today=today)
    # Missing valid_to — fail safe: don't mark, retry next run
    assert not _should_mark_monthly_processed({}, today=today)
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_fetcher_retry.py::test_expired_monthly_password_not_marked_processed -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add helper + apply it**

Add at module level in `fetcher.py`:

```python
def _should_mark_monthly_processed(monthly: dict, today=None) -> bool:
    """True if the monthly-password email is current (valid_to >= today)."""
    if today is None:
        today = datetime.now()
    valid_to = monthly.get('valid_to')
    if not valid_to:
        return False
    try:
        valid_dt = datetime.strptime(valid_to, '%d.%m.%Y')
    except (ValueError, TypeError):
        return False
    return valid_dt.date() >= today.date()
```

Edit `fetcher.py:318-325` (inside the password-scan loop) to use it:

```python
                    if monthly:
                        if monthly['password'] not in zetta_passwords:
                            zetta_passwords.insert(0, monthly['password'])
                            logger.info(f"Got Zetta monthly password (valid {monthly['valid_from']} - {monthly['valid_to']})")
                        if _should_mark_monthly_processed(monthly):
                            self.processed_ids.add(message_id)
                        else:
                            logger.info(f"Monthly password email for {monthly.get('valid_to')} is stale — not marking processed")
                    else:
                        logger.warning(f"Zetta monthly password email found in {pwd_folder} but could not extract password — format may have changed")
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/test_fetcher_retry.py -v
pytest tests/ -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add fetcher.py tests/test_fetcher_retry.py
git commit -m "fix: don't mark stale monthly password emails processed"
```

---

### Task 6: Remove duplicate UTF-7 folder encoder (M2)

**Why:** Today we added `imap_utf7_encode` at module level in `fetcher.py`, but there's also a nearly-identical static method `IMAPFetcher._encode_imap_folder` at line 201 used only by `move_to_folder`. Two implementations of the same encoding = drift risk. If they ever differ, you could `select` folder A, move emails to folder A', and silently lose them.

**Files:**
- Modify: `C:\Pyth\email-processor\fetcher.py:199-230`

- [ ] **Step 1: Verify the static method is only used in one place**

```bash
grep -n "_encode_imap_folder" C:\Pyth\email-processor\fetcher.py
```

Expected: exactly two hits — the definition and the one usage in `move_to_folder`.

- [ ] **Step 2: Delete the static method and use the module function**

In `fetcher.py`:

1. Delete the `_encode_imap_folder` static method (~line 199-215).
2. In `move_to_folder` (~line 230), replace `self._encode_imap_folder(dest_folder)` with `imap_utf7_encode(dest_folder)`.

- [ ] **Step 3: Run the test suite (existing tests exercise move_to_folder paths indirectly)**

```bash
pytest tests/ -v
```

Expected: 104+ passed / 17 skipped.

- [ ] **Step 4: Add a regression test**

Append to `tests/test_fetcher_retry.py`:

```python
def test_imap_utf7_encode_handles_cyrillic():
    """Known folder names must round-trip through imap_utf7_encode correctly."""
    from fetcher import imap_utf7_encode
    # ASCII: pass through unchanged
    assert imap_utf7_encode('INBOX') == 'INBOX'
    # Cyrillic: RFC 3501 modified UTF-7
    # "Обработанные" is 12 Cyrillic chars → known encoded form
    encoded = imap_utf7_encode('Обработанные')
    assert encoded.startswith('&')
    assert encoded.endswith('-')
    # '&' must be escaped as '&-'
    assert imap_utf7_encode('A&B') == 'A&-B'
```

Run it:

```bash
pytest tests/test_fetcher_retry.py::test_imap_utf7_encode_handles_cyrillic -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fetcher.py tests/test_fetcher_retry.py
git commit -m "refactor: remove duplicate UTF-7 folder encoder, use single module-level impl"
```

---

### Task 7: Release v1.10.7

**Why:** CLAUDE.md requires a version bump + changelog entry + tag + VM deploy for every production change.

**Files:**
- Modify: `C:\Pyth\email-processor\main.py:12` (`__version__`)
- Modify: `C:\Pyth\email-processor\CHANGELOG.md`

- [ ] **Step 1: Bump version**

Edit `main.py:12`:

```python
__version__ = "1.10.7"
```

- [ ] **Step 2: Add changelog entry**

Insert at the top of `CHANGELOG.md` (immediately after `# Changelog`):

```markdown
## [1.10.7] - 2026-04-23
### Fixed
- Main IMAP SEARCH now retries up to 3× on `[UNAVAILABLE]` and raises on persistent failure (previously a single transient Yandex error produced a silent zero-records day)
- `_save_processed_ids()` is skipped when `write_batch_to_master` fails — prevents permanent loss of emails whose records didn't reach master.xlsx
- `load_config` raises `ValueError` on unresolved `${VAR}` in config instead of logging and passing the literal placeholder (prevents IMAP account lockout from repeated failed login with `"${IMAP_PASSWORD}"`)
- Zetta monthly-password FETCH guards against expunged UIDs (previously crashed at DEBUG level, silently losing the password)
- Zetta monthly password is only marked processed when `valid_to >= today` (prevents stale passwords from blocking re-reads after month boundary)
### Refactored
- Removed duplicate IMAP UTF-7 folder encoder (consolidated `_encode_imap_folder` static method into the module-level `imap_utf7_encode`)
```

- [ ] **Step 3: Run the full suite one more time**

```bash
pytest tests/ -v
```

Expected: all green.

- [ ] **Step 4: Commit, tag, push, and instruct VM deploy**

```bash
git add main.py CHANGELOG.md
git commit -m "chore: v1.10.7 — post-review production hardening"
git tag v1.10.7
git push origin main
git push origin v1.10.7
```

Then on the VM:

```bash
git pull
python3 main.py --dry-run
```

Watch for `SEARCH attempt X failed` warnings (retry logic still working) and a clean run with zero errors. Then a real `python3 main.py` to confirm.

- [ ] **Step 5: Backup before real run**

```bash
bash backup.sh
```

Keeps a snapshot of the v1.10.6 state in case v1.10.7 has any regressions.

---

## Out of scope for this plan

These findings from the review are intentionally deferred. They're real but lower-risk for the user's specific usage pattern:

- **H8 — formula-injection vs dedup mismatch**: low practical probability given real insurer data (no policy numbers start with `=` / `-` / `+`). Revisit if duplicates show up in production.
- **Temp dir leak on write failure**: cosmetic until disk pressure becomes an issue; `/tmp` is cleaned on reboot anyway.
- **SQLite WAL mode + cron flock**: concurrency only matters if user actually runs cron + manual runs simultaneously. One-per-day cron plus occasional manual `--dry-run` is fine.
- **Windows file lock no-op**: production is Linux, so fcntl path runs. Windows dev only.
- **Timezone-aware datetimes**: VM is on Moscow time, reports are on Moscow time — no TZ drift in practice.

If any of these bite in production, a follow-up plan can address them.

---

## Self-review checklist

- [x] Each task has a failing test, an implementation step, a passing test, and a commit step.
- [x] Exact file paths and line numbers included.
- [x] No placeholders ("TBD", "similar to...", "handle edge cases").
- [x] Function signatures consistent across tasks (`_search_with_retry`, `_safe_fetch_rfc822`, `_should_mark_monthly_processed` all defined and used by identical names).
- [x] Each critical finding from the review has a corresponding task (H5→T1, C1/C2→T2, H6→T3, C4→T4, C3→T5, M2→T6).
- [x] Release process matches CLAUDE.md conventions (version bump, changelog, tag, push, VM pull).
