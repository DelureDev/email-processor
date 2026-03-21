"""
Parser for ООО СК Сбербанк страхование format.
Structure: header row at ~row 7 with columns:
  № п/п | № полиса (ID) | Фамилия | Имя | Отчество | Дата рождения | Адрес | Телефон | Дата начала | Дата окончания | Место работы | Программа | Клиники сети
ФИО is split into 3 columns (Фамилия, Имя, Отчество).
"""
import pandas as pd
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, get_cell_str, assemble_fio

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Sberbank Strakhovanie format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    header_row = find_header_row(df, ('фамилия', 'полис'), max_rows=20)
    if header_row is None:
        logger.error(f"SBER: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_familia = find_col(headers, 'фамилия')
    if col_familia is None:
        logger.error(f"SBER: Could not find 'Фамилия' column in {filepath}")
        return []
    col_imya = find_col(headers, 'имя')
    col_otchestvo = find_col(headers, 'отчество')
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_start = find_col(headers, 'дата', 'начал')
    col_end = find_col(headers, 'дата', 'оконч')
    col_work = find_col(headers, 'место', 'работ')

    for i in range(header_row + 1, len(df)):
        try:
            familia = get_cell_str(df, i, col_familia)
            if not familia:
                continue
            if any(w in familia.lower() for w in ['итого', 'всего', 'список', 'заказчик']):
                continue

            fio = assemble_fio(df, i, col_familia, col_imya, col_otchestvo)
            record = {
                'ФИО': fio.upper(),
                'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': get_cell_str(df, i, col_polis),
                'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
                'Конец обслуживания': format_date(df.iloc[i, col_end]) if col_end is not None else None,
                'Страховая компания': 'Сбербанк страхование',
                'Страхователь': get_cell_str(df, i, col_work),
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"SBER: Skipping row {i} due to error: {e}")

    logger.info(f"SBER: parsed {len(results)} records from {filepath}")
    return results
