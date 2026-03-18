"""
Shared parser utilities — eliminates duplication across all parsers.
"""
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


def format_date(val) -> str | None:
    """Normalize any date value to DD.MM.YYYY string."""
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
    logger.warning(f"format_date: unrecognized date format {s!r}, returning as-is")
    return s


def find_header_row(df, keywords: tuple[str, ...], max_rows: int = 25) -> int | None:
    """Find the first row containing all keywords (case-insensitive)."""
    for i in range(min(max_rows, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        row_text = ' '.join(row_values)
        if all(kw in row_text for kw in keywords):
            return i
    return None


def build_header_map(df, header_row: int) -> dict[str, int]:
    """Build a {lowercased_header: col_index} map from a header row."""
    headers = {}
    for col_idx in range(len(df.columns)):
        val = df.iloc[header_row, col_idx]
        if pd.notna(val):
            headers[str(val).strip().lower().replace('\n', ' ')] = col_idx
    return headers


def find_col(headers: dict[str, int], *keywords: str) -> int | None:
    """Find column index where header contains all keywords."""
    for key, idx in headers.items():
        if all(kw in key for kw in keywords):
            return idx
    return None


def first_col(headers: dict[str, int], *keyword_sets) -> int | None:
    """Try keyword sets in order, return first non-None column index found.

    Replaces `find_col(...) or find_col(...)` chains which silently fail
    when the correct column is at index 0 (falsy in Python).

    Usage: first_col(headers, ('фио',), ('фамилия', 'имя'))
    """
    for kws in keyword_sets:
        result = find_col(headers, *kws)
        if result is not None:
            return result
    return None


def assemble_fio(df, row_idx: int, col_familia: int,
                 col_imya: int | None = None,
                 col_otch: int | None = None) -> str:
    """Combine split Фамилия/Имя/Отчество columns into a single FIO string."""
    parts = [str(df.iloc[row_idx, col_familia]).strip()]
    if col_imya is not None and pd.notna(df.iloc[row_idx, col_imya]):
        parts.append(str(df.iloc[row_idx, col_imya]).strip())
    if col_otch is not None and pd.notna(df.iloc[row_idx, col_otch]):
        parts.append(str(df.iloc[row_idx, col_otch]).strip())
    return ' '.join(parts)


def get_cell_str(df, row_idx: int, col_idx: int | None) -> str | None:
    """Safely get a stripped string from a cell, or None."""
    if col_idx is None:
        return None
    val = df.iloc[row_idx, col_idx]
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None
