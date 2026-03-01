"""
Parser for ООО ПСБ Страхование format.
Same structure as Yugoriya: split ФИО (Фамилия, Имя, Отчество), same column layout.
Header at row ~6: № п/п | полис | фамилия | имя | отчество | Пол | дата рождения | адрес | телефон | Дата прикрепления/открепления | ...| Наименование Страхователя | Название страховой компании
"""
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse PSB Strakhovanie format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    header_row = None
    for i in range(min(20, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фамилия' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"PSB: Could not find header row in {filepath}")
        return []

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
    col_start = find_col('дата', 'прикрепл')
    col_end = find_col('дата', 'откреп')
    col_strahovatel = find_col('наименование', 'страхователя') or find_col('наименование', 'страхователь') or find_col('страхователь')

    for i in range(header_row + 1, len(df)):
        familia = df.iloc[i, col_familia] if col_familia is not None else None
        if pd.isna(familia) or str(familia).strip() == '':
            continue
        familia = str(familia).strip()
        if any(w in familia.lower() for w in ['исполнител', 'директор', 'подпись', 'начальник', 'специалист']):
            break

        parts = [familia]
        if col_imya is not None and pd.notna(df.iloc[i, col_imya]):
            parts.append(str(df.iloc[i, col_imya]).strip())
        if col_otchestvo is not None and pd.notna(df.iloc[i, col_otchestvo]):
            parts.append(str(df.iloc[i, col_otchestvo]).strip())
        fio = ' '.join(parts)

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': str(df.iloc[i, col_polis]).strip() if col_polis is not None and pd.notna(df.iloc[i, col_polis]) else None,
            'Начало обслуживания': _format_date(df.iloc[i, col_start]) if col_start is not None else None,
            'Конец обслуживания': _format_date(df.iloc[i, col_end]) if col_end is not None else None,
            'Страховая компания': 'ПСБ Страхование',
            'Страхователь': str(df.iloc[i, col_strahovatel]).strip() if col_strahovatel is not None and pd.notna(df.iloc[i, col_strahovatel]) else None,
        }
        results.append(record)

    logger.info(f"PSB: parsed {len(results)} records from {filepath}")
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
