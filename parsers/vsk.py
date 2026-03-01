"""
Parser for САО ВСК format.
Two variations:
  Открепление: № п/п | ФИО | Дата рождения | Полис № | Дата открепления | Место работы | Холдинг
  Прикрепление: № п/п | ФИО | Дата рождения | Пол | Серия и номер полиса | Адрес | Телефон | Дата прикрепления | Дата открепления | Место работы | Холдинг | Объём | Программа
ФИО is already combined in one column.
"""
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse VSK format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Find header row (contains "ФИО" and "полис")
    header_row = None
    for i in range(min(15, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фио' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"VSK: Could not find header row in {filepath}")
        return []

    # Map column indices
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
    col_start = find_col('дата', 'прикрепл')
    col_end = find_col('дата', 'откреплен')
    col_work = find_col('место', 'работ')

    for i in range(header_row + 1, len(df)):
        fio = df.iloc[i, col_fio] if col_fio is not None else None

        if pd.isna(fio) or str(fio).strip() == '':
            continue

        fio = str(fio).strip()

        # Skip footer
        if any(w in fio.lower() for w in ['руководител', 'директор', 'подпись', 'исп.', 'тел.']):
            break

        strahovatel = None
        if col_work is not None and pd.notna(df.iloc[i, col_work]):
            strahovatel = str(df.iloc[i, col_work]).strip()

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': _format_date(df.iloc[i, col_start]) if col_start is not None else None,
            'Конец обслуживания': _format_date(df.iloc[i, col_end]) if col_end is not None else None,
            'Страховая компания': 'ВСК',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"VSK: parsed {len(results)} records from {filepath}")
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
