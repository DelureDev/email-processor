"""
Parser for САО ВСК format.
Two variations:
  Открепление: № п/п | ФИО | Дата рождения | Полис № | Дата открепления | Место работы | Холдинг
  Прикрепление: № п/п | ФИО | Дата рождения | Пол | Серия и номер полиса | Адрес | Телефон | Дата прикрепления | Дата открепления | Место работы | Холдинг | Объём | Программа
ФИО is already combined in one column.
"""
import pandas as pd
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse VSK format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    header_row = find_header_row(df, ('фио', 'полис'), max_rows=15)
    if header_row is None:
        logger.error(f"VSK: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_fio = find_col(headers, 'фио')
    if col_fio is None:
        logger.error(f"VSK: Could not find FIO column in {filepath}")
        return []
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_start = find_col(headers, 'дата', 'прикрепл')
    col_end = find_col(headers, 'дата', 'откреплен')
    col_work = first_col(headers, ('холдинг',), ('место', 'работ'))

    for i in range(header_row + 1, len(df)):
        try:
            fio = get_cell_str(df, i, col_fio)
            if not fio:
                continue
            if any(w in fio.lower() for w in ['руководител', 'директор', 'подпись', 'исп.', 'тел.']):
                continue

            record = {
                'ФИО': fio.upper(),
                'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': get_cell_str(df, i, col_polis),
                'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
                'Конец обслуживания': format_date(df.iloc[i, col_end]) if col_end is not None else None,
                'Страховая компания': 'ВСК',
                'Страхователь': get_cell_str(df, i, col_work),
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"VSK: Skipping row {i} due to error: {e}")

    logger.info(f"VSK: parsed {len(results)} records from {filepath}")
    return results
