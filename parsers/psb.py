"""
Parser for ООО ПСБ Страхование format.
Same structure as Yugoriya: split ФИО (Фамилия, Имя, Отчество), same column layout.
Header at row ~6: № п/п | полис | фамилия | имя | отчество | Пол | дата рождения | адрес | телефон | Дата прикрепления/открепления | ...| Наименование Страхователя | Название страховой компании
"""
import pandas as pd
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str, assemble_fio

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse PSB Strakhovanie format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    header_row = find_header_row(df, ('фамилия', 'полис'), max_rows=20)
    if header_row is None:
        logger.error(f"PSB: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_familia = find_col(headers, 'фамилия')
    col_imya = find_col(headers, 'имя')
    col_otchestvo = find_col(headers, 'отчество')
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_start = find_col(headers, 'дата', 'прикрепл')
    col_end = find_col(headers, 'дата', 'откреп')
    col_strahovatel = first_col(headers, ('наименование', 'страхователя'), ('наименование', 'страхователь'), ('страхователь',))

    for i in range(header_row + 1, len(df)):
        familia = get_cell_str(df, i, col_familia)
        if not familia:
            continue
        if any(w in familia.lower() for w in ['исполнител', 'директор', 'подпись', 'начальник', 'специалист']):
            continue

        fio = assemble_fio(df, i, col_familia, col_imya, col_otchestvo)

        record = {
            'ФИО': fio,
            'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': get_cell_str(df, i, col_polis),
            'Начало обслуживания': format_date(df.iloc[i, col_start]) if col_start is not None else None,
            'Конец обслуживания': format_date(df.iloc[i, col_end]) if col_end is not None else None,
            'Страховая компания': 'ПСБ Страхование',
            'Страхователь': get_cell_str(df, i, col_strahovatel),
        }
        results.append(record)

    logger.info(f"PSB: parsed {len(results)} records from {filepath}")
    return results
