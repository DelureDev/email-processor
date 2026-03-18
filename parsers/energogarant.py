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

from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Энергогарант format and return normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    header_row = find_header_row(df, ('фио', 'полис'), max_rows=25)
    if header_row is None:
        logger.error(f"ENERGOGARANT: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_fio = find_col(headers, 'фио')
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_prikr = find_col(headers, 'дата', 'прикрепл')
    col_otkr = find_col(headers, 'дата', 'откреплен')
    col_work = first_col(headers, ('место', 'работ'), ('страхователь',))

    if col_fio is None:
        logger.error(f"ENERGOGARANT: Could not find 'ФИО' column in {filepath}")
        return []

    for i in range(header_row + 1, len(df)):
        try:
            fio = get_cell_str(df, i, col_fio)
            if not fio:
                continue
            if any(w in fio.lower() for w in ['итого', 'всего', 'с уважением', 'директор', 'начальник']):
                continue

            record = {
                'ФИО': fio.upper(),
                'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': get_cell_str(df, i, col_polis),
                'Начало обслуживания': format_date(df.iloc[i, col_prikr]) if col_prikr is not None else None,
                'Конец обслуживания': format_date(df.iloc[i, col_otkr]) if col_otkr is not None else None,
                'Страховая компания': 'Энергогарант',
                'Страхователь': get_cell_str(df, i, col_work),
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"ENERGOGARANT: Skipping row {i} due to error: {e}")

    logger.info(f"ENERGOGARANT: parsed {len(results)} records from {filepath}")
    return results
