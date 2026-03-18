"""
Parser for Лучи Здоровье format.
Structure:
  Row 1: "ООО «Лучи Здоровье»" in a multi-line cell
  Row 14: "Для Клиника Фэнтези на ..."
  Row 15: "Прошу вас в соответствии с договором ..."
  Row 16: "Принять на медицинское обслуживание..." or "Снять с медицинского обслуживания..."
  Row 17: Header — №п/п | № полиса | Фамилия | Имя | Отчество | Пол | Дата рождения | ... | Дата начала | Последний день | Место работы | ...
  Row 18+: Data rows (FIO split into 3 columns)
"""
import pandas as pd
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, get_cell_str, assemble_fio

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Лучи Здоровье format and return normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    header_row = find_header_row(df, ('фамилия', 'полис'), max_rows=25)
    if header_row is None:
        logger.error(f"LUCHI: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_familia = find_col(headers, 'фамилия')
    col_imya = find_col(headers, 'имя')
    col_otch = find_col(headers, 'отчество')
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_start = find_col(headers, 'дата', 'начал')
    col_end = find_col(headers, 'последний', 'день')
    col_work = find_col(headers, 'место', 'работ')

    if col_familia is None:
        logger.error(f"LUCHI: Could not find 'Фамилия' column in {filepath}")
        return []

    for i in range(header_row + 1, len(df)):
        try:
            familia = get_cell_str(df, i, col_familia)
            if not familia:
                continue
            if any(w in familia.lower() for w in ['итого', 'всего', 'генеральный', 'директор']):
                continue

            fio = assemble_fio(df, i, col_familia, col_imya, col_otch).upper()
            record = {
                'ФИО': fio,
                'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': get_cell_str(df, i, col_polis),
                'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
                'Конец обслуживания': format_date(df.iloc[i, col_end]) if col_end is not None else None,
                'Страховая компания': 'Лучи Здоровье',
                'Страхователь': get_cell_str(df, i, col_work),
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"LUCHI: Skipping row {i} due to error: {e}")

    logger.info(f"LUCHI: parsed {len(results)} records from {filepath}")
    return results
