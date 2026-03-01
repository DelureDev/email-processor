"""
Parser for Зетта Страхование жизни format.
Structure: header row at ~row 16 with columns:
  № п/п | Номер полиса | ФИО | Дата рождения | Паспорт | Домашний адрес | Телефон | Служебный телефон
Metadata in rows above: Организация (~row 10), Договор № (~row 11), Срок действия (~row 12)
"""
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Zetta format xlsx and return list of normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, nrows=100)
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
                # The org name might be in the next column
                for k in range(j + 1, len(df.columns)):
                    next_val = df.iloc[i, k]
                    if pd.notna(next_val) and str(next_val).strip():
                        strahovatel = str(next_val).strip()
                        break

            # Срок действия (validity period) -> used for Открепление (end date)
            if 'срок действия' in val_str.lower():
                for k in range(j + 1, len(df.columns)):
                    next_val = df.iloc[i, k]
                    if pd.notna(next_val):
                        period = str(next_val).strip()
                        # Parse "с 27.02.2026 по 08.08.2026"
                        import re
                        dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', period)
                        if len(dates) >= 1:
                            srok_start = dates[0]
                        if len(dates) >= 2:
                            srok_end = dates[1]
                        break

    # Find header row (contains "ФИО" and "полис")
    header_row = None
    for i in range(min(25, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фио' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"ZETTA: Could not find header row in {filepath}")
        return []

    # Map column indices
    headers = {}
    for col_idx in range(len(df.columns)):
        val = df.iloc[header_row, col_idx]
        if pd.notna(val):
            headers[str(val).strip().lower().replace('\n', ' ')] = col_idx

    def find_col(*keywords):
        for key, idx in headers.items():
            if all(kw in key for kw in keywords):
                return idx
        return None

    col_fio = find_col('фио')
    col_birth = find_col('дата', 'рожд')
    col_polis = find_col('полис') or find_col('номер')

    # Parse data rows
    for i in range(header_row + 1, len(df)):
        fio = df.iloc[i, col_fio] if col_fio is not None else None

        if pd.isna(fio) or str(fio).strip() == '':
            # Check if we hit the footer (e.g. "Клиентов :")
            first_val = df.iloc[i, 0] if pd.notna(df.iloc[i, 0]) else ''
            if 'клиентов' in str(first_val).lower():
                break
            continue

        fio = str(fio).strip().upper()

        # Skip non-name rows
        if any(w in fio.lower() for w in ['итого', 'всего', 'клиентов', 'программа']):
            break

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': srok_start,
            'Конец обслуживания': srok_end,
            'Страховая компания': 'Зетта Страхование жизни',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"ZETTA: parsed {len(results)} records from {filepath}")
    return results


def _format_date(val) -> str | None:
    if pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.strftime('%d.%m.%Y')
    s = str(val).strip()
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(s, fmt).strftime('%d.%m.%Y')
        except ValueError:
            continue
    return s
