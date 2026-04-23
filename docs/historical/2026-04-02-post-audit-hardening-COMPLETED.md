# Post-Audit Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all Critical and High issues from the 2026-04-02 audit, plus selected Medium/Low quick wins, without changing any pipeline behavior.

**Architecture:** Incremental fixes to existing files — no new modules. Each task is independent and can be deployed separately. All fixes are backward-compatible with the existing master.xlsx layout and config.yaml structure.

**Tech Stack:** Python 3.11+, openpyxl, pandas, smtplib, logging.handlers

---

## Files Modified

| File | Tasks |
|---|---|
| `notifier.py` | Task 1 (filter empty recipients) |
| `config.yaml` | Task 2 (add processed_folder + healthcheck_url) |
| `main.py` | Task 3 (log rotation), Task 4 (LibreOffice check), Task 5 (healthcheck in stats) |
| `writer.py` | Task 6 (newline in _safe) |
| `parsers/utils.py` | Task 7 (format_date fallback) |
| `parsers/generic_parser.py` | Task 8 (unknown SC label) |
| `tests/test_clinic_matcher.py` | Task 9 (detachment detection tests) |

---

## Task 1: Filter empty recipients in notifier.py (fixes C2)

**Files:**
- Modify: `notifier.py:52-55`
- Test: `tests/test_notifier.py`

**Context:** Production `config.yaml` has `""` as one recipient. `send_report()` passes this raw list to `_send()` → SMTP. Either the send fails or delivers to an invalid address. Fix: strip falsy entries before use.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_notifier.py — add to existing test class or create new
from unittest.mock import patch, MagicMock

def test_send_report_filters_empty_recipients(tmp_path):
    """Empty string recipients must be filtered out before SMTP send."""
    config = {
        'smtp': {
            'enabled': True,
            'host': 'localhost',
            'port': 587,
            'username': 'test@test.com',
            'password': 'pass',
            'from': 'test@test.com',
            'recipients': ['real@test.com', '', '   '],
            'only_if_new_records': False,
        }
    }
    stats = {
        'total_records': 1, 'files_processed': 1, 'files_skipped': 0,
        'by_company': {}, 'errors': [], 'unknown_files': [],
        'unmatched_clinics': [], 'missing_comments': [], 'skipped_files': [],
        'new_records': [], 'master_path': str(tmp_path / 'master.xlsx'),
    }
    with patch('notifier._send') as mock_send:
        from notifier import send_report
        send_report(config, stats)
        call_args = mock_send.call_args
        recipients_used = call_args[0][1]  # second positional arg is recipients
        assert '' not in recipients_used
        assert '   ' not in recipients_used
        assert 'real@test.com' in recipients_used
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_notifier.py::test_send_report_filters_empty_recipients -v
```
Expected: FAIL — empty string is currently passed through.

- [ ] **Step 3: Fix notifier.py**

In `notifier.py`, change line 52:
```python
# Before
recipients = smtp_cfg.get('recipients', [])

# After
recipients = [r for r in smtp_cfg.get('recipients', []) if r and str(r).strip()]
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/test_notifier.py::test_send_report_filters_empty_recipients -v
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add notifier.py tests/test_notifier.py
git commit -m "fix: filter empty/blank recipients before SMTP send"
```

---

## Task 2: Add missing production config keys (fixes H3, H4)

**Files:**
- Modify: `config.yaml`

**Context:** `processed_folder` is absent → emails never move out of INBOX. `healthcheck_url` is empty → no alerting on cron failure. Both features exist in code and are tested; config just needs the values.

- [ ] **Step 1: Add `processed_folder` to config.yaml**

Find the `imap:` section and add `processed_folder`:
```yaml
imap:
  # ... existing keys ...
  processed_folder: "Обработанные"
```

- [ ] **Step 2: Configure healthcheck_url**

If you have an uptime monitoring service (UptimeRobot, Healthchecks.io, etc.), add the ping URL:
```yaml
healthcheck_url: "https://hc-ping.com/YOUR-UUID-HERE"
```
If not yet set up, create a free monitor at https://healthchecks.io, get the ping URL, and add it. If not ready, leave as `""` — the code handles empty URL gracefully (skips ping). Return to this when ready.

- [ ] **Step 3: Verify config loads without error**

```bash
python -c "
import yaml, os
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
print('processed_folder:', cfg.get('imap', {}).get('processed_folder'))
print('healthcheck_url:', cfg.get('healthcheck_url', '(not set)'))
"
```
Expected: prints `Обработанные` and your healthcheck URL (or empty string).

- [ ] **Step 4: Commit**

```bash
git add config.yaml
git commit -m "config: add processed_folder and healthcheck_url to production config"
```

---

## Task 3: Rotate log files (fixes M1)

**Files:**
- Modify: `main.py:35-58` (`setup_logging`)

**Context:** `logging.FileHandler` grows forever. Switch to `RotatingFileHandler` — caps `processor.log` and `audit.log` at 10 MB × 5 backups = 50 MB max each.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_main.py or new tests/test_logging.py
import logging
import os

def test_log_rotation_uses_rotating_handler(tmp_path, monkeypatch):
    """setup_logging must use RotatingFileHandler, not plain FileHandler."""
    monkeypatch.chdir(tmp_path)
    os.makedirs('logs', exist_ok=True)
    config = {'logging': {'file': 'logs/processor.log', 'level': 'INFO'}}

    # Clear any existing handlers
    root = logging.getLogger()
    root.handlers.clear()
    logging.getLogger('audit').handlers.clear()

    from main import setup_logging
    setup_logging(config)

    from logging.handlers import RotatingFileHandler
    handler_types = [type(h) for h in logging.getLogger().handlers]
    assert RotatingFileHandler in handler_types, (
        f"Expected RotatingFileHandler, got: {handler_types}"
    )
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_logging.py::test_log_rotation_uses_rotating_handler -v
```
Expected: FAIL — currently uses plain `FileHandler`.

- [ ] **Step 3: Update setup_logging in main.py**

```python
# Add to imports at top of main.py (after existing logging import):
from logging.handlers import RotatingFileHandler

# Replace setup_logging function (lines 35-58):
def setup_logging(config: dict) -> None:
    log_file = config.get('logging', {}).get('file', './logs/processor.log')
    log_level = config.get('logging', {}).get('level', 'INFO')
    os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            RotatingFileHandler(log_file, encoding='utf-8',
                                maxBytes=10 * 1024 * 1024, backupCount=5),
            logging.StreamHandler(sys.stdout),
        ]
    )

    # Audit logger — separate file for password-handling events
    audit_log_file = config.get('logging', {}).get('audit_file', './logs/audit.log')
    os.makedirs(os.path.dirname(audit_log_file) or '.', exist_ok=True)
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    if not audit_logger.handlers:
        handler = RotatingFileHandler(audit_log_file, encoding='utf-8',
                                      maxBytes=10 * 1024 * 1024, backupCount=5)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        audit_logger.addHandler(handler)
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/test_logging.py::test_log_rotation_uses_rotating_handler -v
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_logging.py
git commit -m "fix: use RotatingFileHandler — cap logs at 50MB total"
```

---

## Task 4: Check LibreOffice return code (fixes H1, L4)

**Files:**
- Modify: `main.py:125-145` (`convert_xls_to_xlsx`)

**Context:** `result = subprocess.run(...)` is assigned but never used (dead code). LibreOffice can exit non-zero and still produce a partial file. Add: check `returncode`, check file size > 0, log the stderr on failure.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_main.py
from unittest.mock import patch, MagicMock
import os

def test_convert_xls_to_xlsx_returns_none_on_nonzero_exit(tmp_path):
    """convert_xls_to_xlsx must return None if LibreOffice exits non-zero."""
    fake_xls = tmp_path / 'test.xls'
    fake_xls.write_bytes(b'fake')
    fake_xlsx = tmp_path / 'test.xlsx'
    fake_xlsx.write_bytes(b'partial output')  # file exists but exit was non-zero

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = b'LibreOffice error'

    with patch('subprocess.run', return_value=mock_result):
        from main import convert_xls_to_xlsx
        result = convert_xls_to_xlsx(str(fake_xls))
    assert result is None

def test_convert_xls_to_xlsx_returns_none_on_zero_byte_output(tmp_path):
    """convert_xls_to_xlsx must return None if output file is zero bytes."""
    fake_xls = tmp_path / 'test.xls'
    fake_xls.write_bytes(b'fake')
    fake_xlsx = tmp_path / 'test.xlsx'
    fake_xlsx.write_bytes(b'')  # zero byte file

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = b''

    with patch('subprocess.run', return_value=mock_result):
        from main import convert_xls_to_xlsx
        result = convert_xls_to_xlsx(str(fake_xls))
    assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_main.py::test_convert_xls_to_xlsx_returns_none_on_nonzero_exit tests/test_main.py::test_convert_xls_to_xlsx_returns_none_on_zero_byte_output -v
```
Expected: FAIL

- [ ] **Step 3: Fix convert_xls_to_xlsx in main.py**

```python
def convert_xls_to_xlsx(filepath: str) -> str | None:
    """Convert .xls to .xlsx using LibreOffice. Returns new path or None on failure."""
    logger = logging.getLogger(__name__)
    if not filepath.lower().endswith('.xls'):
        return filepath

    outdir = os.path.dirname(filepath) or '.'
    try:
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'xlsx', filepath, '--outdir', outdir],
            capture_output=True, timeout=60
        )
        if result.returncode != 0:
            logger.error(f"LibreOffice exited {result.returncode} for {os.path.basename(filepath)}: "
                         f"{result.stderr.decode(errors='replace')[:200]}")
            return None
        xlsx_path = os.path.splitext(filepath)[0] + '.xlsx'
        if os.path.exists(xlsx_path) and os.path.getsize(xlsx_path) > 0:
            logger.info(f"Converted {os.path.basename(filepath)} → .xlsx")
            return xlsx_path
        logger.error(f"LibreOffice produced no output for {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"Failed to convert {filepath}: {e}")

    return None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_main.py::test_convert_xls_to_xlsx_returns_none_on_nonzero_exit tests/test_main.py::test_convert_xls_to_xlsx_returns_none_on_zero_byte_output -v
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "fix: check LibreOffice returncode and output file size in convert_xls_to_xlsx"
```

---

## Task 5: Surface healthcheck failure in email report (fixes L6)

**Files:**
- Modify: `main.py:444-458` (`_ping_healthcheck`)

**Context:** A failed healthcheck ping only goes to `logger.warning`. Once `healthcheck_url` is configured (Task 2), a ping failure means the monitoring service wasn't notified — that should appear in the email report too.

- [ ] **Step 1: Update _ping_healthcheck signature in main.py**

Find `_ping_healthcheck` (around line 444) and update it to accept `stats`:

```python
def _ping_healthcheck(config: dict, success: bool = True, body: bytes = None, stats: dict = None) -> None:
    url = config.get('healthcheck_url', '').strip()
    if not url:
        return
    if not success:
        url = url.rstrip('/') + '/fail'
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=body, method='POST'),
            timeout=10,
        )
        logger.debug(f"Healthcheck pinged: {url}")
    except Exception as e:
        msg = f"Healthcheck ping failed: {e}"
        logger.warning(msg)
        if stats is not None:
            stats['errors'].append(msg)
```

- [ ] **Step 2: Update all call sites**

Search for `_ping_healthcheck(` in `main.py` and pass `stats=stats` to every call:
```bash
grep -n "_ping_healthcheck" main.py
```
For each call found, add `stats=stats` keyword argument.

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all previously passing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "fix: healthcheck ping failure now surfaces in email report stats"
```

---

## Task 6: Add newline to formula injection guard (fixes M3)

**Files:**
- Modify: `writer.py:166-180` (`_safe`)
- Test: `tests/test_writer.py`

**Context:** `_safe()` guards against `=`, `+`, `@`, `\t`, `\r`, `|` but not `\n`. Completing the set.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_writer.py — add to existing _safe tests
def test_safe_prefixes_newline():
    from writer import _safe
    assert _safe('\nINJECT') == "'\nINJECT"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_writer.py::test_safe_prefixes_newline -v
```
Expected: FAIL

- [ ] **Step 3: Fix _safe in writer.py**

```python
# Change line 176 from:
if c in ('=', '+', '@', '\t', '\r', '|'):
# To:
if c in ('=', '+', '@', '\t', '\r', '\n', '|'):
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/test_writer.py::test_safe_prefixes_newline -v
```

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add writer.py tests/test_writer.py
git commit -m "fix: add newline to formula injection guard in _safe()"
```

---

## Task 7: Improve format_date fallback (fixes L2)

**Files:**
- Modify: `parsers/utils.py:18-26` (`format_date`)
- Test: `tests/test_utils.py`

**Context:** Unrecognized date strings are returned as-is, which pollutes dedup keys. Add two more common formats that insurance files use: `DD-MM-YYYY` and `YYYY.MM.DD`. These cover most observed edge cases without changing the return-as-is fallback for truly unknown formats.

- [ ] **Step 1: Write the failing tests**

```python
# In tests/test_utils.py — add to existing format_date tests
def test_format_date_dash_separated():
    from parsers.utils import format_date
    assert format_date('01-03-2026') == '01.03.2026'

def test_format_date_dot_year_first():
    from parsers.utils import format_date
    assert format_date('2026.03.01') == '01.03.2026'
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_utils.py::test_format_date_dash_separated tests/test_utils.py::test_format_date_dot_year_first -v
```
Expected: FAIL

- [ ] **Step 3: Add formats to format_date in parsers/utils.py**

```python
# Change the formats list (line 20) from:
for fmt in ['%Y-%m-%d %H:%M:%S', '%d.%m.%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
# To:
for fmt in ['%Y-%m-%d %H:%M:%S', '%d.%m.%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y.%m.%d']:
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_utils.py::test_format_date_dash_separated tests/test_utils.py::test_format_date_dot_year_first -v
```

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add parsers/utils.py tests/test_utils.py
git commit -m "fix: add DD-MM-YYYY and YYYY.MM.DD to format_date recognized formats"
```

---

## Task 8: Improve generic parser unknown company label (fixes L5)

**Files:**
- Modify: `parsers/generic_parser.py`
- Test: `tests/test_parsers.py`

**Context:** Generic parser returns `'Неизвестная СК'` which makes it impossible to trace which insurer sent the file from the email report's "По страховым компаниям" breakdown. Replace with `'Неизвестна (generic)'` — same meaning, clearly signals it was a fallback detection.

- [ ] **Step 1: Find the line**

```bash
grep -n "Неизвестная СК" parsers/generic_parser.py
```

- [ ] **Step 2: Write the failing test**

```python
# In tests/test_parsers.py or tests/test_generic_parser.py
def test_generic_parser_unknown_sc_label(tmp_path):
    """Generic parser must use 'Неизвестна (generic)' not 'Неизвестная СК'."""
    # Create a minimal xlsx with FIO column only (no insurance company column)
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['ФИО', 'Дата рождения', '№ полиса', 'Начало', 'Конец'])
    ws.append(['Иванов Иван Иванович', '01.01.1980', 'П-001', '01.01.2026', '31.12.2026'])
    path = tmp_path / 'generic_test.xlsx'
    wb.save(path)

    from parsers.generic_parser import parse
    records = parse(str(path))
    if records:
        assert records[0].get('Страховая компания') != 'Неизвестная СК'
        assert 'generic' in records[0].get('Страховая компания', '').lower()
```

- [ ] **Step 3: Replace the string in generic_parser.py**

```bash
sed -i "s/'Неизвестная СК'/'Неизвестна (generic)'/g" parsers/generic_parser.py
```
Verify:
```bash
grep -n "Неизвестн" parsers/generic_parser.py
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/ -k "generic" -v --tb=short
```

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add parsers/generic_parser.py tests/
git commit -m "fix: generic parser labels unknown company as 'Неизвестна (generic)' for traceability"
```

---

## Task 9: Add test coverage for detachment detection (fixes M2)

**Files:**
- Test: `tests/test_clinic_matcher.py`

**Context:** The "открепляем / снятия с медицинского" detection in `detect_clinic()` was tightened twice (v1.9.13, v1.9.14) with no tests. A regression here would silently miscategorize attachment files. Cover: PSB откр (empty clinic), PSB прикр (clinic matched), Alfa snyat (empty clinic), normal file (clinic matched).

- [ ] **Step 1: Write tests using existing test files**

```python
# In tests/test_clinic_matcher.py — add to existing test class
import pytest
import os
from clinic_matcher import detect_clinic, reload_clinics

TEST_FILES = os.path.join(os.path.dirname(__file__), '..', 'test_files')

@pytest.fixture(autouse=True)
def reset_clinic_cache():
    reload_clinics()

@pytest.mark.skipif(
    not os.path.exists(os.path.join(TEST_FILES, 'ПСБ_Список_на_откр_от_31_03_2026_(0000244141).xlsx')),
    reason="PSB откр fixture not in test_files/"
)
def test_psb_otkr_returns_empty_clinic():
    """PSB открепление file → empty clinic, no warning."""
    clinic, extract, cid = detect_clinic(
        os.path.join(TEST_FILES, 'ПСБ_Список_на_откр_от_31_03_2026_(0000244141).xlsx')
    )
    assert clinic == ''
    assert extract is False

@pytest.mark.skipif(
    not os.path.exists(os.path.join(TEST_FILES, 'ПСБ_Список_на_прикр_от_27_03_2026_(0000235400).xlsx')),
    reason="PSB прикр fixture not in test_files/"
)
def test_psb_prikr_returns_garibaldi_15():
    """PSB прикрепление file with 'Детская стоматология № 2' → Гарибальди 15."""
    clinic, extract, cid = detect_clinic(
        os.path.join(TEST_FILES, 'ПСБ_Список_на_прикр_от_27_03_2026_(0000235400).xlsx')
    )
    assert clinic == 'Гарибальди 15'
    assert cid == '000000001'

@pytest.mark.skipif(
    not os.path.exists(os.path.join(TEST_FILES, '1826_00345267_24-03-2026-20-19-38_1826фдг_snyat.xlsx')),
    reason="Alfa snyat fixture not in test_files/"
)
def test_alfa_snyat_returns_empty_clinic():
    """Alfa snyat (снятие) file → empty clinic."""
    clinic, extract, cid = detect_clinic(
        os.path.join(TEST_FILES, '1826_00345267_24-03-2026-20-19-38_1826фдг_snyat.xlsx')
    )
    assert clinic == ''
    assert extract is False
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_clinic_matcher.py -v --tb=short
```
Expected: the three new tests PASS (fixtures are in test_files/).

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_clinic_matcher.py
git commit -m "test: add detachment detection regression tests (PSB откр/прикр, Alfa snyat)"
```

---

## Final: Version bump and tag

After all tasks are complete:

- [ ] **Bump version in main.py**

```python
__version__ = "1.10.0"
```

(Minor bump — this is a meaningful hardening release, not just patches.)

- [ ] **Add CHANGELOG entry**

```markdown
## [1.10.0] - 2026-04-02
### Fixed
- Filter empty/blank recipients before SMTP send — prevents delivery failure
- Log rotation: RotatingFileHandler caps processor.log and audit.log at 50MB total
- LibreOffice return code and output file size now checked in convert_xls_to_xlsx
- Healthcheck ping failure now surfaces in email report stats
- Newline character added to formula injection guard in _safe()
- format_date now recognizes DD-MM-YYYY and YYYY.MM.DD formats
- Generic parser labels unknown company as 'Неизвестна (generic)' for traceability
### Changed
- Production config: processed_folder and healthcheck_url now configured
### Tests
- Detachment detection regression tests (PSB откр/прикр, Alfa snyat)
```

- [ ] **Commit, tag, push**

```bash
git add main.py CHANGELOG.md
git commit -m "chore: v1.10.0 — post-audit hardening release"
git tag v1.10.0
git push origin main
git push origin v1.10.0
```

---

## Out of Scope (known, deferred)

These were identified in the audit but intentionally excluded — either too risky to change without a larger refactor, or very low probability:

- **C1 (dedup key pollution on write failure)** — requires architectural change to process_file batch flow. Risk outweighs benefit for now; the failure scenario is already partially handled by clearing pending/stats on write failure.
- **Opt 1-3 (triple xlsx open per file)** — real optimization but requires passing DataFrames between pipeline stages. Separate refactor project.
- **M6 (Zetta `от` filter)** — theoretical risk only; no observed false positives.
- **L1 (hardcoded column 8 in migration)** — only triggers on very old master files; protected by layout check before migration.
- **L3 (CSV lock)** — both files are on the same filesystem in practice.
