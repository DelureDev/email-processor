"""
Parser for ООО Абсолют Страхование format.
Structure:
  Row 5: Header: № п/п | ФИО | Дата рождения | Адрес | № полиса | Дата начала действия полиса | Дата окончания действия полиса | Программа | СТРАХОВАТЕЛЬ
  ФИО already combined.
"""
import pandas as pd
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, get_cell_str

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Absolut Strakhovanie format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    header_row = find_header_row(df, ('фио', 'полис'), max_rows=15)
    if header_row is None:
        logger.error(f"ABSOLUT: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_fio = find_col(headers, 'фио')
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_start = find_col(headers, 'дата', 'начал')
    col_end = find_col(headers, 'дата', 'оконч')
    col_strah = find_col(headers, 'страхователь')

    for i in range(header_row + 1, len(df)):
        fio = get_cell_str(df, i, col_fio)
        if not fio:
            continue
        if any(w in fio.lower() for w in ['руководител', 'директор', 'подпись', 'исп.']):
            break

        record = {
            'ФИО': fio,
            'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': get_cell_str(df, i, col_polis),
            'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
            'Конец обслуживания': format_date(df.iloc[i, col_end]) if col_end is not None else None,
            'Страховая компания': 'Абсолют Страхование',
            'Страхователь': get_cell_str(df, i, col_strah),
        }
        results.append(record)

    logger.info(f"ABSOLUT: parsed {len(results)} records from {filepath}")
    return results
