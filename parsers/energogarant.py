"""
Parser for Энергогарант format.
Structure (letter-style):
  Row 4: "Московский филиал ПАО "САК "ЭНЕРГОГАРАНТ""
  Row 13-14: Free text describing the request
  Row 17: Header — № | ФИО | Пол | Дата рождения | Наименование программы | № Полисов | Дата прикрепления | Дата открепления | ... | Место работы
  Row 18+: Data rows (ФИО in single column)
"""
import pandas as pd
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Энергогарант format and return normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    # Find header row (contains "ФИО" and "Полис")
    header_row = None
    for i in range(min(25, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фио' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"ENERGOGARANT: Could not find header row in {filepath}")
        return []

    # Map column indices
    headers = {}
    for col_idx in range(len(df.columns)):
        val = df.iloc[header_row, col_idx]
        if pd.notna(val):
            key = str(val).strip().lower().replace('\n', ' ')
            headers[key] = col_idx

    def find_col(*keywords):
        for key, idx in headers.items():
            if all(kw in key for kw in keywords):
                return idx
        return None

    col_fio = find_col('фио')
    col_birth = find_col('дата', 'рожд')
    col_polis = find_col('полис')
    col_prikr = find_col('дата', 'прикрепл')
    col_otkr = find_col('дата', 'откреплен')
    col_work = find_col('место', 'работ') or find_col('страхователь')

    if col_fio is None:
        logger.error(f"ENERGOGARANT: Could not find 'ФИО' column in {filepath}")
        return []

    # Extract strahovatel from "Место работы" column or from letter text
    strahovatel = None

    # Parse data rows
    for i in range(header_row + 1, len(df)):
        fio = df.iloc[i, col_fio] if col_fio is not None else None

        if pd.isna(fio) or str(fio).strip() == '':
            continue

        fio_str = str(fio).strip()

        # Skip footer rows
        if any(w in fio_str.lower() for w in ['итого', 'всего', 'с уважением', 'директор', 'начальник']):
            break

        fio_upper = fio_str.upper()

        # Dates
        start_date = _format_date(df.iloc[i, col_prikr]) if col_prikr is not None else None
        end_date = _format_date(df.iloc[i, col_otkr]) if col_otkr is not None else None

        # Policy
        polis = None
        if col_polis is not None and pd.notna(df.iloc[i, col_polis]):
            polis = str(df.iloc[i, col_polis]).strip()

        # Strahovatel from row
        if col_work is not None and pd.notna(df.iloc[i, col_work]):
            strahovatel = str(df.iloc[i, col_work]).strip()

        record = {
            'ФИО': fio_upper,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': polis,
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'Энергогарант',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"ENERGOGARANT: parsed {len(results)} records from {filepath}")
    return results


def _format_date(val) -> str | None:
    if pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.strftime('%d.%m.%Y')
    s = str(val).strip()
    if not s:
        return None
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(s, fmt).strftime('%d.%m.%Y')
        except ValueError:
            continue
    return s
