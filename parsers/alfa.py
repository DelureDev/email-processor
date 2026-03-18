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
import logging

from parsers.utils import format_date, get_cell_str

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse AlfaStrah format xlsx and return list of normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Defaults (overridden by header detection below)
    col_num = 0
    col_polis = 1
    col_fio = 2
    col_birth = 3
    col_group = 5
    col_start = 6
    col_end = 7

    # Try to find header row and map columns
    header_found = False
    for hi in range(min(30, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[hi] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фио' in row_text and 'полис' in row_text:
            header_found = True
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

    if not header_found:
        logger.error(f"ALFA: Could not find header row in {filepath}")
        return []

    # Find all data rows by looking for rows where col_num is a number
    for i in range(len(df)):
        try:
            val_0 = df.iloc[i, col_num]
            if pd.isna(val_0):
                continue
            try:
                row_num = int(float(val_0))
                if row_num < 1:
                    continue
            except (ValueError, TypeError):
                continue

            fio = get_cell_str(df, i, col_fio)
            if not fio:
                continue

            if any(w in fio.lower() for w in ['№ п/п', 'список', 'альфастрахование']):
                continue

            polis = get_cell_str(df, i, col_polis)
            birth = format_date(df.iloc[i, col_birth]) if len(df.columns) > col_birth and pd.notna(df.iloc[i, col_birth]) else None
            start_date = format_date(df.iloc[i, col_start]) if len(df.columns) > col_start and pd.notna(df.iloc[i, col_start]) else None
            end_date = format_date(df.iloc[i, col_end]) if len(df.columns) > col_end and pd.notna(df.iloc[i, col_end]) else None

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
                'ФИО': fio.upper(),
                'Дата рождения': birth,
                '№ полиса': polis,
                'Начало обслуживания': start_date,
                'Конец обслуживания': end_date,
                'Страховая компания': 'АльфаСтрахование',
                'Страхователь': strahovatel,
            }
            results.append(record)
        except Exception as e:
            logger.warning(f"ALFA: Skipping row {i} due to error: {e}")

    logger.info(f"ALFA: parsed {len(results)} records from {filepath}")
    return results
