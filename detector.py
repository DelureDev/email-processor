"""
Format Detector — identifies which of the known formats an xlsx file matches.
Two-stage detection:
  1. Sender-based (fast, reliable) — if sender is known, skip content analysis
  2. Content-based (fallback) — read first 25 rows and match keywords
"""
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ─── Sender → Format mapping ─────────────────────────────────────────────────
# Maps known sender substrings (lowercase) to format names.
# Checked first — if matched, skip content-based detection entirely.
SENDER_FORMAT_MAP = {
    'spiski.dms@reso.ru': 'reso',
    'spiski@psbins.ru': 'psb',
    'avis@alfastrah.ru': 'alfa',
    'alfapriority@alfastrah.ru': 'alfa',
    'zetta_life_spiski@zettains.ru': 'zetta',
    'pulse.letter@zettains.ru': 'zetta',
    'spiski_lpu@ingos.ru': 'ingos',
    'list@luchi.ru': 'luchi',
    'shahova@energogarant.ru': 'energogarant',
    'spiski@absolutins.ru': 'absolut',
    'spiski-dms@ugsk.ru': 'yugoriya',
    'spiskirobot': 'vsk',
    'spiski_lpu@soglasie.ru': 'soglasie',
    'pultdms@soglasie.ru': 'soglasie',
    'dobrovolnoe_ms@sberbankins.ru': 'sber',
    'digital.assistant@sberins.ru': 'sber',
    'dms@kaplife.ru': 'kaplife',
}


def detect_by_sender(sender: str) -> str | None:
    """Try to detect format from sender email address."""
    if not sender:
        return None
    sender_lower = sender.lower()
    for sender_key, fmt in SENDER_FORMAT_MAP.items():
        if sender_key in sender_lower:
            return fmt
    return None


# ─── Content-based detection rules ──────────────────────────────────────────
# Each entry: (format_name, required_keywords_tuple)
# All keywords must appear in the text blob (first 25 rows, lowercased).
# Order matters — more specific rules first.
CONTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ('reso',        ('ресо-гарантия',)),
    ('reso',        ('ресо',)),
    ('yugoriya',    ('югория',)),
    ('zetta',       ('зетта', 'страхован')),
    ('alfa',        ('альфастрахован',)),
    ('sber',        ('сбербанк страхован',)),
    ('sber',        ('список застрахованных лиц', 'фамилия')),
    ('soglasie',    ('согласие', 'фамилия')),
    ('absolut',     ('абсолют', 'страхован')),
    ('psb',         ('псб', 'страхован')),
    ('kaplife',     ('капитал лайф',)),
    ('kaplife',     ('капитал', 'страхован', 'жизни')),
    ('euroins',     ('евроинс',)),
    ('renins',      ('ренессанс',)),
    ('luchi',       ('лучи здоровье',)),
    ('energogarant',('энергогарант',)),
    ('ingos',       ('ингосстрах',)),
    ('vsk',         ('вск', 'фио')),
    ('vsk',         ('контингента',)),
]


def detect_format(filepath: str, sender: str = None) -> str | None:
    """
    Detect which format the xlsx file is.
    Args:
        filepath: path to the xlsx/xls file
        sender: optional sender email address (enables fast sender-based detection)
    Returns format name string or None if unknown.
    """
    # Stage 1: Sender-based detection (fast, reliable)
    if sender:
        fmt = detect_by_sender(sender)
        if fmt:
            logger.info(f"Detected format: {fmt.upper()} (sender: {sender}) ({filepath})")
            return fmt

    # Stage 2: Content-based detection (fallback)
    try:
        with pd.ExcelFile(filepath) as xl:
            # Sheet 0 only: insurers put their data on the first sheet
            df = xl.parse(sheet_name=xl.sheet_names[0], header=None, nrows=25)
        text_blob = ' '.join(str(v) for v in df.values.flat if pd.notna(v)).lower()

        for fmt, keywords in CONTENT_RULES:
            if all(kw in text_blob for kw in keywords):
                logger.info(f"Detected format: {fmt.upper()} ({filepath})")
                return fmt

        # Fallback: generic detection by column headers (low confidence)
        for row_idx in range(min(20, len(df))):
            row_values = [str(v).lower().strip() for v in df.iloc[row_idx] if pd.notna(v)]
            row_text = ' '.join(row_values)
            if 'фио' in row_text and ('полис' in row_text or '№ полиса' in row_text):
                logger.warning(f"Low-confidence detection: GENERIC_FIO ({filepath}) — consider adding a content rule")
                return 'generic_fio'
            if 'фамилия' in row_text and 'имя' in row_text:
                logger.warning(f"Low-confidence detection: GENERIC_FIO_SPLIT ({filepath}) — consider adding a content rule")
                return 'generic_fio_split'

        logger.warning(f"Unknown format: {filepath}")
        return None

    except Exception as e:
        logger.error(f"Error detecting format for {filepath}: {e}")
        return None
