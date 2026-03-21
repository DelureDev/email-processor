"""
Parser for Зетта Страхование жизни format.
Structure: header row at ~row 16 with columns:
  № п/п | Номер полиса | ФИО | Дата рождения | Паспорт | Домашний адрес | Телефон | Служебный телефон
Metadata in rows above: Организация (~row 10), Договор № (~row 11), Срок действия (~row 12)
"""
import pandas as pd
import re
import logging

from parsers.utils import format_date, find_header_row, build_header_map, find_col, first_col, get_cell_str

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Zetta format xlsx and return list of normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    # Extract metadata from upper rows
    strahovatel = None
    srok_start = None
    srok_end = None

    for i in range(min(20, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()

            # Organization name (Страхователь)
            if 'организация' in val_str.lower() and ':' in val_str:
                for k in range(j + 1, len(df.columns)):
                    next_val = df.iloc[i, k]
                    if pd.notna(next_val) and str(next_val).strip():
                        strahovatel = str(next_val).strip()
                        break

            # Срок действия (validity period)
            if 'срок действия' in val_str.lower():
                for k in range(j + 1, len(df.columns)):
                    next_val = df.iloc[i, k]
                    if pd.notna(next_val):
                        period = str(next_val).strip()
                        dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', period)
                        if len(dates) >= 1:
                            srok_start = dates[0]
                        if len(dates) >= 2:
                            srok_end = dates[1]
                        break

    # Find header row
    header_row = find_header_row(df, ('фио', 'полис'), max_rows=25)
    if header_row is None:
        header_row = find_header_row(df, ('фамилия имя', 'полис'), max_rows=25)
    if header_row is None:
        logger.error(f"ZETTA: Could not find header row in {filepath}")
        for dbg_i in range(min(20, len(df))):
            dbg_vals = [str(v) for v in df.iloc[dbg_i] if pd.notna(v)]
            if dbg_vals:
                logger.error(f"ZETTA DEBUG row {dbg_i}: {dbg_vals}")
        return []

    headers = build_header_map(df, header_row)
    col_fio = first_col(headers, ('фио',), ('фамилия имя',), ('фамилия',))
    if col_fio is None:
        logger.error(f"ZETTA: Could not find FIO column in {filepath}")
        return []
    col_birth = find_col(headers, 'дата', 'рожд')
    col_polis = first_col(headers, ('полис',), ('номер',))

    for i in range(header_row + 1, len(df)):
        try:
            fio = get_cell_str(df, i, col_fio)
            if not fio:
                first_val = get_cell_str(df, i, 0)
                if first_val and 'клиентов' in first_val.lower():
                    break
                continue

            fio = fio.upper()
            if any(w in fio.lower() for w in ['итого', 'всего', 'клиентов', 'программа']):
                continue

            record = {
                'ФИО': fio,
                'Дата рождения': format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': get_cell_str(df, i, col_polis),
                'Начало обслуживания': srok_start,
                'Конец обслуживания': srok_end,
                'Страховая компания': 'Зетта Страхование жизни',
                'Страхователь': strahovatel,
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"ZETTA: Skipping row {i} due to error: {e}")

    logger.info(f"ZETTA: parsed {len(results)} records from {filepath}")
    return results
