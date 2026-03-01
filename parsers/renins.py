"""
Parser for ПАО Группа Ренессанс Страхование format.
Files come as .xls — need xlrd or LibreOffice conversion.
Structure:
  Row ~15: "сотрудников:" + company name (Страхователь)
  Row ~17: "на срок: с DD.MM.YYYY г. по DD.MM.YYYY г."
  Row ~20: Header: № п/п | Фамилия (actually full ФИО) | Дата рождения | Паспорт | Адрес | Телефон | № полиса
  ФИО already combined in "Фамилия" column.
"""
import pandas as pd
import re
import logging
import subprocess
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def _ensure_xlsx(filepath: str) -> str:
    """Convert .xls to .xlsx if needed."""
    if filepath.lower().endswith('.xls'):
        outdir = os.path.dirname(filepath) or '.'
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'xlsx', filepath, '--outdir', outdir],
            capture_output=True, timeout=60
        )
        base = os.path.splitext(filepath)[0]
        xlsx_path = base + '.xlsx'
        if os.path.exists(xlsx_path):
            return xlsx_path
        logger.error(f"RENINS: Failed to convert {filepath}")
        return filepath
    return filepath


def parse(filepath: str) -> list[dict]:
    """Parse Renessans Strakhovanie format."""
    filepath = _ensure_xlsx(filepath)
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Extract metadata from upper rows
    start_date = None
    end_date = None
    strahovatel = None

    for i in range(min(25, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()

            # "сотрудников:" row — next column has company name
            if 'сотрудников' in val_str.lower():
                for k in range(j + 1, min(j + 3, len(df.columns))):
                    nv = df.iloc[i, k]
                    if pd.notna(nv) and str(nv).strip():
                        strahovatel = str(nv).strip()
                        break

            # "на срок: с DD.MM.YYYY г. по DD.MM.YYYY г."
            if 'на срок' in val_str.lower() or ('с ' in val_str and ' по ' in val_str):
                # Check same cell and next columns
                combined = val_str
                for k in range(j + 1, min(j + 3, len(df.columns))):
                    nv = df.iloc[i, k]
                    if pd.notna(nv):
                        combined += ' ' + str(nv).strip()
                dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', combined)
                if len(dates) >= 2:
                    start_date = dates[0]
                    end_date = dates[1]
                elif len(dates) == 1:
                    start_date = dates[0]

    # Find header row
    header_row = None
    for i in range(min(25, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if ('фамилия' in row_text or 'фио' in row_text) and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"RENINS: Could not find header row in {filepath}")
        return []

    headers = {}
    for col_idx in range(len(df.columns)):
        val = df.iloc[header_row, col_idx]
        if pd.notna(val):
            headers[str(val).strip().lower().replace('\n', ' ')] = col_idx

    def find_col(*keywords):
        for key, idx in headers.items():
            if all(kw in key for kw in keywords):
                return idx
        return None

    col_fio = find_col('фамилия') or find_col('фио')
    col_birth = find_col('дата', 'рожд')
    col_polis = find_col('полис')

    for i in range(header_row + 1, len(df)):
        fio = df.iloc[i, col_fio] if col_fio is not None else None
        if pd.isna(fio) or str(fio).strip() == '':
            continue
        fio = str(fio).strip()
        # Skip clinic code rows (short strings like "С532") and footers
        if len(fio) < 5 or any(w in fio.lower() for w in ['руководител', 'исполнител', 'директор']):
            continue
        # Check if it's actually a data row (col 0 should be a number)
        row_num = df.iloc[i, 0]
        if pd.isna(row_num):
            continue
        try:
            int(float(row_num))
        except (ValueError, TypeError):
            continue

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'Ренессанс Страхование',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"RENINS: parsed {len(results)} records from {filepath}")
    return results


def _format_date(val) -> str | None:
    if pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.strftime('%d.%m.%Y')
    s = str(val).strip()
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(s, fmt).strftime('%d.%m.%Y')
        except ValueError:
            continue
    return s
