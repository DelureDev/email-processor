# Zetta Password Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the Zetta monthly password locally so that 29 out of 30 days the pipeline skips the IMAP SEARCH entirely, making Zetta ZIP extraction immune to Yandex's intermittent `[UNAVAILABLE]` rejections of the `FROM "parollpu@zettains.ru"` filter.

**Architecture:** New small module `zetta_password_cache.py` handling JSON load/save of `{password, valid_from, valid_to}` to `./zetta_password.json` (gitignored, mode 0600). `fetcher.fetch_attachments()` loads cache at start, skips the IMAP pre-scan when a non-expired cached password exists, and writes the cache after any successful IMAP-driven extraction. Existing per-email password flow (Zetta pulse + Sber) is untouched — cached password is only the *monthly* fallback.

**Tech Stack:** Python 3.12, JSON, pytest, existing imaplib/email pipeline.

---

## Pre-flight

- Working directory: `C:\Pyth\email-processor` (main branch)
- Clean baseline: `git status` shows only untracked plan files and unrelated `.claude/` noise; `python -m pytest tests/ -v` shows 112 passed / 17 skipped on v1.10.7.

If tests don't pass, STOP — something has regressed and must be fixed before starting.

---

## Task 1: Cache module + unit tests

**Why:** A standalone module with no runtime dependency on IMAP is easy to unit-test and easy to reason about. Isolating load/save here keeps `fetcher.py` focused on its actual job (IMAP). The module is small on purpose — <60 lines.

**Files:**
- Create: `C:\Pyth\email-processor\zetta_password_cache.py`
- Create: `C:\Pyth\email-processor\tests\test_zetta_password_cache.py`

### Step 1: Write the failing tests

Create `C:\Pyth\email-processor\tests\test_zetta_password_cache.py`:

```python
"""Unit tests for zetta_password_cache."""
import json
from datetime import datetime
import pytest


class TestLoad:
    def test_missing_file_returns_none(self, tmp_path):
        from zetta_password_cache import load
        assert load(str(tmp_path / 'nope.json')) is None

    def test_malformed_json_returns_none(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text('{ not valid json', encoding='utf-8')
        assert load(str(p)) is None

    def test_missing_required_keys_returns_none(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text(json.dumps({'password': 'x'}), encoding='utf-8')  # no valid_to
        assert load(str(p)) is None

    def test_expired_cache_returns_none(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text(json.dumps({
            'password': 'abc', 'valid_from': '01.03.2026', 'valid_to': '31.03.2026',
        }), encoding='utf-8')
        today = datetime(2026, 4, 23)
        assert load(str(p), today=today) is None

    def test_current_cache_returns_dict(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text(json.dumps({
            'password': 'abc', 'valid_from': '01.04.2026', 'valid_to': '30.04.2026',
        }), encoding='utf-8')
        today = datetime(2026, 4, 23)
        result = load(str(p), today=today)
        assert result == {'password': 'abc', 'valid_from': '01.04.2026', 'valid_to': '30.04.2026'}

    def test_boundary_valid_to_equals_today_is_still_valid(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text(json.dumps({
            'password': 'abc', 'valid_from': '01.04.2026', 'valid_to': '30.04.2026',
        }), encoding='utf-8')
        today = datetime(2026, 4, 30)  # last day
        assert load(str(p), today=today) is not None


class TestSave:
    def test_save_creates_file(self, tmp_path):
        from zetta_password_cache import save
        p = str(tmp_path / 'cache.json')
        save(p, 'secret', '01.04.2026', '30.04.2026')
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        assert data == {'password': 'secret', 'valid_from': '01.04.2026', 'valid_to': '30.04.2026'}

    def test_save_overwrites_existing(self, tmp_path):
        from zetta_password_cache import save
        p = str(tmp_path / 'cache.json')
        save(p, 'old', '01.03.2026', '31.03.2026')
        save(p, 'new', '01.04.2026', '30.04.2026')
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        assert data['password'] == 'new'
        assert data['valid_to'] == '30.04.2026'

    def test_roundtrip_through_load(self, tmp_path):
        from zetta_password_cache import save, load
        p = str(tmp_path / 'cache.json')
        save(p, 'mypwd', '01.04.2026', '30.04.2026')
        today = datetime(2026, 4, 15)
        result = load(p, today=today)
        assert result['password'] == 'mypwd'
```

### Step 2: Run tests to verify they fail

```bash
python -m pytest tests/test_zetta_password_cache.py -v
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'zetta_password_cache'`.

### Step 3: Implement `zetta_password_cache.py`

Create `C:\Pyth\email-processor\zetta_password_cache.py`:

```python
"""Persistent cache for the Zetta monthly password.

Zetta sends ONE password valid for the entire month. Caching it locally means
the pipeline doesn't have to re-read it from IMAP every run, which makes
Zetta ZIP extraction immune to transient Yandex SEARCH failures.

Format: {"password": str, "valid_from": "DD.MM.YYYY", "valid_to": "DD.MM.YYYY"}
File is gitignored and written with mode 0600.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ('password', 'valid_from', 'valid_to')


def load(path: str, today: datetime | None = None) -> dict | None:
    """Load cached password. Returns None if missing, malformed, or expired.

    Fail-safe: on any parse error, returns None so the caller falls back to
    whatever upstream discovery mechanism it has (IMAP SEARCH).
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Zetta password cache at {path} is unreadable: {e}")
        return None
    if not all(k in data for k in _REQUIRED_KEYS):
        logger.warning(f"Zetta password cache at {path} missing required keys")
        return None
    if today is None:
        today = datetime.now()
    try:
        valid_dt = datetime.strptime(data['valid_to'], '%d.%m.%Y')
    except (ValueError, TypeError):
        logger.warning(f"Zetta password cache at {path} has invalid valid_to")
        return None
    if valid_dt.date() < today.date():
        logger.info(f"Zetta password cache at {path} expired ({data['valid_to']}), ignoring")
        return None
    return data


def save(path: str, password: str, valid_from: str, valid_to: str) -> None:
    """Write the cache with mode 0600 so only the owner can read it."""
    data = {'password': password, 'valid_from': valid_from, 'valid_to': valid_to}
    # Write to a tmp file then rename, so a crash mid-write doesn't corrupt cache
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows and some filesystems ignore chmod — not critical for correctness
        pass
    logger.info(f"Zetta password cache updated (valid {valid_from} - {valid_to})")
```

### Step 4: Run tests to verify they pass

```bash
python -m pytest tests/test_zetta_password_cache.py -v
python -m pytest tests/ -v
```

Expected: all 9 new tests pass; full suite 121 passed / 17 skipped.

### Step 5: Commit

```bash
git add zetta_password_cache.py tests/test_zetta_password_cache.py
git commit -m "feat: add zetta_password_cache module for persisting monthly password"
```

(Post-commit hook auto-pushes.)

---

## Task 2: Wire cache into `fetcher.fetch_attachments`

**Why:** Make the pipeline use the cache. Load at start of `fetch_attachments`. If cache is valid, skip the IMAP pre-scan entirely (that's the whole point — bypass Yandex's flaky FROM-filtered SEARCH). After any successful IMAP pre-scan that yields a password, write the cache so next run skips IMAP.

**Files:**
- Modify: `C:\Pyth\email-processor\fetcher.py`
- Modify: `C:\Pyth\email-processor\tests\test_fetcher_retry.py` (add integration test)

### Step 1: Write the failing integration test

Append to `C:\Pyth\email-processor\tests\test_fetcher_retry.py`:

```python
class TestPasswordCacheSkipsImapScan:
    """When a valid password cache exists, the IMAP pre-scan must NOT run."""

    def test_valid_cache_skips_imap_prescan(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        import zetta_password_cache
        from fetcher import IMAPFetcher

        # Write a valid cache file
        cache_path = tmp_path / 'zetta_password.json'
        zetta_password_cache.save(str(cache_path), 'cached-pw', '01.04.2026', '30.04.2026')

        config = {
            'imap': {'server': 's', 'port': 993, 'username': 'u', 'password': 'p',
                     'folder': 'INBOX', 'processed_folder': 'Processed',
                     'zetta_password_cache': str(cache_path)},
            'processing': {'temp_folder': str(tmp_path), 'processed_ids_file': str(tmp_path / 'ids.db')},
        }
        fetcher = IMAPFetcher(config, dry_run=True)

        # Mock IMAP so we can assert what's called
        fetcher.mail = MagicMock()
        fetcher.mail.select = MagicMock(return_value=('OK', [b'0']))
        # Main SEARCH returns empty — we only care about whether password SEARCH ran
        fetcher.mail.uid = MagicMock(return_value=('OK', [b'']))

        # Patch today via zetta_password_cache's datetime
        from datetime import datetime as real_dt
        class FixedDatetime(real_dt):
            @classmethod
            def now(cls):
                return real_dt(2026, 4, 23)
        monkeypatch.setattr('zetta_password_cache.datetime', FixedDatetime)
        monkeypatch.setattr('fetcher.datetime', FixedDatetime)

        fetcher.fetch_attachments(days_back=3)

        # Assert: no SEARCH call with FROM parollpu@zettains.ru
        search_criteria = [c.args[2] for c in fetcher.mail.uid.call_args_list
                           if len(c.args) >= 3 and c.args[0] == 'SEARCH']
        for crit in search_criteria:
            assert 'parollpu@zettains.ru' not in crit, \
                f"IMAP pre-scan still ran despite valid cache; criteria was: {crit}"

    def test_imap_scan_saves_password_to_cache(self, tmp_path, monkeypatch):
        """After the IMAP pre-scan finds a password, it must be written to cache."""
        from unittest.mock import MagicMock
        import zetta_password_cache
        from fetcher import IMAPFetcher

        cache_path = tmp_path / 'zetta_password.json'
        # No cache initially
        assert not cache_path.exists()

        config = {
            'imap': {'server': 's', 'port': 993, 'username': 'u', 'password': 'p',
                     'folder': 'INBOX', 'processed_folder': '',
                     'zetta_password_cache': str(cache_path)},
            'processing': {'temp_folder': str(tmp_path), 'processed_ids_file': str(tmp_path / 'ids.db')},
        }
        fetcher = IMAPFetcher(config, dry_run=True)
        fetcher.mail = MagicMock()
        fetcher.mail.select = MagicMock(return_value=('OK', [b'0']))

        # Fake IMAP responses: SEARCH finds one UID, FETCH returns a body we can
        # parse as monthly password email. We patch _extract_monthly_pwd_from_msg
        # to return a deterministic dict rather than constructing a real email.
        fetcher.mail.uid = MagicMock(side_effect=[
            ('OK', [b'42']),  # password SEARCH returns UID 42
            ('OK', [(b'header', b'dummy-rfc822-bytes')]),  # FETCH
            ('OK', [b'']),  # main SEARCH returns nothing
        ])
        monkeypatch.setattr('fetcher._extract_monthly_pwd_from_msg',
                            lambda msg: {'password': 'freshly-found-pw',
                                         'valid_from': '01.04.2026',
                                         'valid_to': '30.04.2026'})
        monkeypatch.setattr('fetcher.email.message_from_bytes',
                            lambda raw: MagicMock(get=lambda k, d=None: '<msg-id>'))

        fetcher.fetch_attachments(days_back=3)

        # Assert cache file now exists and contains the discovered password
        assert cache_path.exists()
        loaded = zetta_password_cache.load(str(cache_path))
        assert loaded is not None
        assert loaded['password'] == 'freshly-found-pw'
```

### Step 2: Run tests to verify they fail

```bash
python -m pytest tests/test_fetcher_retry.py::TestPasswordCacheSkipsImapScan -v
```

Expected: both tests FAIL — the pre-scan still runs regardless of cache (currently there's no cache loading at all).

### Step 3: Wire the cache into `fetcher.py`

Changes in `fetcher.py`:

**3a.** Add import at top of module (with the other local imports):

```python
import zetta_password_cache
```

**3b.** In `IMAPFetcher.__init__`, add a line to stash the cache path from config. Place it immediately after the `self.processed_folder = ...` line:

```python
        self.zetta_password_cache_path = config['imap'].get(
            'zetta_password_cache', './zetta_password.json')
```

**3c.** In `fetch_attachments`, locate the pre-scan block that currently looks like:

```python
        # Pre-scan: search for Zetta monthly password (go back 35 days to catch 1st-of-month email)
        # Searches both INBOX and processed_folder — email may have been moved by a prior run
        pwd_since = _imap_date(datetime.now() - timedelta(days=35))
        pwd_search_folders = [self.folder]
        if self.processed_folder and self.processed_folder != self.folder:
            pwd_search_folders.append(self.processed_folder)

        for pwd_folder in pwd_search_folders:
            ...
```

Insert a cache-loading step **before** the folder loop (between the folder list build and the `for pwd_folder` loop):

```python
        # Try cached monthly password first — avoids a Yandex SEARCH roundtrip
        # which can be flaky for FROM-filtered queries.
        cached = zetta_password_cache.load(self.zetta_password_cache_path)
        if cached:
            zetta_passwords.insert(0, cached['password'])
            logger.info(f"Using cached Zetta monthly password (valid {cached['valid_from']} - {cached['valid_to']})")
```

Then wrap the existing `for pwd_folder in pwd_search_folders:` loop so it only runs if no cached password was loaded:

```python
        if not zetta_passwords:
            for pwd_folder in pwd_search_folders:
                ...  # existing body unchanged
```

**3d.** When the IMAP pre-scan successfully extracts a monthly password, also write it to the cache. Find the block inside the pre-scan loop that looks like:

```python
                    if monthly:
                        if monthly['password'] not in zetta_passwords:
                            zetta_passwords.insert(0, monthly['password'])
                            logger.info(f"Got Zetta monthly password (valid {monthly['valid_from']} - {monthly['valid_to']})")
                        if _should_mark_monthly_processed(monthly):
                            self.processed_ids.add(message_id)
                        else:
                            logger.info(f"Monthly password email for {monthly.get('valid_to')} is stale — not marking processed")
```

Change it to also save the cache on success:

```python
                    if monthly:
                        if monthly['password'] not in zetta_passwords:
                            zetta_passwords.insert(0, monthly['password'])
                            logger.info(f"Got Zetta monthly password (valid {monthly['valid_from']} - {monthly['valid_to']})")
                        if _should_mark_monthly_processed(monthly):
                            self.processed_ids.add(message_id)
                            try:
                                zetta_password_cache.save(
                                    self.zetta_password_cache_path,
                                    monthly['password'],
                                    monthly['valid_from'],
                                    monthly['valid_to'])
                            except OSError as e:
                                logger.warning(f"Could not write Zetta password cache: {e}")
                        else:
                            logger.info(f"Monthly password email for {monthly.get('valid_to')} is stale — not marking processed")
```

**Important:** we only write cache when `_should_mark_monthly_processed(monthly)` returns True — so we never cache a stale password.

### Step 4: Run all tests

```bash
python -m pytest tests/ -v
```

Expected: all 121 existing + 2 new integration tests pass → 123 passed / 17 skipped.

### Step 5: Update `.gitignore`

Append to `C:\Pyth\email-processor\.gitignore` under the "Project runtime files" section (before the `tmp.db*` line added in v1.10.7 is also fine):

```
zetta_password.json
```

### Step 6: Commit

```bash
git add fetcher.py tests/test_fetcher_retry.py .gitignore
git commit -m "feat: use persistent Zetta password cache to skip IMAP pre-scan when valid"
```

---

## Task 3: Release v1.10.8

**Files:**
- Modify: `C:\Pyth\email-processor\main.py` (line 12)
- Modify: `C:\Pyth\email-processor\CHANGELOG.md`

### Step 1: Bump version

Edit `main.py:12`:

```python
__version__ = "1.10.8"
```

### Step 2: Add changelog entry

Insert at top of `CHANGELOG.md`, immediately after the `# Changelog` line:

```markdown
## [1.10.8] - 2026-04-23
### Added
- Zetta monthly password now cached to `./zetta_password.json` (gitignored, mode 0600) on successful extraction. On subsequent runs the pipeline loads the cache and skips the IMAP pre-scan entirely, making Zetta ZIP extraction immune to Yandex's intermittent `[UNAVAILABLE]` rejections of the `FROM "parollpu@zettains.ru"` filter. Cache expires automatically when `valid_to < today`.
- New config key `imap.zetta_password_cache` (default: `./zetta_password.json`) to customize cache location.
```

### Step 3: Full suite one last time

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: 123 passed / 17 skipped.

### Step 4: Commit, tag, push tag

```bash
git add main.py CHANGELOG.md
git commit -m "chore: v1.10.8 — Zetta password cache"
git tag v1.10.8
git push origin v1.10.8
```

(Main branch auto-pushes via post-commit hook. Tags must be pushed explicitly.)

### Step 5: VM deploy + smoke test

On the VM:

```
bash backup.sh && git pull && python3 main.py --dry-run
```

First run after deploy will use the existing IMAP flow to find the password (cache file doesn't exist yet) and will write the cache as a side effect. Look for:

```
Got Zetta monthly password (valid 01.04.2026 - 30.04.2026)
Zetta password cache updated (valid 01.04.2026 - 30.04.2026)
```

Then run again immediately to verify the cache is used:

```
python3 main.py --dry-run
```

Look for:

```
Using cached Zetta monthly password (valid 01.04.2026 - 30.04.2026)
```

And confirm NO `Found N Zetta monthly password email(s) in INBOX` line — that would mean IMAP was still hit.

---

## Out of scope for this plan

- **Cache invalidation when password stops working.** If Zetta unexpectedly rotates the password mid-month, the cached one will fail to unlock zips. Per-email passwords (from the main fetch loop) are the fallback today, and if they also fail the `failed_zips` list surfaces the error in the email report. Manual fix: delete `./zetta_password.json` on the VM, re-run. Could be automated later by invalidating the cache after N consecutive zip-extraction failures.
- **Encryption at rest.** The cache file stores the password in plaintext, mode 0600. This matches how `config.yaml` stores IMAP/SMTP credentials today. If/when you move to a secrets manager, the cache should go through it too.
- **Sharing cache across hosts.** The cache is local to the VM. If you run the pipeline on multiple hosts they'd each do one IMAP hit per month — acceptable.

---

## Self-review checklist

- [x] Every task has failing test → implement → passing test → single commit.
- [x] No placeholders (TBD, similar to, handle edge cases).
- [x] `zetta_password_cache.load`/`save` signatures are identical in Task 1 (definition) and Task 2 (usage).
- [x] Cache path config key `imap.zetta_password_cache` used consistently.
- [x] Each requirement has a task: cache module (T1), wiring + skip logic + save-on-success (T2), release (T3).
- [x] Release process matches CLAUDE.md conventions.
- [x] Gitignore entry added so cache isn't committed.
- [x] Mode 0600 on save; Windows fallback noted.
- [x] Atomic write (tmp + rename) so a crash mid-write doesn't corrupt the cache.
