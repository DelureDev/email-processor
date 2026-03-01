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

    # Strategy: find all data rows by looking for rows where col 0 is a number
    # and col 2 (ФИО) has a name
    for i in range(len(df)):
        # Check if this is a data row (col 0 is a sequential number)
        val_0 = df.iloc[i, 0]
        if pd.isna(val_0):
            continue
        try:
            row_num = int(float(val_0))
            if row_num < 1:
                continue
        except (ValueError, TypeError):
            continue

        # Verify it's a real data row — col 2 should have a name (ФИО)
        fio = df.iloc[i, 2] if len(df.columns) > 2 else None
        if pd.isna(fio) or str(fio).strip() == '':
            continue

        fio = str(fio).strip()

        # Skip if it doesn't look like a name
        if any(w in fio.lower() for w in ['№ п/п', 'список', 'альфастрахование']):
            continue

        # Extract fields
        polis = str(df.iloc[i, 1]).strip() if pd.notna(df.iloc[i, 1]) else None
        birth = _format_date(df.iloc[i, 3]) if len(df.columns) > 3 and pd.notna(df.iloc[i, 3]) else None

        # Period: col 6 = "с" (start), col 7 = "по" (end)
        start_date = _format_date(df.iloc[i, 6]) if len(df.columns) > 6 and pd.notna(df.iloc[i, 6]) else None
        end_date = _format_date(df.iloc[i, 7]) if len(df.columns) > 7 and pd.notna(df.iloc[i, 7]) else None

        # Страхователь from col 5: "Группа Яндекс; №0330S/045/7828/24П; ООО "Яндекс.Лавка""
        strahovatel = None
        if len(df.columns) > 5 and pd.notna(df.iloc[i, 5]):
            group_str = str(df.iloc[i, 5]).strip()
            parts = group_str.split(';')
            if len(parts) >= 3:
                strahovatel = parts[-1].strip()
            elif len(parts) == 2:
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
