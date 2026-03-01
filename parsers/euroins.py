"""
Parser for ООО РСО ЕВРОИНС format.
Structure:
  Row ~9: "Прикрепление с DD.MM.YYYY по DD.MM.YYYY" (dates for all records)
  Row ~12: Header: № п/п | Номер полиса | Ф.И.О | Дата рождения | Адрес | Телефон | Вид обслуживания
  ФИО already combined. No Страхователь column.
"""
import pandas as pd
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Euroins format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Extract dates from header rows ("Прикрепление с ... по ..." or "Открепление с ...")
    start_date = None
    end_date = None

    for i in range(min(15, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if 'прикрепление' in val_str.lower() or 'открепление' in val_str.lower():
                dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', val_str)
                if len(dates) >= 2:
                    start_date = dates[0]
                    end_date = dates[1]
                elif len(dates) == 1:
                    start_date = dates[0]

    # Find header row
    header_row = None
    for i in range(min(20, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if ('ф.и.о' in row_text or 'фио' in row_text) and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"EUROINS: Could not find header row in {filepath}")
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

    col_fio = find_col('ф.и.о') or find_col('фио')
    col_birth = find_col('дата', 'рожд')
    col_polis = find_col('полис')

    for i in range(header_row + 1, len(df)):
        fio = df.iloc[i, col_fio] if col_fio is not None else None
        if pd.isna(fio) or str(fio).strip() == '':
            continue
        fio = str(fio).strip()
        if any(w in fio.lower() for w in ['рамках', 'программ', 'руководител', 'исполнител', '*']):
            break

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'Евроинс',
            'Страхователь': None,
        }
        results.append(record)

    logger.info(f"EUROINS: parsed {len(results)} records from {filepath}")
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
