"""
Parser for ООО СК Согласие format.
Structure:
  Row ~5: "Прикрепление с: DD.MM.YYYY по: DD.MM.YYYY" (dates for all records)
  Row ~6: "Организация: <name>" (Страхователь for all records)
  Row ~13: Header: № | № полиса ДМС | Фамилия | Имя | Отчество | Д/Р | Адрес | Дом.тел | Раб.тел | № карты
  ФИО split into 3 columns.
  Only parse first sheet (TDSheet), skip technical sheet.
"""
import pandas as pd
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Soglasie format xlsx."""
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Extract metadata: dates and organization from upper rows
    start_date = None
    end_date = None
    strahovatel = None

    for i in range(min(15, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()

            # "Прикрепление с: DD.MM.YYYY по: DD.MM.YYYY"
            if 'прикрепление' in val_str.lower() or 'открепление' in val_str.lower():
                # Start date might be in same cell or next column
                dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', val_str)
                if dates:
                    start_date = dates[0]
                # Check next columns for dates
                for k in range(j + 1, min(j + 4, len(df.columns))):
                    next_val = df.iloc[i, k]
                    if pd.notna(next_val):
                        more_dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', str(next_val))
                        for d in more_dates:
                            if start_date is None:
                                start_date = d
                            elif end_date is None:
                                end_date = d

            # "Организация: <name>"
            if 'организация' in val_str.lower() and ':' in val_str:
                # Org name might be after ":" in same cell or in next column
                after_colon = val_str.split(':', 1)[-1].strip()
                if after_colon:
                    strahovatel = after_colon
                else:
                    for k in range(j + 1, min(j + 3, len(df.columns))):
                        next_val = df.iloc[i, k]
                        if pd.notna(next_val) and str(next_val).strip():
                            strahovatel = str(next_val).strip()
                            break

    # Find header row (contains "Фамилия" and "полис")
    header_row = None
    for i in range(min(25, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фамилия' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"SOGLASIE: Could not find header row in {filepath}")
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
    col_birth = find_col('д/р') or find_col('дата', 'рожд')
    col_polis = find_col('полис')

    for i in range(header_row + 1, len(df)):
        familia = df.iloc[i, col_familia] if col_familia is not None else None

        if pd.isna(familia) or str(familia).strip() == '':
            continue

        familia = str(familia).strip()

        if any(w in familia.lower() for w in ['итого', 'всего', 'список', 'согласие']):
            break

        # Combine ФИО
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
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'СК Согласие',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"SOGLASIE: parsed {len(results)} records from {filepath}")
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
