# v1.10.11 — Critical Bug Fixes (C1-C5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 5 independent critical bugs surfaced by the 2026-04-23 multi-agent review, ship as v1.10.11.

**Architecture:** Each bug is a tight, local change (1-5 LOC) in a different module. All fixes follow the same TDD shape: write a failing test, apply the minimal patch, verify the full suite still passes, commit. Bugs are independent — no shared state, no ordering dependencies.

**Tech Stack:** Python 3.11+, pytest, pandas, openpyxl, standard library smtplib.

**Bug Map:**
| Fix | File | Symptom |
|-----|------|---------|
| C1 | `notifier.py:57-62` | SMTP failure swallowed; healthcheck stays green |
| C2 | `writer.py:44-49` | `load_existing_keys` silently returns 4-field keys → mass duplication |
| C3 | `writer.py:166-180` | `_safe` bypassed by `-1+cmd...` prefix → formula injection |
| C4 | `parsers/vsk.py:35,52` | `Страхователь` column written from `Место работы`, not `Холдинг` |
| C5 | `detector.py:57` | Second RESO rule matches `'ресо'` substring → wrong parser |

---

## Task 1: C5 — Remove over-broad RESO content rule

**Rationale:** `('reso', ('ресо',))` is a 4-character substring check. The preceding rule `('ресо-гарантия',)` already matches legitimate RESO files. The loose rule only fires on false positives (unknown insurers with incidental "ресо" text) and silently mis-routes them to the RESO parser.

**Files:**
- Modify: `detector.py:57` (delete one line)
- Test: `tests/test_detector.py` (add one test)

- [ ] **Step 1.1: Write failing test**

Append to `tests/test_detector.py`:

```python
def test_reso_not_matched_on_bare_substring(tmp_path):
    """A file containing 'ресо' but NOT 'ресо-гарантия' must not be routed to RESO."""
    import pandas as pd
    path = tmp_path / "ambiguous.xlsx"
    pd.DataFrame({
        'col1': ['Компания: ООО Ресорс-М'],
        'col2': ['Прочие данные'],
    }).to_excel(path, index=False)
    result = detect_format(str(path))
    assert result != 'reso', f"Expected non-reso, got {result!r}"
```

- [ ] **Step 1.2: Run test — verify it fails**

```bash
pytest tests/test_detector.py::test_reso_not_matched_on_bare_substring -v
```

Expected: FAIL with `assert 'reso' != 'reso'`.

- [ ] **Step 1.3: Apply fix**

In `detector.py`, delete line 57 (the second RESO entry):

```python
# BEFORE (lines 55-57):
CONTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ('reso',        ('ресо-гарантия',)),
    ('reso',        ('ресо',)),

# AFTER:
CONTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ('reso',        ('ресо-гарантия',)),
```

- [ ] **Step 1.4: Run test — verify it passes**

```bash
pytest tests/test_detector.py::test_reso_not_matched_on_bare_substring -v
```

Expected: PASS.

- [ ] **Step 1.5: Run full detector suite**

```bash
pytest tests/test_detector.py -v
```

Expected: All tests PASS (including `test_detect_alfa`, `test_detect_ingos`, etc. — those use fixtures in `test_files/` and will SKIP if fixtures missing; non-fixture tests must pass).

- [ ] **Step 1.6: Commit**

```bash
git add detector.py tests/test_detector.py
git commit -m "fix: remove over-broad RESO content rule (C5)

The bare substring rule ('ресо',) caused false positives for any
insurer whose content mentioned РЕСО anywhere in the first 25 rows
(e.g., 'Ресорс-М' in a memo). The preceding 'ресо-гарантия' rule
covers the legitimate case.

Closes review finding C5 from 2026-04-23 multi-agent review."
```

---

## Task 2: C4 — VSK `Страхователь` must come from `Холдинг`, not `Место работы`

**Rationale:** VSK files have two separate columns: `Место работы` (workplace) and `Холдинг` (holding/policyholder legal entity). The current code maps workplace into the `Страхователь` schema field. The correct policyholder is the holding company. `first_col` already exists in `parsers.utils` for exactly this kind of fallback preference.

**Files:**
- Modify: `parsers/vsk.py:11` (add `first_col` to imports)
- Modify: `parsers/vsk.py:35` (replace `find_col` with `first_col`)
- Test: `tests/test_parsers.py` or new `tests/test_vsk_strahovatel.py`

- [ ] **Step 2.1: Write failing test**

Create `tests/test_vsk_strahovatel.py`:

```python
"""Regression test: VSK Страхователь column must come from Холдинг, not Место работы."""
import pandas as pd
from openpyxl import Workbook
from parsers.vsk import parse


def _write_vsk_xlsx(path, rows):
    """Build a minimal VSK xlsx with both 'Место работы' and 'Холдинг' columns."""
    wb = Workbook()
    ws = wb.active
    headers = [
        '№ п/п', 'ФИО', 'Дата рождения', 'Пол', 'Серия и номер полиса',
        'Адрес', 'Телефон', 'Дата прикрепления', 'Дата открепления',
        'Место работы', 'Холдинг', 'Объём', 'Программа',
    ]
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_vsk_strahovatel_uses_holding(tmp_path):
    path = tmp_path / "vsk.xlsx"
    _write_vsk_xlsx(path, [
        [1, 'ИВАНОВ ИВАН ИВАНОВИЧ', '01.01.1990', 'М', 'POL123',
         'Москва', '+7-000', '01.01.2026', '31.12.2026',
         'Офис на Ленина 1', 'ООО ХолдингАкме', 'Полный', 'Стандарт'],
    ])

    records = parse(str(path))

    assert len(records) == 1
    assert records[0]['Страхователь'] == 'ООО ХолдингАкме', \
        f"Expected Страхователь to come from Холдинг, got {records[0]['Страхователь']!r}"


def test_vsk_strahovatel_falls_back_to_workplace_if_holding_missing(tmp_path):
    """Backwards compat: if a VSK variant lacks Холдинг column, fall back to Место работы."""
    path = tmp_path / "vsk_no_holding.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(['№ п/п', 'ФИО', 'Дата рождения', 'Полис №',
               'Дата открепления', 'Место работы'])
    ws.append([1, 'ПЕТРОВ ПЕТР ПЕТРОВИЧ', '02.02.1985', 'POL456',
               '15.06.2026', 'Завод №5'])
    wb.save(path)

    records = parse(str(path))

    assert len(records) == 1
    assert records[0]['Страхователь'] == 'Завод №5'
```

- [ ] **Step 2.2: Run test — verify first test fails**

```bash
pytest tests/test_vsk_strahovatel.py -v
```

Expected: `test_vsk_strahovatel_uses_holding` FAILS (currently returns 'Офис на Ленина 1'). `test_vsk_strahovatel_falls_back_to_workplace_if_holding_missing` passes today.

- [ ] **Step 2.3: Apply fix**

Edit `parsers/vsk.py` line 11:

```python
# BEFORE:
from parsers.utils import format_date, find_header_row, build_header_map, find_col, get_cell_str

# AFTER:
from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str
```

Edit `parsers/vsk.py` line 35:

```python
# BEFORE:
    col_work = find_col(headers, 'место', 'работ')

# AFTER:
    col_work = first_col(headers, ('холдинг',), ('место', 'работ'))
```

- [ ] **Step 2.4: Run test — verify it passes**

```bash
pytest tests/test_vsk_strahovatel.py -v
```

Expected: both tests PASS.

- [ ] **Step 2.5: Run full parser suite**

```bash
pytest tests/test_parsers.py tests/test_vsk_strahovatel.py -v
```

Expected: all PASS (fixture-dependent tests may SKIP).

- [ ] **Step 2.6: Commit**

```bash
git add parsers/vsk.py tests/test_vsk_strahovatel.py
git commit -m "fix: VSK Страхователь reads from Холдинг column, not Место работы (C4)

VSK format has separate columns 'Место работы' (workplace) and
'Холдинг' (policyholder). The parser previously wrote workplace into
the Страхователь schema field. Now uses first_col(('холдинг',),
('место','работ')) to prefer Холдинг with workplace fallback.

All existing VSK records in master.xlsx have the wrong Страхователь
value; they will be corrected next time the same insured is re-sent.

Closes review finding C4 from 2026-04-23 multi-agent review."
```

---

## Task 3: C3 — `_safe` must escape any non-pure-numeric dash string

**Rationale:** Current check `not s[1].isdigit()` skips escaping for any string starting with `-` followed by a digit. An attacker-controlled field containing `-1+cmd|'/C calc'!A1` passes through raw to both xlsx and CSV. When opened in Excel, it evaluates. The fix: only skip escaping when the entire string is a signed decimal number.

**Files:**
- Modify: `writer.py:166-180` (tighten `_safe`)
- Test: `tests/test_writer.py` (extend existing `TestSafe` class)

- [ ] **Step 3.1: Write failing test**

Append to the `TestSafe` class in `tests/test_writer.py` (around line 127):

```python
    def test_blocks_dash_digit_formula(self):
        """Regression: '-1+cmd' previously bypassed the dash carve-out."""
        assert _safe("-1+cmd|'/C calc'!A1") == "'-1+cmd|'/C calc'!A1"

    def test_blocks_dash_digit_with_at(self):
        assert _safe("-1@SUM(A1:A10)") == "'-1@SUM(A1:A10)"

    def test_blocks_dash_number_with_letters(self):
        assert _safe("-500abc") == "'-500abc"

    def test_preserves_negative_integer(self):
        """Sanity: pure negative integers still pass through unescaped."""
        assert _safe('-12345') == '-12345'

    def test_preserves_negative_decimal(self):
        assert _safe('-3.14159') == '-3.14159'
```

- [ ] **Step 3.2: Run test — verify new tests fail**

```bash
pytest tests/test_writer.py::TestSafe -v
```

Expected: `test_blocks_dash_digit_formula`, `test_blocks_dash_digit_with_at`, `test_blocks_dash_number_with_letters` all FAIL. Existing tests continue to PASS.

- [ ] **Step 3.3: Apply fix**

Edit `writer.py` near line 14 (existing imports area) — add `import re` if not already imported.

Check current imports:

```bash
head -20 writer.py
```

If `import re` is missing, add it alongside the other imports at the top of the file.

Then edit `_safe` at `writer.py:166-180`:

```python
# BEFORE:
def _safe(value) -> object:
    """Prevent formula injection by prefixing formula-like strings with apostrophe.
    Does not prefix negative numbers (e.g. -500 stays as-is).
    """
    if value is None:
        return ''
    s = str(value)
    if not s:
        return value
    c = s[0]
    if c in ('=', '+', '@', '\t', '\r', '\n', '|'):
        return "'" + s
    if c == '-' and (len(s) < 2 or not s[1].isdigit()):
        return "'" + s
    return value

# AFTER:
_SIGNED_NUMBER_RE = re.compile(r'^-?\d+(\.\d+)?$')

def _safe(value) -> object:
    """Prevent formula injection by prefixing formula-like strings with apostrophe.
    Does not prefix pure signed numbers (e.g. -500, -3.14 stay as-is).
    Any other '-' prefix (including '-1+cmd') is escaped.
    """
    if value is None:
        return ''
    s = str(value)
    if not s:
        return value
    c = s[0]
    if c in ('=', '+', '@', '\t', '\r', '\n', '|'):
        return "'" + s
    if c == '-' and not _SIGNED_NUMBER_RE.fullmatch(s):
        return "'" + s
    return value
```

- [ ] **Step 3.4: Run test — verify all `_safe` tests pass**

```bash
pytest tests/test_writer.py::TestSafe -v
pytest tests/test_writer.py::test_safe_prefixes_newline -v
```

Expected: all PASS.

- [ ] **Step 3.5: Run full writer suite**

```bash
pytest tests/test_writer.py -v
```

Expected: all PASS.

- [ ] **Step 3.6: Commit**

```bash
git add writer.py tests/test_writer.py
git commit -m "fix: tighten _safe to block '-1+cmd' formula injection (C3)

The dash carve-out 'not s[1].isdigit()' allowed any string starting
with '-<digit>' through unescaped. A value like -1+cmd|'/C calc'!A1
evaluated as a formula when Excel opened the xlsx/CSV.

Now only pure signed numbers matching /^-?\\d+(\\.\\d+)?$/ pass
through; any other dash-prefixed string is apostrophe-escaped.

Closes review finding C3 from 2026-04-23 multi-agent review."
```

---

## Task 4: C2 — `load_existing_keys` must raise if `Клиника` column is missing

**Rationale:** When master.xlsx lacks the `Клиника` column, the current fallback (`dedup_cols[:-1]`) silently builds 4-field existing keys with empty clinic for all rows. New records from the pipeline have real clinic names → 5-field keys → no dedup overlap → **every historical record re-inserted** on that run. Since CLAUDE.md says the schema has been migrated since v1.9+, no live user should hit this — but a regression or manual edit would cause silent mass duplication. Fail loud instead.

**Files:**
- Modify: `writer.py:44-49` (replace silent fallback with RuntimeError)
- Test: `tests/test_writer.py` (add one test to `TestLoadExistingKeys`)

- [ ] **Step 4.1: Write failing test**

Append to the `TestLoadExistingKeys` class in `tests/test_writer.py`:

```python
    def test_raises_if_klinika_column_missing(self, tmp_path):
        """master.xlsx without Клиника column must raise, not silently mis-dedup."""
        from openpyxl import Workbook
        path = str(tmp_path / "old_schema.xlsx")
        wb = Workbook()
        ws = wb.active
        # Old (pre-v1.9) schema — no Клиника, no Комментарий в полис
        ws.append(['ФИО', 'Дата рождения', '№ полиса', 'Начало обслуживания',
                   'Конец обслуживания', 'Страховая компания', 'Страхователь',
                   'Источник файла', 'Дата обработки'])
        ws.append(['ИВАНОВ И И', '01.01.1990', 'POL-1', '01.01.2026',
                   '31.12.2026', 'ТестСК', 'ООО', 'a.xlsx', '23.04.2026'])
        wb.save(path)

        with pytest.raises(RuntimeError, match=r'(?i)клиника'):
            load_existing_keys(path)
```

- [ ] **Step 4.2: Run test — verify it fails**

```bash
pytest tests/test_writer.py::TestLoadExistingKeys::test_raises_if_klinika_column_missing -v
```

Expected: FAIL — current code returns `set()` of 5-tuples with empty clinic, does not raise.

- [ ] **Step 4.3: Apply fix**

Edit the entire body of `load_existing_keys` (writer.py:38-62). Replace the full function with:

```python
def load_existing_keys(master_path: str) -> set:
    """Load dedup keys (ФИО + полис + начало + конец + клиника) from existing master file."""
    keys = set()
    if not os.path.exists(master_path):
        return keys

    dedup_cols = ['ФИО', '№ полиса', 'Начало обслуживания', 'Конец обслуживания', 'Клиника']

    # Check schema outside the general try/except so the error message is not double-wrapped.
    try:
        header_cols = set(pd.read_excel(master_path, nrows=0).columns)
    except Exception as e:
        logger.error(f"Error reading master headers from {master_path}: {e}")
        raise RuntimeError(f"Cannot read master headers: {e}") from e

    missing = [c for c in dedup_cols if c not in header_cols]
    if missing:
        raise RuntimeError(
            f"Dedup columns missing from {master_path}: {missing}. "
            f"Master file is on an old schema (pre-v1.9 layout had no Клиника column). "
            f"Add the missing column(s) (e.g. via openpyxl insert_cols) or restore "
            f"from backup before re-running — continuing would silently duplicate the "
            f"entire history on the next write."
        )

    try:
        df = pd.read_excel(master_path, usecols=dedup_cols, dtype=str)

        for col in dedup_cols:
            df[col] = df[col].map(lambda v: clean_dedup_val(v))
        df['ФИО'] = df['ФИО'].str.upper().str.replace('Ё', 'Е', regex=False)
        df['Клиника'] = df['Клиника'].str.upper()
        for col in ['Начало обслуживания', 'Конец обслуживания']:
            df[col] = df[col].map(norm_date_pad)

        keys = set(zip(df['ФИО'], df['№ полиса'], df['Начало обслуживания'], df['Конец обслуживания'], df['Клиника']))
    except Exception as e:
        logger.error(f"Error loading existing keys from {master_path}: {e}")
        raise RuntimeError(f"Cannot load dedup keys: {e}") from e
    return keys
```

Changes vs original:
1. `dedup_cols` lifted out of try block.
2. Header read has its own narrow try that re-raises (unchanged behavior).
3. New `missing` check raises a dedicated RuntimeError (not wrapped — the schema error is user-facing).
4. `available` variable removed; always uses `dedup_cols`.
5. `if 'Клиника' not in df.columns: df['Клиника'] = ''` removed — no longer reachable.

- [ ] **Step 4.4: Run test — verify it passes**

```bash
pytest tests/test_writer.py::TestLoadExistingKeys -v
```

Expected: new test PASSES, existing `test_loads_keys` / `test_dedup_works` / `test_empty_on_missing_file` continue to PASS.

- [ ] **Step 4.5: Run full writer suite**

```bash
pytest tests/test_writer.py -v
```

Expected: all PASS.

- [ ] **Step 4.6: Run full test suite**

```bash
pytest tests/ -v
```

Expected: 105+ pass, fixture-dependent tests skip (same as pre-change baseline).

- [ ] **Step 4.7: Commit**

```bash
git add writer.py tests/test_writer.py
git commit -m "fix: load_existing_keys raises when Клиника column missing (C2)

Previous fallback (dedup_cols[:-1]) silently built 4-field existing
keys with empty clinic for historical rows, while new records carried
5-field keys with real clinic names. Same logical record across runs
no longer matched → entire history re-duplicated on that run.

Since the schema has included Клиника since v1.9+, this only triggers
on regression or manual edits. Failing loud prevents silent corruption.

Closes review finding C2 from 2026-04-23 multi-agent review."
```

---

## Task 5: C1 — `send_report` must record SMTP failure in `stats['errors']`

**Rationale:** `send_report` catches every SMTP exception and only calls `logger.error`. `_ping_healthcheck` reads `stats['errors']` to decide between success URL and `/fail`. Result: Yandex down / password expired / TLS failure ⇒ report never delivered, healthcheck stays green, operator has no signal.

**Files:**
- Modify: `notifier.py:57-62` (append to `stats['errors']` in except)
- Test: `tests/test_notifier.py` (add one test)

- [ ] **Step 5.1: Write failing test**

Append to `tests/test_notifier.py`:

```python
def test_smtp_failure_recorded_in_stats_errors(tmp_path):
    """Regression: SMTP exception must populate stats['errors'] so healthcheck flips red."""
    from unittest.mock import patch
    import smtplib
    config = {
        'smtp': {
            'enabled': True,
            'host': 'localhost',
            'port': 587,
            'username': 'test@test.com',
            'password': 'pass',
            'from_address': 'test@test.com',
            'recipients': ['real@test.com'],
            'only_if_new_records': False,
        }
    }
    stats = {
        'total_records': 1, 'files_processed': 1, 'files_skipped': 0,
        'by_company': {}, 'errors': [], 'unknown_files': [],
        'unmatched_clinics': [], 'missing_comments': [], 'skipped_files': [],
        'new_records': [], 'master_path': str(tmp_path / 'master.xlsx'),
    }
    with patch('notifier._send', side_effect=smtplib.SMTPAuthenticationError(535, b'bad creds')):
        send_report(config, stats)

    assert len(stats['errors']) == 1
    assert 'smtp' in stats['errors'][0].lower()
```

- [ ] **Step 5.2: Run test — verify it fails**

```bash
pytest tests/test_notifier.py::test_smtp_failure_recorded_in_stats_errors -v
```

Expected: FAIL — `stats['errors']` is empty after SMTP exception.

- [ ] **Step 5.3: Apply fix**

Edit `notifier.py:57-62`:

```python
# BEFORE:
    try:
        msg = _build_message(smtp_cfg, stats)
        _send(smtp_cfg, recipients, msg)
        logger.info(f"Report sent to {', '.join(recipients)}")
    except Exception as e:
        logger.error(f"Failed to send report: {e}", exc_info=True)

# AFTER:
    try:
        msg = _build_message(smtp_cfg, stats)
        _send(smtp_cfg, recipients, msg)
        logger.info(f"Report sent to {', '.join(recipients)}")
    except Exception as e:
        logger.error(f"Failed to send report: {e}", exc_info=True)
        stats.setdefault('errors', []).append(f"SMTP send failed: {e}")
```

- [ ] **Step 5.4: Run test — verify it passes**

```bash
pytest tests/test_notifier.py::test_smtp_failure_recorded_in_stats_errors -v
```

Expected: PASS.

- [ ] **Step 5.5: Run full notifier + healthcheck suites**

```bash
pytest tests/test_notifier.py tests/test_healthcheck.py -v
```

Expected: all PASS. Verify the healthcheck tests still pass unchanged — they read `stats['errors']` exactly as this fix appends into.

- [ ] **Step 5.6: Commit**

```bash
git add notifier.py tests/test_notifier.py
git commit -m "fix: SMTP send failure now marks stats['errors'] (C1)

send_report previously caught and logged every exception without
populating stats['errors']. _ping_healthcheck reads that list to
decide success vs /fail. Yandex outage / bad password / TLS failure
left operator with a green ping and no delivered report.

Closes review finding C1 from 2026-04-23 multi-agent review."
```

---

## Task 6: Version bump, CHANGELOG, tag, push, deploy

**Files:**
- Modify: `main.py:12` (`__version__`)
- Modify: `CHANGELOG.md` (new v1.10.11 entry)

- [ ] **Step 6.1: Bump version**

Edit `main.py:12`:

```python
# BEFORE:
__version__ = "1.10.10"

# AFTER:
__version__ = "1.10.11"
```

- [ ] **Step 6.2: Add CHANGELOG entry**

Prepend a new entry in `CHANGELOG.md` immediately under the top `# Changelog` heading (or wherever v1.10.10 sits):

```markdown
## [1.10.11] - 2026-04-23
### Fixed
- **C1 — Healthcheck honesty**: `notifier.send_report` now appends `"SMTP send failed: ..."` to `stats['errors']` on any SMTP exception, so `_ping_healthcheck` correctly flips to `/fail`. Previously SMTP failures were logged only, leaving healthcheck green while reports silently stopped.
- **C2 — Mass duplication guard**: `writer.load_existing_keys` now raises `RuntimeError` when master.xlsx lacks the `Клиника` column. Previous silent fallback to 4-field dedup caused every historical row to re-insert on the next write because new records carried 5-field keys. Defensive fix — master files since v1.9 already have the column.
- **C3 — Formula injection**: `writer._safe` tightened — only values matching `^-?\d+(\.\d+)?$` (pure signed numbers) bypass the apostrophe prefix. Previously `-1+cmd|'/C calc'!A1` passed through unescaped because `s[1].isdigit()` was True. Applies to both xlsx and CSV writes.
- **C4 — VSK Страхователь column**: `parsers/vsk.py` now reads `Страхователь` from `Холдинг` (preferred) with fallback to `Место работы`. Previously all VSK records had workplace string in the Страхователь field. Legacy records in master.xlsx remain wrong until the same insured is re-sent.
- **C5 — RESO false positives**: removed the overly broad content rule `('reso', ('ресо',))` from `detector.CONTENT_RULES`. The remaining `('ресо-гарантия',)` rule covers real RESO files; the bare substring was silently mis-routing any file mentioning 'ресо' (e.g. 'Ресорс-М') to the RESO parser.
```

- [ ] **Step 6.3: Commit version bump**

```bash
git add main.py CHANGELOG.md
git commit -m "chore: v1.10.11 — critical bug fixes C1-C5

See CHANGELOG.md for details. All 5 fixes from the 2026-04-23
multi-agent review, each landed as a TDD commit."
```

- [ ] **Step 6.4: Tag**

```bash
git tag v1.10.11
```

- [ ] **Step 6.5: Push to remote**

```bash
git push origin main
git push origin v1.10.11
```

- [ ] **Step 6.6: Deploy to VM**

Remind the user to run on the VM:

```bash
# On VM:
git pull
# Then verify:
python3 main.py --version  # should print 1.10.11
```

No Python script changes required on the VM (tests don't run in prod), just the `git pull`.

---

## Verification checklist

After all tasks complete:

- [ ] `pytest tests/ -v` — all previously passing tests still pass (104+ pass, 16 skip without fixtures)
- [ ] `git log --oneline main..HEAD` (or `git log --oneline -6`) — should show 6 clean commits: 5 fixes + 1 version bump
- [ ] `git tag -l 'v1.10.*'` — includes `v1.10.11`
- [ ] `git show v1.10.11 --stat` — diff is small and local to 5 files
- [ ] VM: `git pull && python3 -c "import main; print(main.__version__)"` prints `1.10.11`

## Out of scope for this PR

The following findings from the review are NOT in this plan. Address separately after v1.10.11 ships:

- **C6-C13** from the critical list (schema-migration writes, network-share locking, zip slip edge cases, password-only-email handling, format_date raw pass-through, detect_by_sender dead-code branch, detachment false positives, find_header_row narrative matching)
- All HIGH findings (H1-H18)

Each of the above requires either broader refactor, test fixtures, or architectural discussion. They are documented in the 2026-04-23 review summary.
