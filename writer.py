"""
Writer — appends normalized records to master xlsx file on network drive.
"""
import os
import sys
import shutil
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from contextlib import contextmanager
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@contextmanager
def _master_lock(master_path: str):
    """Exclusive file lock around master.xlsx writes. No-op on Windows (dev only)."""
    if sys.platform == 'win32':
        yield
        return
    import fcntl
    lock_path = master_path + '.lock'
    with open(lock_path, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


COLUMNS = ['ФИО', 'Дата рождения', '№ полиса', 'Начало обслуживания', 'Конец обслуживания', 'Страховая компания', 'Страхователь', 'Источник файла', 'Дата обработки']


def load_existing_keys(master_path: str) -> set:
    """Load dedup keys (ФИО + полис + начало + конец) from existing master file."""
    keys = set()
    if not os.path.exists(master_path):
        return keys
    try:
        dedup_cols = ['ФИО', '№ полиса', 'Начало обслуживания', 'Конец обслуживания']
        df = pd.read_excel(master_path, usecols=dedup_cols)

        def _clean(s):
            s = str(s).strip()
            return '' if s in ('nan', 'None', 'NaT') else s

        for col in dedup_cols:
            df[col] = df[col].map(_clean)
        df['ФИО'] = df['ФИО'].str.upper()

        keys = set(zip(df['ФИО'], df['№ полиса'], df['Начало обслуживания'], df['Конец обслуживания']))
    except Exception as e:
        logger.error(f"Error loading existing keys: {e}")
    return keys

HEADER_FONT = Font(name='Arial', bold=True, size=11, color='FFFFFF')
HEADER_FILL = PatternFill('solid', fgColor='2F5496')
HEADER_ALIGNMENT = Alignment(horizontal='center', vertical='center', wrap_text=True)
DATA_FONT = Font(name='Arial', size=10)
DATA_ALIGNMENT = Alignment(vertical='center')
THIN_BORDER = Border(
    left=Side(style='thin', color='D9D9D9'),
    right=Side(style='thin', color='D9D9D9'),
    top=Side(style='thin', color='D9D9D9'),
    bottom=Side(style='thin', color='D9D9D9'),
)
COLUMN_WIDTHS = {
    'ФИО': 35,
    'Дата рождения': 16,
    '№ полиса': 25,
    'Начало обслуживания': 20,
    'Конец обслуживания': 20,
    'Страховая компания': 25,
    'Страхователь': 25,
    'Источник файла': 30,
    'Дата обработки': 16,
}


def write_to_master(records: list[dict], master_path: str, source_filename: str = ""):
    """Append records to master xlsx file. Creates file if it doesn't exist."""
    write_batch_to_master([(records, source_filename)], master_path)


def write_batch_to_master(batch: list[tuple[list[dict], str]], master_path: str):
    """
    Write multiple batches of records in a single open/save cycle.
    batch: list of (records, source_filename) tuples.
    Opens the workbook once regardless of how many files are in the batch.
    """
    if not batch:
        return

    os.makedirs(os.path.dirname(master_path) or '.', exist_ok=True)

    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    all_records = [
        {**r, 'Источник файла': source_filename, 'Дата обработки': now}
        for records, source_filename in batch
        for r in records
    ]

    with _master_lock(master_path):
        if os.path.exists(master_path):
            bak_path = master_path + '.bak'
            try:
                shutil.copy2(master_path, bak_path)
            except OSError as e:
                logger.warning(f"Could not create backup of master: {e}")
            _append_to_existing(all_records, master_path)
        else:
            _create_new(all_records, master_path)

    logger.info(f"Wrote {len(all_records)} records ({len(batch)} files) to {master_path}")
    _export_csv(master_path)


def _export_csv(master_path: str) -> None:
    """Export master xlsx to a CSV file alongside it (UTF-8 with BOM for Excel compatibility)."""
    csv_path = os.path.splitext(master_path)[0] + '.csv'
    try:
        df = pd.read_excel(master_path)
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        logger.info(f"CSV backup exported: {csv_path}")
    except Exception as e:
        logger.warning(f"CSV backup failed: {e}")


def _create_new(records: list[dict], path: str):
    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"

    # Header
    for col_idx, col_name in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(col_idx)].width = COLUMN_WIDTHS.get(col_name, 20)

    ws.row_dimensions[1].height = 30
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}1"

    # Data
    for row_idx, record in enumerate(records, 2):
        for col_idx, col_name in enumerate(COLUMNS, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=record.get(col_name, ''))
            cell.font = DATA_FONT
            cell.border = THIN_BORDER
            cell.alignment = DATA_ALIGNMENT

    # Freeze header
    ws.freeze_panes = 'A2'

    wb.save(path)


def _append_to_existing(records: list[dict], path: str):
    wb = load_workbook(path)
    if 'Данные' not in wb.sheetnames:
        raise ValueError(f"Sheet 'Данные' not found in {path}. Available sheets: {wb.sheetnames}")
    ws = wb['Данные']

    # Find actual last data row (max_row may include empty styled rows)
    next_row = ws.max_row + 1
    for r in range(ws.max_row, 0, -1):
        if any(ws.cell(row=r, column=c).value is not None for c in range(1, len(COLUMNS) + 1)):
            next_row = r + 1
            break

    for row_idx, record in enumerate(records, next_row):
        for col_idx, col_name in enumerate(COLUMNS, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=record.get(col_name, ''))
            cell.font = DATA_FONT
            cell.border = THIN_BORDER
            cell.alignment = DATA_ALIGNMENT

    # Update autofilter range
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{ws.max_row}"

    wb.save(path)
