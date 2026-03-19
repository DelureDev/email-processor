"""
Generic parser for unknown formats that have standard column headers.
Handles two variants:
  - GENERIC_FIO: single "ФИО" column + "полис" column
  - GENERIC_FIO_SPLIT: separate "Фамилия"/"Имя"/"Отчество" columns + "полис" column

Extracts whatever it can find — ФИО, birth date, policy, dates, company name.
Used as a fallback when no specific parser matches.
"""
import pandas as pd
import re
import logging

from parsers.utils import format_date, build_header_map, find_col, first_col, get_cell_str, assemble_fio

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse a generic format file with standard column headers."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    # Try to extract company name and dates from upper rows
    strahovatel = None
    start_date = None
    end_date = None

    for i in range(min(20, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            val_lower = val_str.lower()

            if 'организация' in val_lower and ':' in val_str:
                after = val_str.split(':', 1)[-1].strip()
                if after:
                    strahovatel = after
                else:
                    for k in range(j + 1, min(j + 3, len(df.columns))):
                        nv = df.iloc[i, k]
                        if pd.notna(nv) and str(nv).strip():
                            strahovatel = str(nv).strip()
                            break

            if 'страхователь' in val_lower and ':' in val_str:
                after = val_str.split(':', 1)[-1].strip()
                if after:
                    strahovatel = after

            dates_found = re.findall(r'\d{2}\.\d{2}\.\d{4}', val_str)
            if dates_found and ('прикрепл' in val_lower or 'обслуж' in val_lower or 'действ' in val_lower or 'срок' in val_lower):
                if len(dates_found) >= 1 and start_date is None:
                    start_date = dates_found[0]
                if len(dates_found) >= 2 and end_date is None:
                    end_date = dates_found[1]

    # Find header row
    header_row = None
    has_split_fio = False

    for i in range(min(25, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)

        if 'фио' in row_text and ('полис' in row_text or '№ полиса' in row_text):
            header_row = i
            has_split_fio = False
            break
        if 'фамилия' in row_text and 'имя' in row_text:
            header_row = i
            has_split_fio = True
            break

    if header_row is None:
        logger.error(f"GENERIC: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)

    # FIO columns
    col_fio = find_col(headers, 'фио')
    col_familia = find_col(headers, 'фамилия')
    col_imya = find_col(headers, 'имя')
    col_otch = find_col(headers, 'отчество')

    # Other columns
    col_birth = first_col(headers, ('д/р',), ('д.рожд',), ('дата', 'рожд'))
    col_polis = find_col(headers, 'полис')
    col_start = first_col(headers, ('дата', 'прикрепл'), ('дата', 'начал'), ('начало',))
    col_end = first_col(headers, ('дата', 'откреплен'), ('дата', 'оконч'), ('последний',), ('конец',))
    col_company = find_col(headers, 'страхов', 'компан')
    col_work = first_col(headers, ('место', 'работ'), ('страхователь',))

    for i in range(header_row + 1, len(df)):
        try:
            if has_split_fio:
                familia = get_cell_str(df, i, col_familia)
                if not familia:
                    continue
                if any(w in familia.lower() for w in ['итого', 'всего', 'генеральный', 'директор', 'страница']):
                    continue
                fio = assemble_fio(df, i, col_familia, col_imya, col_otch).upper()
            else:
                fio = get_cell_str(df, i, col_fio)
                if not fio:
                    continue
                fio = fio.upper()
                if any(w in fio.lower() for w in ['итого', 'всего', 'клиентов', 'программа']):
                    continue

            row_start = format_date(df.iloc[i, col_start]) if col_start is not None else start_date
            row_end = format_date(df.iloc[i, col_end]) if col_end is not None else end_date
            row_company = get_cell_str(df, i, col_company)
            row_work = get_cell_str(df, i, col_work) or strahovatel

            record = {
                'ФИО': fio,
                'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': get_cell_str(df, i, col_polis),
                'Начало обслуживания': row_start,
                'Конец обслуживания': row_end,
                'Страховая компания': row_company or 'Неизвестная СК',
                'Страхователь': row_work,
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"GENERIC: Skipping row {i} due to error: {e}")

    logger.info(f"GENERIC: parsed {len(results)} records from {filepath}")
    return results
