"""
Parser for Лучи Здоровье format.
Structure:
  Row 1: "ООО «Лучи Здоровье»" in a multi-line cell
  Row 14: "Для Клиника Фэнтези на ..."
  Row 15: "Прошу вас в соответствии с договором ..."
  Row 16: "Принять на медицинское обслуживание..." or "Снять с медицинского обслуживания..."
  Row 17: Header — №п/п | № полиса | Фамилия | Имя | Отчество | Пол | Дата рождения | ... | Дата начала | Последний день | Место работы | ...
  Row 18+: Data rows (FIO split into 3 columns)

Прикрепление cols: №п/п | № полиса | Фамилия | Имя | Отчество | Пол | Дата рождения | Адрес | Телефон | Дата начала обслуживания | Последний день обслуживания | Место работы | Программа | Тип оплаты | Клиники сети
Открепление cols:  №п/п | № полиса | Фамилия | Имя | Отчество | Пол | Дата рождения | Последний день обслуживания | Место работы | Программа | Тип оплаты | Клиники сети
"""
import pandas as pd
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Лучи Здоровье format and return normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    # Extract metadata
    strahovatel = None

    # Find header row (contains "Фамилия" and "полиса")
    header_row = None
    for i in range(min(25, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фамилия' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"LUCHI: Could not find header row in {filepath}")
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

    col_familia = find_col('фамилия')
    col_imya = find_col('имя')
    col_otch = find_col('отчество')
    col_birth = find_col('дата', 'рожд')
    col_polis = find_col('полис')
    col_start = find_col('дата', 'начал')
    col_end = find_col('последний', 'день')
    col_work = find_col('место', 'работ')

    if col_familia is None:
        logger.error(f"LUCHI: Could not find 'Фамилия' column in {filepath}")
        return []

    # Parse data rows
    for i in range(header_row + 1, len(df)):
        familia = df.iloc[i, col_familia] if col_familia is not None else None

        if pd.isna(familia) or str(familia).strip() == '':
            continue

        familia = str(familia).strip()

        # Skip footer rows
        if any(w in familia.lower() for w in ['итого', 'всего', 'генеральный', 'директор']):
            break

        # Build full name
        parts = [familia]
        if col_imya is not None:
            imya = df.iloc[i, col_imya]
            if pd.notna(imya) and str(imya).strip():
                parts.append(str(imya).strip())
        if col_otch is not None:
            otch = df.iloc[i, col_otch]
            if pd.notna(otch) and str(otch).strip():
                parts.append(str(otch).strip())

        fio = ' '.join(parts).upper()

        # Dates
        start_date = _format_date(df.iloc[i, col_start]) if col_start is not None else None
        end_date = _format_date(df.iloc[i, col_end]) if col_end is not None else None

        # Policy
        polis = None
        if col_polis is not None and pd.notna(df.iloc[i, col_polis]):
            polis = str(df.iloc[i, col_polis]).strip()

        # Strahovatel from "Место работы"
        if col_work is not None and pd.notna(df.iloc[i, col_work]):
            strahovatel = str(df.iloc[i, col_work]).strip()

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': polis,
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'Лучи Здоровье',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"LUCHI: parsed {len(results)} records from {filepath}")
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
