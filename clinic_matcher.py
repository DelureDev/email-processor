"""
Clinic matcher — scans an xlsx/xls file for known clinic keywords
and returns the matching clinic name from clinics.yaml.
"""
import os
import logging
import yaml
import pandas as pd

logger = logging.getLogger(__name__)

_clinics: list[dict] | None = None

# Maximum cell length considered a header (not data) in extract_policy_comment
_MAX_HEADER_LEN = 60


def reload_clinics() -> None:
    """Invalidate the clinic cache. Useful in tests that swap clinics.yaml."""
    global _clinics
    _clinics = None


def _load_clinics(config_path: str = 'clinics.yaml') -> list[dict]:
    """Load and cache clinics config. Each entry has 'name' and sorted 'keywords' (longest first)."""
    global _clinics
    if _clinics is not None:
        return _clinics
    if not os.path.exists(config_path):
        logger.warning(f"clinics.yaml not found at {config_path} — clinic detection disabled")
        _clinics = []
        return _clinics
    with open(config_path, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    # Build a flat list of (keyword, clinic_name, extract_comment) sorted globally by keyword length
    # (longest first) to prevent shorter keywords from matching before more specific longer ones.
    entries = []
    for entry in data.get('clinics', []):
        name = entry.get('name', '').strip()
        extract_comment = entry.get('extract_comment', False)
        for kw in entry.get('keywords', []):
            if name and kw:
                entries.append({'name': name, 'keyword': kw.lower(), 'extract_comment': extract_comment})
    entries.sort(key=lambda e: len(e['keyword']), reverse=True)
    _clinics = entries
    logger.debug(f"Loaded {len(_clinics)} clinic keyword entries from {config_path}")
    return _clinics


def _file_to_text(filepath: str) -> str:
    """Read entire xlsx/xls into a single lowercased string for keyword scanning."""
    try:
        with pd.ExcelFile(filepath) as xl:
            parts = []
            for sheet in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sheet, header=None, dtype=str)
                parts.append(df.fillna('').to_string())
        return ' '.join(parts).lower()
    except Exception as e:
        logger.warning(f"clinic_matcher: could not read {filepath}: {e}")
        return ''


# Column names to search for program/service description (in order of priority)
_COMMENT_COLUMNS = [
    'вид медицинского обслуживания',
    'наименование программы дмс',
    'программа дмс',
    'вид обслуживания',
    'программа страхования',
    'программа',
]

# Keywords that indicate a free-text row is a program description
_COMMENT_ROW_KEYWORDS = ['поликлиническое', 'амбулаторно', 'стоматологическое', 'программа']


def detect_clinic(filepath: str, config_path: str = 'clinics.yaml') -> tuple[str, bool]:
    """
    Scan file for clinic keywords.
    Returns (clinic_name, extract_comment) tuple.
    clinic_name is '⚠️ Не определено' if no match found.
    extract_comment is True if this clinic has extract_comment: true in clinics.yaml.
    """
    clinics = _load_clinics(config_path)
    if not clinics:
        return '⚠️ Не определено', False

    text = _file_to_text(filepath)
    if not text:
        return '⚠️ Не определено', False

    for entry in clinics:
        if entry['keyword'] in text:
            logger.debug(f"Clinic matched: '{entry['name']}' via keyword '{entry['keyword']}' in {os.path.basename(filepath)}")
            return entry['name'], entry['extract_comment']

    logger.warning(f"No clinic matched for {os.path.basename(filepath)} — setting '⚠️ Не определено'")
    return '⚠️ Не определено', False


def extract_policy_comment(filepath: str) -> str:
    """
    Extract program/service description from file for Комментарий в полис.
    Strategy:
      1. Look for known column headers → take first non-empty cell value
      2. Scan all rows for free-text program description lines
    Returns empty string if nothing found.
    """
    try:
        with pd.ExcelFile(filepath) as xl:
            for sheet in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sheet, header=None, dtype=str).fillna('')

                # Strategy 1: known column headers
                for row_idx in range(min(20, len(df))):
                    row = [str(v).strip().lower() for v in df.iloc[row_idx]]
                    for col_kw in _COMMENT_COLUMNS:
                        for col_idx, cell in enumerate(row):
                            if col_kw in cell and len(cell) < _MAX_HEADER_LEN:
                                for data_row in range(row_idx + 1, min(row_idx + 5, len(df))):
                                    val = str(df.iloc[data_row, col_idx]).strip()
                                    if val and val.lower() not in ('nan', ''):
                                        logger.debug(f"Comment found via column '{col_kw}': {val[:60]}")
                                        return val

                # Strategy 2: free-text row scan
                for row_idx in range(len(df)):
                    for col_idx in range(len(df.columns)):
                        cell = str(df.iloc[row_idx, col_idx]).strip()
                        cell_lower = cell.lower()
                        if len(cell) > 20 and any(kw in cell_lower for kw in _COMMENT_ROW_KEYWORDS):
                            logger.debug(f"Comment found via free-text row {row_idx}: {cell[:60]}")
                            return cell

    except Exception as e:
        logger.warning(f"extract_policy_comment: could not read {filepath}: {e}")

    logger.warning(f"extract_policy_comment: nothing found in {os.path.basename(filepath)} — add column header to _COMMENT_COLUMNS or keyword to _COMMENT_ROW_KEYWORDS")
    return ''
