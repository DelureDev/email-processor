"""
Generic parser for unknown formats that have standard column headers.
Handles two variants:
  - GENERIC_FIO: single "ФИО" column + "полис" column
  - GENERIC_FIO_SPLIT: separate "Фамилия"/"Имя"/"Отчество" columns + "полис" column

Extracts whatever it can find — ФИО, birth date, policy, dates, company name.
Used as a fallback when no specific parser matches.
"""
import pandas as pd
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse a generic format file with standard column headers."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    # Try to extract company name and dates from upper rows
    company = None
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

            # Look for organization/strahovatel
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

            # Look for страхователь
            if 'страхователь' in val_lower and ':' in val_str:
                after = val_str.split(':', 1)[-1].strip()
                if after:
                    strahovatel = after

            # Look for dates
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

    # Map column indices
    headers = {}
    for col_idx in range(len(df.columns)):
        val = df.iloc[header_row, col_idx]
        if pd.notna(val):
            key = str(val).strip().lower().replace('\n', ' ')
            headers[key] = col_idx

    def find_col(*keywords):
        for key, idx in headers.items():
            if all(kw in key for kw in keywords):
                return idx
        return None

    # FIO columns
    col_fio = find_col('фио')
    col_familia = find_col('фамилия')
    col_imya = find_col('имя')
    col_otch = find_col('отчество')

    # Other columns
    col_birth = find_col('д/р') or find_col('д.рожд') or find_col('дата', 'рожд')
    col_polis = find_col('полис')
    col_start = find_col('дата', 'прикрепл') or find_col('дата', 'начал') or find_col('начало')
    col_end = find_col('дата', 'откреплен') or find_col('дата', 'оконч') or find_col('последний') or find_col('конец')
    col_company = find_col('страхов', 'компан')
    col_work = find_col('место', 'работ') or find_col('страхователь')

    # Parse data rows
    for i in range(header_row + 1, len(df)):
        # Get FIO
        if has_split_fio:
            familia = df.iloc[i, col_familia] if col_familia is not None else None
            if pd.isna(familia) or str(familia).strip() == '':
                continue
            familia = str(familia).strip()
            if any(w in familia.lower() for w in ['итого', 'всего', 'генеральный', 'директор', 'страница']):
                break
            parts = [familia]
            if col_imya is not None and pd.notna(df.iloc[i, col_imya]):
                parts.append(str(df.iloc[i, col_imya]).strip())
            if col_otch is not None and pd.notna(df.iloc[i, col_otch]):
                parts.append(str(df.iloc[i, col_otch]).strip())
            fio = ' '.join(parts).upper()
        else:
            fio_val = df.iloc[i, col_fio] if col_fio is not None else None
            if pd.isna(fio_val) or str(fio_val).strip() == '':
                continue
            fio = str(fio_val).strip().upper()
            if any(w in fio.lower() for w in ['итого', 'всего', 'клиентов', 'программа']):
                break

        # Get other fields
        row_start = _format_date(df.iloc[i, col_start]) if col_start is not None else start_date
        row_end = _format_date(df.iloc[i, col_end]) if col_end is not None else end_date
        row_company = str(df.iloc[i, col_company]).strip() if col_company is not None and pd.notna(df.iloc[i, col_company]) else company
        row_work = str(df.iloc[i, col_work]).strip() if col_work is not None and pd.notna(df.iloc[i, col_work]) else strahovatel

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': row_start,
            'Конец обслуживания': row_end,
            'Страховая компания': row_company or 'Неизвестная СК',
            'Страхователь': row_work,
        }
        results.append(record)

    logger.info(f"GENERIC: parsed {len(results)} records from {filepath}")
    return results


def _format_date(val) -> str | None:
    if pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.strftime('%d.%m.%Y')
    s = str(val).strip()
    if not s:
        return None
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(s, fmt).strftime('%d.%m.%Y')
        except ValueError:
            continue
    return s
