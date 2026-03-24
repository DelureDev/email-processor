# Error Visibility & Pipeline Resilience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every pipeline failure is visible in the email report — no more silent deaths or log-only errors.

**Architecture:** Wrap all crash-prone operations in try/except with `stats['errors'].append(...)`, add regression tests for the Zetta password fix, and surface Zetta zip extraction failures in the email report. All changes are in existing files — no new modules needed.

**Tech Stack:** Python 3, pytest, openpyxl, imaplib

---

## File Map

| File | Changes |
|------|---------|
| `main.py` | Wrap `write_batch_to_master` in try/except (both modes), propagate `_attach_monthly_if_last_day` errors to stats, read `fetcher.failed_zips` |
| `fetcher.py` | Track failed zip filenames in `self.failed_zips` |
| `tests/test_zetta_handler.py` | Add regression test for password with `%?{}` chars |
| `tests/test_pipeline_resilience.py` | Tests for write failure handling, monthly attachment error propagation |
| `CHANGELOG.md` | v1.9.11 entry |
| `CLAUDE.md` | Version bump |

---

### Task 1: Regression test for Zetta password with special characters

**Files:**
- Modify: `tests/test_zetta_handler.py:38-53` (TestExtractMonthlyPassword class)

- [ ] **Step 1: Write the tests**

Add to `TestExtractMonthlyPassword` class in `tests/test_zetta_handler.py`:

```python
def test_special_chars_in_password(self):
    """Regression test for v1.9.9 — passwords with %?{} were rejected."""
    body = """Уважаемые партнеры!
    Направляем пароль, действующий по электронным спискам
    в период с 01.03.2026 по 31.03.2026 .

    3RpNk%?}*t

    Коммерческая тайна.
    Настоящее сообщение конфиденциально."""
    result = extract_monthly_password(body)
    assert result is not None
    assert result['password'] == '3RpNk%?}*t'
    assert result['valid_from'] == '01.03.2026'

def test_html_bold_password_with_special_chars(self):
    """Regression: actual Zetta email format with <b> tag and special chars."""
    body = (
        '<html><body>'
        'Уважаемые партнеры!<br>'
        'Направляем пароль, действующий по электронным спискам, '
        'полученным от ООО &quot;Зетта Страхование жизни&quot; '
        'в период с 01.03.2026 по 31.03.2026 .<br>'
        '<br>'
        '<b>3RpNk%?}*t</b><br>'
        '<br>'
        '<font size="2">Коммерческая тайна.<br>'
        'Настоящее сообщение конфиденциально.</font>'
        '</body></html>'
    )
    result = extract_monthly_password(body)
    assert result is not None
    assert result['password'] == '3RpNk%?}*t'
```

- [ ] **Step 2: Run tests to verify they pass** (these test the already-fixed regex)

Run: `pytest tests/test_zetta_handler.py::TestExtractMonthlyPassword -v`
Expected: All PASS (including 2 new tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_zetta_handler.py
git commit -m "test: add regression tests for Zetta password with special chars"
```

---

### Task 2: Wrap `write_batch_to_master` in try/except (Critical fix)

This is the most important fix. If `write_batch_to_master` raises, the entire pipeline crashes — no email, no healthcheck, no visibility.

**Key safety invariant:** On write failure in IMAP mode, emails MUST stay in INBOX for re-fetch. This means we must also clear `processed_imap_ids` (prevents moving to Обработанные) AND clear `stats['new_records']` (prevents email report showing records that were never actually saved).

**Files:**
- Modify: `main.py:514-517` (run_imap_mode)
- Modify: `main.py:570-571` (run_local_mode)
- Create: `tests/test_pipeline_resilience.py`

- [ ] **Step 1: Write the test**

Create `tests/test_pipeline_resilience.py`:

```python
"""Tests for pipeline resilience — write failures, monthly errors."""
import pytest
from unittest.mock import patch, MagicMock
from main import make_stats


class TestWriteBatchFailure:
    """Pipeline must survive write_batch_to_master failure."""

    @patch('main.send_report')
    @patch('main.write_batch_to_master', side_effect=RuntimeError("Disk full"))
    @patch('main.load_existing_keys', return_value=set())
    @patch('main.IMAPFetcher')
    def test_imap_mode_survives_write_failure(self, mock_fetcher_cls, mock_keys, mock_write, mock_report):
        """run_imap_mode should catch write failure, add to errors, not move emails."""
        from main import run_imap_mode

        # Simulate fetcher returning one attachment so pending is populated
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_attachments.return_value = [{
            'filepath': '/tmp/fake.xlsx',
            'filename': 'fake.xlsx',
            'sender': 'test@test.com',
            'subject': 'Test',
            'date': '2026-03-24',
            'message_id': '<test@test>',
            'imap_id': '123',
            '_extract_dir': None,
        }]
        mock_fetcher.failed_zips = []
        mock_fetcher_cls.return_value = mock_fetcher

        config = {
            'imap': {'server': 'x', 'username': 'x', 'password': 'x'},
            'output': {'master_file': '/tmp/test_master.xlsx'},
            'processing': {'deduplicate': True},
        }

        # Patch process_file to populate pending without actually parsing
        with patch('main.process_file') as mock_pf:
            def fake_process(fp, mp, cfg, stats, **kw):
                if kw.get('pending') is not None:
                    kw['pending'].append(([{'test': 'record'}], 'fake.xlsx'))
                stats['total_records'] += 1
                stats['new_records'].append({'test': 'record'})
            mock_pf.side_effect = fake_process

            stats = run_imap_mode(config, dry_run=False)

        # Should have error in stats, not crash
        assert any('Disk full' in e for e in stats['errors'])
        # Should NOT have moved emails (move_to_folder should not be called)
        mock_fetcher.move_to_folder.assert_not_called()
        # new_records should be cleared since write failed
        assert stats['new_records'] == []

    @patch('main.send_report')
    @patch('main.write_batch_to_master', side_effect=RuntimeError("Corrupted xlsx"))
    @patch('main.load_existing_keys', return_value=set())
    def test_local_mode_survives_write_failure(self, mock_keys, mock_write, mock_report):
        """run_local_mode should catch write failure, add to errors, continue."""
        import tempfile, os
        from main import run_local_mode

        with tempfile.TemporaryDirectory() as td:
            # Create a dummy xlsx so process_file finds something
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(['ФИО', 'Дата рождения'])
            wb.save(os.path.join(td, 'test.xlsx'))

            config = {
                'output': {'master_file': os.path.join(td, 'master.xlsx')},
                'processing': {'deduplicate': False},
            }

            with patch('main.process_file') as mock_pf:
                def fake_process(fp, mp, cfg, stats, **kw):
                    if kw.get('pending') is not None:
                        kw['pending'].append(([{'test': 'record'}], 'test.xlsx'))
                    stats['total_records'] += 1
                mock_pf.side_effect = fake_process

                stats = run_local_mode(td, config, dry_run=False)

            assert any('Corrupted xlsx' in e for e in stats['errors'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_resilience.py::TestWriteBatchFailure::test_imap_mode_survives_write_failure -v`
Expected: FAIL (RuntimeError propagates uncaught)

- [ ] **Step 3: Implement the fix in `run_imap_mode`**

In `main.py`, replace lines 514-517:

```python
    # Write batch BEFORE marking emails as processed — if write fails,
    # emails stay in inbox and will be re-fetched on next run (no data loss).
    if pending and not dry_run:
        write_batch_to_master(pending, master_path)
```

With:

```python
    # Write batch BEFORE marking emails as processed — if write fails,
    # emails stay in inbox and will be re-fetched on next run (no data loss).
    if pending and not dry_run:
        try:
            write_batch_to_master(pending, master_path)
        except Exception as e:
            logger.error(f"Failed to write batch to master: {e}", exc_info=True)
            stats['errors'].append(f"Master write failed: {e}")
            pending.clear()              # Signal: nothing was written
            processed_imap_ids.clear()   # Don't move emails — re-fetch next run
            stats['new_records'].clear() # Don't report records that weren't saved
            stats['total_records'] = 0
```

- [ ] **Step 4: Implement the same fix in `run_local_mode`**

In `main.py`, replace lines 570-571:

```python
    if pending and not dry_run:
        write_batch_to_master(pending, master_path)
```

With:

```python
    if pending and not dry_run:
        try:
            write_batch_to_master(pending, master_path)
        except Exception as e:
            logger.error(f"Failed to write batch to master: {e}", exc_info=True)
            stats['errors'].append(f"Master write failed: {e}")
            stats['new_records'].clear()
            stats['total_records'] = 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_pipeline_resilience.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: 88+ passed (no regressions)

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_pipeline_resilience.py
git commit -m "fix: wrap write_batch_to_master in try/except — pipeline survives write failure"
```

---

### Task 3: Propagate `_attach_monthly_if_last_day` errors to stats

**Files:**
- Modify: `main.py:326-327`
- Modify: `tests/test_pipeline_resilience.py`

- [ ] **Step 1: Write the test**

Add to `tests/test_pipeline_resilience.py`:

```python
class TestMonthlyAttachmentFailure:
    def test_monthly_error_in_stats(self):
        """_attach_monthly_if_last_day should add error to stats, not just log."""
        from main import _attach_monthly_if_last_day, make_stats
        import calendar
        from datetime import datetime
        from unittest.mock import patch

        stats = make_stats()
        config = {'output': {'master_file': '/tmp/nonexistent_master_test.xlsx'}}

        today = datetime.now()
        last_day = calendar.monthrange(today.year, today.month)[1]

        # Force "last day of month" and force pd.read_excel to raise
        with patch('main.datetime') as mock_dt, \
             patch('main.os.path.exists', return_value=True), \
             patch('main.pd.read_excel', side_effect=Exception("Corrupted master")):
            mock_dt.now.return_value = today.replace(day=last_day)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            _attach_monthly_if_last_day(config, stats)

        assert any('monthly' in e.lower() or 'Corrupted' in e for e in stats['errors'])
```

Note: `main.py` uses `from datetime import datetime` at the top level, so `main.datetime` won't intercept the class — BUT `_attach_monthly_if_last_day` calls `datetime.now()` directly. We need to check how `datetime` is imported in `main.py` and patch accordingly.

Actually, since `main.py` does `from datetime import datetime`, the function uses the local name `datetime`. Patching `main.datetime` will work because it replaces the module-level name binding.

However, a simpler approach: just create a fake master file that causes `pd.read_excel` to fail naturally:

```python
class TestMonthlyAttachmentFailure:
    def test_monthly_error_in_stats(self):
        """_attach_monthly_if_last_day should add error to stats, not just log."""
        import tempfile, os
        from main import _attach_monthly_if_last_day, make_stats

        stats = make_stats()

        # Create a corrupt "xlsx" file
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            f.write(b'not a real xlsx')
            corrupt_path = f.name

        try:
            config = {'output': {'master_file': corrupt_path}}
            # Force last day of month so the function actually runs
            import calendar
            from datetime import datetime
            today = datetime.now()
            last_day = calendar.monthrange(today.year, today.month)[1]

            from unittest.mock import patch
            with patch('main.datetime') as mock_dt:
                mock_dt.now.return_value = today.replace(day=last_day)
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                _attach_monthly_if_last_day(config, stats)

            assert any('monthly' in e.lower() or 'Failed' in e for e in stats['errors'])
        finally:
            os.unlink(corrupt_path)
```

- [ ] **Step 2: Run test — verify it fails** (error logged but not in stats)

Run: `pytest tests/test_pipeline_resilience.py::TestMonthlyAttachmentFailure -v`
Expected: FAIL

- [ ] **Step 3: Implement the fix**

In `main.py`, replace line 327:

```python
        logging.getLogger(__name__).error(f"Failed to build monthly records: {e}")
```

With:

```python
        logging.getLogger(__name__).error(f"Failed to build monthly records: {e}")
        stats['errors'].append(f"Monthly report build failed: {e}")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_pipeline_resilience.py -v && pytest tests/ -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_pipeline_resilience.py
git commit -m "fix: propagate _attach_monthly_if_last_day errors to stats"
```

---

### Task 4: Surface Zetta zip extraction failures in email report

Currently `fetcher.py` logs "All passwords failed" but never tells `main.py`. We track failed filenames and expose them.

**Files:**
- Modify: `fetcher.py` (track failed zips in `self.failed_zips`)
- Modify: `main.py` (read `fetcher.failed_zips` after fetch)

- [ ] **Step 1: Initialize `failed_zips` in `__init__`**

In `fetcher.py`'s `IMAPFetcher.__init__`, add after other instance vars:

```python
        self.failed_zips = []
```

- [ ] **Step 2: Track failed zips in `fetch_attachments`**

In `fetcher.py`, after line 241 (`zetta_passwords = []`), add:

```python
        failed_zips = []            # filenames of zips where all passwords failed
```

At lines 449-450, replace:

```python
                else:
                    logger.warning(f"Failed to extract zip {info['filename']} — will retry next run")
```

With:

```python
                else:
                    logger.warning(f"Failed to extract zip {info['filename']} — will retry next run")
                    failed_zips.append(info['filename'])
```

At line 456-457, update the no-password case:

```python
        elif zetta_zips and not zetta_passwords:
            logger.warning(f"Found {len(zetta_zips)} Zetta zips but no passwords!")
            failed_zips.extend(info['filename'] for _, info in zetta_zips)
```

Before `return results` (line 460), store on self:

```python
        self.failed_zips = failed_zips
```

- [ ] **Step 3: Read failed zips in `run_imap_mode`**

In `main.py`, after the fetch/parse try/except block (after line 512), before the write section, add:

```python
    # Surface Zetta zip failures in email report
    if fetcher.failed_zips:
        for name in fetcher.failed_zips:
            stats['errors'].append(f"Zetta zip not extracted: {name}")
```

Note: use "not extracted" rather than "wrong password?" since the no-password case is also covered.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add fetcher.py main.py
git commit -m "fix: surface Zetta zip extraction failures in email report"
```

---

### Task 5: Version bump, changelog, final verification

**Files:**
- Modify: `main.py:12` (__version__)
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Bump version to 1.9.11**

In `main.py`, change `__version__ = "1.9.10"` to `__version__ = "1.9.11"`.

- [ ] **Step 2: Add CHANGELOG entry**

```markdown
## [1.9.11] - 2026-03-24
### Fixed
- **Critical: `write_batch_to_master` crash no longer kills pipeline** — wrapped in try/except in both IMAP and local modes. On failure: error in email report, healthcheck pings /fail, emails stay in INBOX for re-fetch, stats cleared to avoid phantom record counts.
- **`_attach_monthly_if_last_day` errors now in email report** — was only logging, same pattern as v1.9.10 CSV fix.
- **Zetta zip extraction failures now in email report** — "All passwords failed" and "no passwords found" were only in VM logs, now surfaced via `stats['errors']`.
- **Regression tests for Zetta password with `%?{}` characters** — the exact scenario from v1.9.9 now has test coverage (plaintext and HTML bold format).
```

- [ ] **Step 3: Update CLAUDE.md version**

Change `Current version: **v1.9.10**.` to `Current version: **v1.9.11**.`

- [ ] **Step 4: Run full test suite one final time**

Run: `pytest tests/ -v`
Expected: 92+ passed, 16 skipped

- [ ] **Step 5: Commit, tag, push**

```bash
git add main.py CHANGELOG.md CLAUDE.md
git commit -m "fix: v1.9.11 — pipeline resilience: no more silent failures"
git tag v1.9.11
git push origin main
git push origin v1.9.11
```
