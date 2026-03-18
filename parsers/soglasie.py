"""
Parser for ООО СК Согласие format.
Structure:
  Row ~5: "Прикрепление с: DD.MM.YYYY по: DD.MM.YYYY" (dates for all records)
  Row ~6: "Организация: <name>" (Страхователь for all records)
  Row ~13: Header: № | № полиса ДМС | Фамилия | Имя | Отчество | Д/Р | Адрес | Дом.тел | Раб.тел | № карты
  ФИО split into 3 columns.
  Only parse first sheet (TDSheet), skip technical sheet.
"""
import pandas as pd
import re
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str, assemble_fio

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Soglasie format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Extract metadata: dates and organization from upper rows
    start_date = None
    end_date = None
    strahovatel = None

    for i in range(min(15, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()

            # "Прикрепление с: DD.MM.YYYY по: DD.MM.YYYY" or "Открепление ..."
            is_prikr = 'прикрепление' in val_str.lower()
            is_otkr = 'открепление' in val_str.lower()
            if is_prikr or is_otkr:
                all_dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', val_str)
                for k in range(j + 1, min(j + 4, len(df.columns))):
                    next_val = df.iloc[i, k]
                    if pd.notna(next_val):
                        all_dates.extend(re.findall(r'\d{2}\.\d{2}\.\d{4}', str(next_val)))
                if is_otkr and all_dates:
                    if end_date is None:
                        end_date = all_dates[0]
                elif is_prikr and all_dates:
                    if start_date is None:
                        start_date = all_dates[0]
                    if len(all_dates) >= 2 and end_date is None:
                        end_date = all_dates[1]

            # "Организация: <name>"
            if 'организация' in val_str.lower() and ':' in val_str:
                after_colon = val_str.split(':', 1)[-1].strip()
                if after_colon:
                    strahovatel = after_colon
                else:
                    for k in range(j + 1, min(j + 3, len(df.columns))):
                        next_val = df.iloc[i, k]
                        if pd.notna(next_val) and str(next_val).strip():
                            strahovatel = str(next_val).strip()
                            break

    header_row = find_header_row(df, ('фамилия', 'полис'), max_rows=25)
    if header_row is None:
        logger.error(f"SOGLASIE: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_familia = find_col(headers, 'фамилия')
    col_imya = find_col(headers, 'имя')
    col_otchestvo = find_col(headers, 'отчество')
    col_birth = first_col(headers, ('д/р',), ('дата', 'рожд'))
    col_polis = find_col(headers, 'полис')

    for i in range(header_row + 1, len(df)):
        familia = get_cell_str(df, i, col_familia)
        if not familia:
            continue
        if any(w in familia.lower() for w in ['итого', 'всего', 'список', 'согласие']):
            continue

        fio = assemble_fio(df, i, col_familia, col_imya, col_otchestvo)

        record = {
            'ФИО': fio,
            'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': get_cell_str(df, i, col_polis),
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'СК Согласие',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"SOGLASIE: parsed {len(results)} records from {filepath}")
    return results
