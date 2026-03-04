"""
Parser for Ингосстрах (SPISKI_LPU) format.
Structure:
  Row 2: СПАО "Ингосстрах" + исх. номер
  Row 4: "Прикрепление/Открепление DD.MM.YYYY"
  Row 7: Договор: XXXXXXX-XX/XX + По факту
  Row 9: Страхователь: ...
  Row 11: Окончание договора: DD.MM.YYYY
  Row 12: Header — п/п | Полис | Фамилия | Имя | Отчество | Д.Рожд. | Пол | ... | Дата прикрепления | Дата открепления | ...
  Row 13+: Data rows (FIO split into 3 columns)
"""
import pandas as pd
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def parse(filepath: str) -> list[dict]:
    """Parse Ingosstrakh SPISKI_LPU format and return normalized records."""
    df = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)
    results = []

    # Extract metadata from upper rows
    strahovatel = None
    dogovor_end = None

    for i in range(min(15, len(df))):
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            if pd.isna(val):
                continue
            val_str = str(val).strip()

            # Страхователь (row ~9)
            if 'страхователь:' in val_str.lower():
                # Extract name after "Страхователь:"
                match = re.search(r'страхователь:\s*(.+)', val_str, re.IGNORECASE)
                if match:
                    strahovatel = match.group(1).strip()

            # Окончание договора (row ~11)
            if 'окончание договора' in val_str.lower():
                dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', val_str)
                if dates:
                    dogovor_end = dates[0]

    # Find header row (contains "Фамилия" and "Полис")
    header_row = None
    for i in range(min(20, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'фамилия' in row_text and 'полис' in row_text:
            header_row = i
            break

    if header_row is None:
        logger.error(f"INGOS: Could not find header row in {filepath}")
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
    col_birth = find_col('д.рожд') or find_col('дата', 'рожд')
    col_polis = find_col('полис')
    col_prikr = find_col('дата', 'прикрепл')
    col_otkr = find_col('дата', 'откреплен')

    if col_familia is None:
        logger.error(f"INGOS: Could not find 'Фамилия' column in {filepath}")
        return []

    # Parse data rows
    for i in range(header_row + 1, len(df)):
        familia = df.iloc[i, col_familia] if col_familia is not None else None

        if pd.isna(familia) or str(familia).strip() == '':
            continue

        familia = str(familia).strip()

        # Skip non-data rows
        if any(w in familia.lower() for w in ['итого', 'всего', 'клиентов', 'страница']):
            break

        # Build full name from split columns
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

        # Get dates
        start_date = _clean_date(df.iloc[i, col_prikr]) if col_prikr is not None else None
        end_date = _clean_date(df.iloc[i, col_otkr]) if col_otkr is not None else dogovor_end

        # Get policy
        polis = None
        if col_polis is not None and pd.notna(df.iloc[i, col_polis]):
            polis = str(df.iloc[i, col_polis]).strip()

        record = {
            'ФИО': fio,
            'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
            '№ полиса': polis,
            'Начало обслуживания': start_date,
            'Конец обслуживания': end_date,
            'Страховая компания': 'Ингосстрах',
            'Страхователь': strahovatel,
        }
        results.append(record)

    logger.info(f"INGOS: parsed {len(results)} records from {filepath}")
    return results


def _clean_date(val) -> str | None:
    """Clean date value - strip whitespace."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s:
        return None
    return _format_date(s)


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
