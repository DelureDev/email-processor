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
    _clinics = []
    for entry in data.get('clinics', []):
        name = entry.get('name', '').strip()
        keywords = sorted(entry.get('keywords', []), key=len, reverse=True)
        if name and keywords:
            _clinics.append({'name': name, 'keywords': keywords})
    logger.debug(f"Loaded {len(_clinics)} clinics from {config_path}")
    return _clinics


def _file_to_text(filepath: str) -> str:
    """Read entire xlsx/xls into a single lowercased string for keyword scanning."""
    try:
        xl = pd.ExcelFile(filepath)
        parts = []
        for sheet in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet, header=None, dtype=str)
            parts.append(df.fillna('').to_string())
        return ' '.join(parts).lower()
    except Exception as e:
        logger.warning(f"clinic_matcher: could not read {filepath}: {e}")
        return ''


def detect_clinic(filepath: str, config_path: str = 'clinics.yaml') -> str:
    """
    Scan file for clinic keywords. Returns clinic name or '⚠️ Не определено'.
    Keywords sorted longest-first to avoid partial matches (e.g. 'Детская стоматология №2'
    is checked before 'Детская стоматология').
    """
    clinics = _load_clinics(config_path)
    if not clinics:
        return '⚠️ Не определено'

    text = _file_to_text(filepath)
    if not text:
        return '⚠️ Не определено'

    for clinic in clinics:
        for keyword in clinic['keywords']:
            if keyword.lower() in text:
                logger.debug(f"Clinic matched: '{clinic['name']}' via keyword '{keyword}' in {os.path.basename(filepath)}")
                return clinic['name']

    logger.warning(f"No clinic matched for {os.path.basename(filepath)} — setting '⚠️ Не определено'")
    return '⚠️ Не определено'
