"""
Parser for АО ГСК Югория format.
Structure: header row at ~row 6 with columns:
  № п/п | Полис | Фамилия | Имя | Отчество | Пол | Дата рождения | Адрес | Телефон | Дата открепления | Страхователь | Страховая компания
"""
import pandas as pd
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str, assemble_fio

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Yugoriya format xlsx and return list of normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    header_row = find_header_row(df, ('фамилия', 'полис'), max_rows=20)
    if header_row is None:
        logger.error(f"YUGORIYA: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_familia = find_col(headers, 'фамилия')
    if col_familia is None:
        logger.error(f"YUGORIYA: Could not find 'Фамилия' column in {filepath}")
        return []
    col_imya = find_col(headers, 'имя')
    col_otchestvo = find_col(headers, 'отчество')
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_start = find_col(headers, 'дата', 'прикрепл')
    col_otkr = find_col(headers, 'дата', 'откреп')
    col_strahovatel = first_col(headers, ('наименование', 'страхователя'), ('наименование', 'страхователь'), ('страхователь',))
    col_sk = first_col(headers, ('страховой', 'компани'), ('страховая',))

    for i in range(header_row + 1, len(df)):
        try:
            familia = get_cell_str(df, i, col_familia)
            if not familia:
                continue
            if any(w in familia.lower() for w in ['югория', 'директор', 'подпись', 'итого']):
                continue

            fio = assemble_fio(df, i, col_familia, col_imya, col_otchestvo).upper()
            sk = get_cell_str(df, i, col_sk) or 'ГСК Югория'
            record = {
                'ФИО': fio,
                'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': get_cell_str(df, i, col_polis),
                'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
                'Конец обслуживания': format_date(df.iloc[i, col_otkr]) if col_otkr is not None else None,
                'Страховая компания': sk,
                'Страхователь': get_cell_str(df, i, col_strahovatel),
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"YUGORIYA: Skipping row {i} due to error: {e}")

    logger.info(f"YUGORIYA: parsed {len(results)} records from {filepath}")
    return results
