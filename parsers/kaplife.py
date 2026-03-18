"""
Parser for ООО Капитал Лайф Страхование Жизни format.
Two types:
  - Прикрепление: Header row 9: № п/п | Страхователь | Полис | Фамилия | Имя | Отчество | Дата рождения | Пол | Объём | Дата начала | Дата окончания | Адрес | Телефон | Франшиза
  - ИзменениеФЛ: Data corrections (typo fixes etc.) — different header, we still extract useful data
ФИО split into 3 columns (Фамилия, Имя, Отчество).
"""
import pandas as pd
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str, assemble_fio

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Kapital Life format."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Find header row — look for row with "Фамилия" or "Ф.И.О." and "Полис"
    header_row = find_header_row(df, ('фамилия', 'полис'), max_rows=20)
    is_change_format = False
    if header_row is None:
        header_row = find_header_row(df, ('ф.и.о', 'полис'), max_rows=20)
        if header_row is not None:
            is_change_format = True

    if header_row is None:
        logger.error(f"KAPLIFE: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)

    if is_change_format:
        # ИзменениеФЛ format: ФИО is combined in "Ф.И.О. (Новая)" column
        col_fio_new = first_col(headers, ('ф.и.о', 'новая'), ('ф.и.о',))
        col_birth = find_col(headers, 'дата', 'рожд')
        col_polis = find_col(headers, 'полис')
        col_start = find_col(headers, 'дата', 'прикрепл')
        col_end = find_col(headers, 'дата', 'откреп')
        col_strah = find_col(headers, 'страхователь')

        for i in range(header_row + 1, len(df)):
            try:
                polis = get_cell_str(df, i, col_polis)
                if not polis:
                    continue
                fio = get_cell_str(df, i, col_fio_new)
                if not fio:
                    continue
                if any(w in fio.lower() for w in ['контакт-центр', 'руководител', 'исполнител']):
                    continue
                record = {
                    'ФИО': fio.upper(),
                    'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                    '№ полиса': polis,
                    'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
                    'Конец обслуживания': format_date(df.iloc[i, col_end]) if col_end is not None else None,
                    'Страховая компания': 'Капитал Лайф',
                    'Страхователь': get_cell_str(df, i, col_strah),
                }
                results.append(record)
            except Exception as e:
                logger.warning(f"KAPLIFE: Skipping row {i} due to error: {e}")
    else:
        # Standard Прикрепление format: split ФИО
        col_familia = find_col(headers, 'фамилия')
        col_imya = find_col(headers, 'имя')
        col_otchestvo = find_col(headers, 'отчество')
        col_birth = find_col(headers, 'дата', 'рожд')
        col_polis = find_col(headers, 'полис')
        col_start = find_col(headers, 'дата', 'начал')
        col_end = find_col(headers, 'дата', 'оконч')
        col_strah = find_col(headers, 'страхователь')

        for i in range(header_row + 1, len(df)):
            try:
                familia = get_cell_str(df, i, col_familia)
                if not familia:
                    continue
                if any(w in familia.lower() for w in ['контакт-центр', 'руководител', 'исполнител', 'медицинский']):
                    continue

                fio = assemble_fio(df, i, col_familia, col_imya, col_otchestvo)

                record = {
                    'ФИО': fio.upper(),
                    'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                    '№ полиса': get_cell_str(df, i, col_polis),
                    'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
                    'Конец обслуживания': format_date(df.iloc[i, col_end]) if col_end is not None else None,
                    'Страховая компания': 'Капитал Лайф',
                    'Страхователь': get_cell_str(df, i, col_strah),
                }
                results.append(record)
            except Exception as e:
                logger.warning(f"KAPLIFE: Skipping row {i} due to error: {e}")

    logger.info(f"KAPLIFE: parsed {len(results)} records from {filepath}")
    return results
