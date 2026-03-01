"""
Parser for ООО Капитал Лайф Страхование Жизни format.
Files come as .xls — need xlrd or LibreOffice conversion.
Two types:
  - Прикрепление: Header row 9: № п/п | Страхователь | Полис | Фамилия | Имя | Отчество | Дата рождения | Пол | Объём | Дата начала | Дата окончания | Адрес | Телефон | Франшиза
  - ИзменениеФЛ: Data corrections (typo fixes etc.) — different header, we still extract useful data
ФИО split into 3 columns (Фамилия, Имя, Отчество).
"""
import pandas as pd
import logging
import subprocess
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def _ensure_xlsx(filepath: str) -> str:
    """Convert .xls to .xlsx if needed. Returns path to xlsx file."""
    if filepath.lower().endswith('.xls'):
        outdir = os.path.dirname(filepath) or '.'
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'xlsx', filepath, '--outdir', outdir],
            capture_output=True, timeout=60
        )
        xlsx_path = filepath + 'x'  # .xls -> .xlsx
        if os.path.exists(xlsx_path):
            return xlsx_path
        # Try without the extra x
        base = os.path.splitext(filepath)[0]
        xlsx_path = base + '.xlsx'
        if os.path.exists(xlsx_path):
            return xlsx_path
        logger.error(f"KAPLIFE: Failed to convert {filepath}: {result.stderr}")
        return filepath
    return filepath


def parse(filepath: str) -> list[dict]:
    """Parse Kapital Life format."""
    filepath = _ensure_xlsx(filepath)
    df = pd.read_excel(filepath, sheet_name=0, header=None)
    results = []

    # Find header row — look for row with "Фамилия" or "Ф.И.О." and "Полис"
    header_row = None
    is_change_format = False
    for i in range(min(20, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if 'полис' in row_text and ('фамилия' in row_text or 'ф.и.о' in row_text):
            header_row = i
            if 'ф.и.о' in row_text:
                is_change_format = True
            break

    if header_row is None:
        logger.error(f"KAPLIFE: Could not find header row in {filepath}")
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

    if is_change_format:
        # ИзменениеФЛ format: ФИО is combined in "Ф.И.О. (Новая)" column
        col_fio_new = find_col('ф.и.о', 'новая') or find_col('ф.и.о')
        col_birth = find_col('дата', 'рожд')
        col_polis = find_col('полис')
        col_start = find_col('дата', 'прикрепл')
        col_end = find_col('дата', 'откреп')
        col_strah = find_col('страхователь')

        for i in range(header_row + 1, len(df)):
            polis = df.iloc[i, col_polis] if col_polis is not None else None
            if pd.isna(polis) or str(polis).strip() == '':
                continue
            fio = str(df.iloc[i, col_fio_new]).strip() if col_fio_new is not None and pd.notna(df.iloc[i, col_fio_new]) else None
            if not fio:
                continue
            if any(w in fio.lower() for w in ['контакт-центр', 'руководител', 'исполнител']):
                break
            record = {
                'ФИО': fio,
                'Дата рождения': _format_date(df.iloc[i, col_birth]) if col_birth is not None else None,
                '№ полиса': str(polis).strip(),
                'Начало обслуживания': _format_date(df.iloc[i, col_start]) if col_start is not None else None,
                'Конец обслуживания': _format_date(df.iloc[i, col_end]) if col_end is not None else None,
                'Страховая компания': 'Капитал Лайф',
                'Страхователь': str(df.iloc[i, col_strah]).strip() if col_strah is not None and pd.notna(df.iloc[i, col_strah]) else None,
            }
            results.append(record)
    else:
        # Standard Прикрепление format: split ФИО
        col_familia = find_col('фамилия')
        col_imya = find_col('имя')
        col_otchestvo = find_col('отчество')
        col_birth = find_col('дата', 'рожд')
        col_polis = find_col('полис')
        col_start = find_col('дата', 'начал')
        col_end = find_col('дата', 'оконч')
        col_strah = find_col('страхователь')

        for i in range(header_row + 1, len(df)):
            familia = df.iloc[i, col_familia] if col_familia is not None else None
            if pd.isna(familia) or str(familia).strip() == '':
                continue
            familia = str(familia).strip()
            if any(w in familia.lower() for w in ['контакт-центр', 'руководител', 'исполнител', 'медицинский']):
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
                'Страховая компания': 'Капитал Лайф',
                'Страхователь': str(df.iloc[i, col_strah]).strip() if col_strah is not None and pd.notna(df.iloc[i, col_strah]) else None,
            }
            results.append(record)

    logger.info(f"KAPLIFE: parsed {len(results)} records from {filepath}")
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
