"""
Parser for АО АльфаСтрахование format.
Structure: repeating blocks, each containing:
  - Row 0: "АО "АльфаСтрахование"" header
  - Row 6/16/etc: Column headers: № п/п | № полиса | ФИО | Дата рождения | Адрес | Группа,договор,организация | Период с | по | Вид обслуживания
  - Row 7/17/etc: Sub-header "с" / "по"
  - Row 8/18/etc: Data row (one person)

Skip files containing "all" in filename (technical files).
Страхователь is extracted from column 5 (last part after last ";").
"""
import pandas as pd
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse AlfaStrah format xlsx and return list of normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Find header row to detect column indices dynamically
    col_num = 0       # № п/п
    col_polis = 1     # № полиса
    col_fio = 2       # ФИО
    col_birth = 3     # Дата рождения
    col_group = 5     # Группа,договор,организация
    col_start = 6     # Период с
    col_end = 7       # Период по

    # Try to find header row and map columns
    for hi in range(min(30, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[hi] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фио' in row_text and 'полис' in row_text:
            for ci in range(len(df.columns)):
                val = df.iloc[hi, ci]
                if pd.isna(val):
                    continue
                h = str(val).strip().lower()
                if 'п/п' in h:
                    col_num = ci
                elif 'полис' in h:
                    col_polis = ci
                elif 'фио' in h:
                    col_fio = ci
                elif 'дата' in h and 'рожд' in h:
                    col_birth = ci
                elif 'группа' in h or 'договор' in h or 'организац' in h:
                    col_group = ci
            # Check next row for "с" / "по" sub-headers
            if hi + 1 < len(df):
                for ci in range(len(df.columns)):
                    sv = df.iloc[hi + 1, ci]
                    if pd.notna(sv):
                        sh = str(sv).strip().lower()
                        if sh == 'с':
                            col_start = ci
                        elif sh == 'по':
                            col_end = ci
            break

    # Strategy: find all data rows by looking for rows where col_num is a number
    for i in range(len(df)):
        val_0 = df.iloc[i, col_num]
        if pd.isna(val_0):
            continue
        try:
            row_num = int(float(val_0))
            if row_num < 1:
                continue
        except (ValueError, TypeError):
            continue

        fio = df.iloc[i, col_fio] if len(df.columns) > col_fio else None
        if pd.isna(fio) or str(fio).strip() == '':
            continue

        fio = str(fio).strip()

        # Skip if it doesn't look like a name
        if any(w in fio.lower() for w in ['№ п/п', 'список', 'альфастрахование']):
            continue

        # Extract fields
        polis = str(df.iloc[i, col_polis]).strip() if len(df.columns) > col_polis and pd.notna(df.iloc[i, col_polis]) else None
        birth = _format_date(df.iloc[i, col_birth]) if len(df.columns) > col_birth and pd.notna(df.iloc[i, col_birth]) else None

        start_date = _format_date(df.iloc[i, col_start]) if len(df.columns) > col_start and pd.notna(df.iloc[i, col_start]) else None
        end_date = _format_date(df.iloc[i, col_end]) if len(df.columns) > col_end and pd.notna(df.iloc[i, col_end]) else None

        # Страхователь from group column: "Группа Яндекс; №0330S/045/7828/24П; ООО "Яндекс.Лавка""
        strahovatel = None
        if len(df.columns) > col_group and pd.notna(df.iloc[i, col_group]):
            group_str = str(df.iloc[i, col_group]).strip()
            parts = group_str.split(';')
            if len(parts) >= 2:
                strahovatel = parts[-1].strip()
            else:
                strahovatel = group_str

        record = {
            'ФИО': fio,
            'Дата рождения': birth,
            '№ полиса': polis,
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'АльфаСтрахование',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"ALFA: parsed {len(results)} records from {filepath}")
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
