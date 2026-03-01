"""
Parser for ООО Абсолют Страхование format.
Structure:
  Row 5: Header: № п/п | ФИО | Дата рождения | Адрес | № полиса | Дата начала действия полиса | Дата окончания действия полиса | Программа | СТРАХОВАТЕЛЬ
  ФИО already combined.
"""
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Absolut Strakhovanie format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    header_row = None
    for i in range(min(15, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фио' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"ABSOLUT: Could not find header row in {filepath}")
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

    col_fio = find_col('фио')
    col_birth = find_col('дата', 'рожд')
    col_polis = find_col('полис')
    col_start = find_col('дата', 'начал')
    col_end = find_col('дата', 'оконч')
    col_strah = find_col('страхователь')

    for i in range(header_row + 1, len(df)):
        fio = df.iloc[i, col_fio] if col_fio is not None else None
        if pd.isna(fio) or str(fio).strip() == '':
            continue
        fio = str(fio).strip()
        if any(w in fio.lower() for w in ['руководител', 'директор', 'подпись', 'исп.']):
            break

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': _format_date(df.iloc[i, col_start]) if col_start is not None else None,
            'Конец обслуживания': _format_date(df.iloc[i, col_end]) if col_end is not None else None,
            'Страховая компания': 'Абсолют Страхование',
            'Страхователь': str(df.iloc[i, col_strah]).strip() if col_strah is not None and pd.notna(df.iloc[i, col_strah]) else None,
        }
        results.append(record)

    logger.info(f"ABSOLUT: parsed {len(results)} records from {filepath}")
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
