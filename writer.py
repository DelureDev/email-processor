"""
Writer — appends normalized records to master xlsx file on network drive.
"""
import os
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

COLUMNS = ['ФИО', 'Дата рождения', '№ полиса', 'Начало обслуживания', 'Конец обслуживания', 'Страховая компания', 'Страхователь', 'Источник файла', 'Дата обработки']


def load_existing_keys(master_path: str) -> set:
    """Load dedup keys (ФИО + полис + начало + конец) from existing master file."""
    keys = set()
    if not os.path.exists(master_path):
        return keys
    try:
        df = pd.read_excel(master_path)
        for _, row in df.iterrows():
            def clean(val):
                s = str(val).strip() if val is not None else ''
                return '' if s == 'nan' or s == 'None' or s == 'NaT' else s
            key = (
                clean(row.get('ФИО', '')).upper(),
                clean(row.get('№ полиса', '')),
                clean(row.get('Начало обслуживания', '')),
                clean(row.get('Конец обслуживания', '')),
            )
            keys.add(key)
    except Exception as e:
        logger.error(f"Error loading existing keys: {e}")
    return keys

HEADER_FONT = Font(name='Arial', bold=True, size=11, color='FFFFFF')
HEADER_FILL = PatternFill('solid', fgColor='2F5496')
HEADER_ALIGNMENT = Alignment(horizontal='center', vertical='center', wrap_text=True)
DATA_FONT = Font(name='Arial', size=10)
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
    os.makedirs(os.path.dirname(master_path) or '.', exist_ok=True)

    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    for r in records:
        r['Источник файла'] = source_filename
        r['Дата обработки'] = now

    if os.path.exists(master_path):
        _append_to_existing(records, master_path)
    else:
        _create_new(records, master_path)

    logger.info(f"Wrote {len(records)} records to {master_path}")


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
            cell.alignment = Alignment(vertical='center')

    # Freeze header
    ws.freeze_panes = 'A2'

    wb.save(path)


def _append_to_existing(records: list[dict], path: str):
    wb = load_workbook(path)
    ws = wb['Данные'] if 'Данные' in wb.sheetnames else wb.active

    next_row = ws.max_row + 1

    for row_idx, record in enumerate(records, next_row):
        for col_idx, col_name in enumerate(COLUMNS, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=record.get(col_name, ''))
            cell.font = DATA_FONT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical='center')

    # Update autofilter range
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{ws.max_row}"

    wb.save(path)
