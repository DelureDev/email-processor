"""
Parser for ООО СК Сбербанк страхование format.
Structure: header row at ~row 7 with columns:
  № п/п | № полиса (ID) | Фамилия | Имя | Отчество | Дата рождения | Адрес | Телефон | Дата начала | Дата окончания | Место работы | Программа | Клиники сети
ФИО is split into 3 columns (Фамилия, Имя, Отчество).
"""
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Sberbank Strakhovanie format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Find header row (contains "Фамилия" and "полис")
    header_row = None
    for i in range(min(20, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фамилия' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"SBER: Could not find header row in {filepath}")
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

    col_familia = find_col('фамилия')
    col_imya = find_col('имя')
    col_otchestvo = find_col('отчество')
    col_birth = find_col('дата', 'рожд')
    col_polis = find_col('полис')
    col_start = find_col('дата', 'начал')
    col_end = find_col('дата', 'оконч')
    col_work = find_col('место', 'работ')

    for i in range(header_row + 1, len(df)):
        familia = df.iloc[i, col_familia] if col_familia is not None else None

        if pd.isna(familia) or str(familia).strip() == '':
            continue

        familia = str(familia).strip()

        # Skip footer rows
        if any(w in familia.lower() for w in ['итого', 'всего', 'список', 'заказчик']):
            break

        # Combine ФИО
        parts = [familia]
        if col_imya is not None and pd.notna(df.iloc[i, col_imya]):
            parts.append(str(df.iloc[i, col_imya]).strip())
        if col_otchestvo is not None and pd.notna(df.iloc[i, col_otchestvo]):
            parts.append(str(df.iloc[i, col_otchestvo]).strip())
        fio = ' '.join(parts)

        # Страхователь from "Место работы"
        strahovatel = None
        if col_work is not None and pd.notna(df.iloc[i, col_work]):
            strahovatel = str(df.iloc[i, col_work]).strip()

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': _format_date(df.iloc[i, col_start]) if col_start is not None else None,
            'Конец обслуживания': _format_date(df.iloc[i, col_end]) if col_end is not None else None,
            'Страховая компания': 'Сбербанк страхование',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"SBER: parsed {len(results)} records from {filepath}")
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
