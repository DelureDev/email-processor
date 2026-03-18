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

from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str

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

    # Find header row — Euroins uses "Ф.И.О" not "ФИО"
    header_row = find_header_row(df, ('ф.и.о', 'полис'), max_rows=20)
    if header_row is None:
        header_row = find_header_row(df, ('фио', 'полис'), max_rows=20)
    if header_row is None:
        logger.error(f"EUROINS: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_fio = first_col(headers, ('ф.и.о',), ('фио',))
    if col_fio is None:
        logger.error(f"EUROINS: Could not find FIO column in {filepath}")
        return []
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')

    for i in range(header_row + 1, len(df)):
        try:
            fio = get_cell_str(df, i, col_fio)
            if not fio:
                continue
            if any(w in fio.lower() for w in ['рамках', 'программ', 'руководител', 'исполнител', '*']):
                continue

            record = {
                'ФИО': fio.upper(),
                'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': get_cell_str(df, i, col_polis),
                'Начало обслуживания': start_date,
                'Конец обслуживания': end_date,
                'Страховая компания': 'Евроинс',
                'Страхователь': None,
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"EUROINS: Skipping row {i} due to error: {e}")

    logger.info(f"EUROINS: parsed {len(results)} records from {filepath}")
    return results
