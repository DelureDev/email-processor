"""
Parser for RESO-Garantiya format.
Structure: header row at ~row 8 with columns:
  №п/п | ФИО | Дата рождения | Пол | Адрес | № полиса | Начало обслуживания | Открепление с | Программа | Страхователь
"""
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse RESO format xlsx and return list of normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Find header row (contains "ФИО" and "№ полиса")
    header_row = None
    for i in range(min(20, len(df))):
        row_values = [str(v).strip() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values).lower()
        if 'фио' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"RESO: Could not find header row in {filepath}")
        return []

    # Map column indices
    headers = {}
    for col_idx in range(len(df.columns)):
        val = df.iloc[header_row, col_idx]
        if pd.notna(val):
            headers[str(val).strip().lower().replace('\n', ' ')] = col_idx

    # Find column indices by partial match
    def find_col(*keywords):
        for key, idx in headers.items():
            if all(kw in key for kw in keywords):
                return idx
        return None

    col_fio = find_col('фио')
    col_birth = find_col('дата', 'рожд')
    col_polis = find_col('полис')
    col_otkr = find_col('откреплен') or find_col('оконч', 'обслуж') or find_col('окончан')
    col_start = find_col('начало', 'обслуж')
    col_strahovatel = find_col('страхователь')

    # Parse data rows (after header, until empty row or footer)
    for i in range(header_row + 1, len(df)):
        fio = df.iloc[i, col_fio] if col_fio is not None else None

        if pd.isna(fio) or str(fio).strip() == '':
            continue

        fio = str(fio).strip()

        # Skip if it looks like a footer / signature
        if any(w in fio.lower() for w in ['исполнител', 'директор', 'подпись', 'от  имени']):
            break

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': _format_date(df.iloc[i, col_start]) if col_start is not None else None,
            'Конец обслуживания': _format_date(df.iloc[i, col_otkr]) if col_otkr is not None else None,
            'Страховая компания': 'РЕСО-Гарантия',
            'Страхователь': str(df.iloc[i, col_strahovatel]).strip() if col_strahovatel is not None and pd.notna(df.iloc[i, col_strahovatel]) else None,
        }
        results.append(record)

    logger.info(f"RESO: parsed {len(results)} records from {filepath}")
    return results


def _format_date(val) -> str | None:
    if pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.strftime('%d.%m.%Y')
    s = str(val).strip()
    # Try common date formats
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(s, fmt).strftime('%d.%m.%Y')
        except ValueError:
            continue
    return s
