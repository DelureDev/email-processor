"""
Parser for Ингосстрах (SPISKI_LPU) format.
Structure:
  Row 2: СПАО "Ингосстрах" + исх. номер
  Row 4: "Прикрепление/Открепление DD.MM.YYYY"
  Row 7: Договор: XXXXXXX-XX/XX + По факту
  Row 9: Страхователь: ...
  Row 11: Окончание договора: DD.MM.YYYY
  Row 12: Header — п/п | Полис | Фамилия | Имя | Отчество | Д.Рожд. | Пол | ... | Дата прикрепления | Дата открепления | ...
  Row 13+: Data rows (FIO split into 3 columns)
"""
import pandas as pd
import logging
import re

from parsers.utils import format_date, find_header_row, build_header_map, find_col, get_cell_str, assemble_fio

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Ingosstrakh SPISKI_LPU format and return normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    # Extract metadata from upper rows
    strahovatel = None

    for i in range(min(15, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()

            if 'страхователь:' in val_str.lower():
                match = re.search(r'страхователь:\s*(.+)', val_str, re.IGNORECASE)
                if match:
                    strahovatel = match.group(1).strip()

    header_row = find_header_row(df, ('фамилия', 'полис'), max_rows=20)
    if header_row is None:
        logger.error(f"INGOS: Could not find header row in {filepath}")
        return []

    headers = build_header_map(df, header_row)
    col_familia = find_col(headers, 'фамилия')
    col_imya = find_col(headers, 'имя')
    col_otch = find_col(headers, 'отчество')
    col_birth = find_col(headers, 'д.рожд') or find_col(headers, 'дата', 'рожд')
    col_polis = find_col(headers, 'полис')
    col_prikr = find_col(headers, 'дата', 'прикрепл')
    col_otkr = find_col(headers, 'дата', 'откреплен')

    if col_familia is None:
        logger.error(f"INGOS: Could not find 'Фамилия' column in {filepath}")
        return []

    for i in range(header_row + 1, len(df)):
        familia = get_cell_str(df, i, col_familia)
        if not familia:
            continue
        if any(w in familia.lower() for w in ['итого', 'всего', 'клиентов', 'страница']):
            break

        fio = assemble_fio(df, i, col_familia, col_imya, col_otch).upper()

        start_date = format_date(df.iloc[i, col_prikr]) if col_prikr is not None else None
        end_date = format_date(df.iloc[i, col_otkr]) if col_otkr is not None else None

        record = {
            'ФИО': fio,
            'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': get_cell_str(df, i, col_polis),
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'Ингосстрах',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"INGOS: parsed {len(results)} records from {filepath}")
    return results
