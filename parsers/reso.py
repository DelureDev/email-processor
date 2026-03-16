"""
Parser for RESO-Garantiya format.
Structure: header row at ~row 8 with columns:
  №п/п | ФИО | Дата рождения | Пол | Адрес | № полиса | Начало обслуживания | Открепление с | Программа | Страхователь
"""
import pandas as pd
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, get_cell_str

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse RESO format xlsx and return list of normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    header_row = find_header_row(df, ('фио', 'полис'), max_rows=20)
    if header_row is None:
        logger.error(f"RESO: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_fio = find_col(headers, 'фио')
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_otkr = find_col(headers, 'откреплен') or find_col(headers, 'оконч', 'обслуж') or find_col(headers, 'окончан')
    col_start = find_col(headers, 'начало', 'обслуж')
    col_strahovatel = find_col(headers, 'страхователь')

    for i in range(header_row + 1, len(df)):
        fio = get_cell_str(df, i, col_fio)
        if not fio:
            continue
        if any(w in fio.lower() for w in ['исполнител', 'директор', 'подпись', 'от  имени']):
            break

        record = {
            'ФИО': fio,
            'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': get_cell_str(df, i, col_polis),
            'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
            'Конец обслуживания': format_date(df.iloc[i, col_otkr]) if col_otkr is not None else None,
            'Страховая компания': 'РЕСО-Гарантия',
            'Страхователь': get_cell_str(df, i, col_strahovatel),
        }
        results.append(record)

    logger.info(f"RESO: parsed {len(results)} records from {filepath}")
    return results
