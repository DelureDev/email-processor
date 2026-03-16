"""
Parser for ПАО Группа Ренессанс Страхование format.
Structure:
  Row ~15: "сотрудников:" + company name (Страхователь)
  Row ~17: "на срок: с DD.MM.YYYY г. по DD.MM.YYYY г."
  Row ~20: Header: № п/п | Фамилия (actually full ФИО) | Дата рождения | Паспорт | Адрес | Телефон | № полиса
  ФИО already combined in "Фамилия" column.
"""
import pandas as pd
import re
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, get_cell_str

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Renessans Strakhovanie format."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Extract metadata from upper rows
    start_date = None
    end_date = None
    strahovatel = None

    for i in range(min(25, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()

            # "сотрудников:" row — next column has company name
            if 'сотрудников' in val_str.lower():
                for k in range(j + 1, min(j + 3, len(df.columns))):
                    nv = df.iloc[i, k]
                    if pd.notna(nv) and str(nv).strip():
                        strahovatel = str(nv).strip()
                        break

            # "на срок: с DD.MM.YYYY г. по DD.MM.YYYY г."
            if 'на срок' in val_str.lower() or ('с ' in val_str and ' по ' in val_str and re.search(r'\d{2}\.\d{2}\.\d{4}', val_str)):
                combined = val_str
                for k in range(j + 1, min(j + 3, len(df.columns))):
                    nv = df.iloc[i, k]
                    if pd.notna(nv):
                        combined += ' ' + str(nv).strip()
                dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', combined)
                if len(dates) >= 2:
                    start_date = dates[0]
                    end_date = dates[1]
                elif len(dates) == 1:
                    start_date = dates[0]

    header_row = find_header_row(df, ('фамилия', 'полис'), max_rows=25)
    if header_row is None:
        header_row = find_header_row(df, ('фио', 'полис'), max_rows=25)
    if header_row is None:
        logger.error(f"RENINS: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_fio = find_col(headers, 'фамилия') or find_col(headers, 'фио')
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')

    for i in range(header_row + 1, len(df)):
        fio = get_cell_str(df, i, col_fio)
        if not fio:
            continue
        # Skip clinic code rows (short strings like "С532") and footers
        if len(fio) < 5 or any(w in fio.lower() for w in ['руководител', 'исполнител', 'директор']):
            continue
        # Check if it's actually a data row (col 0 should be a number)
        row_num = df.iloc[i, 0]
        if pd.isna(row_num):
            continue
        try:
            int(float(row_num))
        except (ValueError, TypeError):
            continue

        record = {
            'ФИО': fio,
            'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': get_cell_str(df, i, col_polis),
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'Ренессанс Страхование',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"RENINS: parsed {len(results)} records from {filepath}")
    return results
