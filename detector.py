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
            df = xl.parse(sheet_name=xl.sheet_names[0], header=None, nrows=25)
        text_blob = ' '.join(str(v) for v in df.values.flat if pd.notna(v)).lower()

        # --- Format A: RESO-Garantiya style ---
        if 'ресо-гарантия' in text_blob or 'ресо' in text_blob:
            logger.info(f"Detected format: RESO ({filepath})")
            return 'reso'

        # --- Format B: Yugoriya style ---
        if 'югория' in text_blob:
            logger.info(f"Detected format: YUGORIYA ({filepath})")
            return 'yugoriya'

        # --- Format C: Zetta style ---
        if 'зетта' in text_blob and 'страхован' in text_blob:
            logger.info(f"Detected format: ZETTA ({filepath})")
            return 'zetta'

        # --- Format D: AlfaStrakhovanie style ---
        if 'альфастрахован' in text_blob:
            logger.info(f"Detected format: ALFA ({filepath})")
            return 'alfa'

        # --- Format E: Sberbank Strakhovanie style ---
        if 'сбербанк страхован' in text_blob or ('список застрахованных лиц' in text_blob and 'фамилия' in text_blob):
            logger.info(f"Detected format: SBER ({filepath})")
            return 'sber'

        # --- Format F: Soglasie style ---
        if 'согласие' in text_blob and 'фамилия' in text_blob:
            logger.info(f"Detected format: SOGLASIE ({filepath})")
            return 'soglasie'

        # --- Format H: Absolut Strakhovanie style ---
        if 'абсолют' in text_blob and 'страхован' in text_blob:
            logger.info(f"Detected format: ABSOLUT ({filepath})")
            return 'absolut'

        # --- Format I: PSB Strakhovanie style ---
        if 'псб' in text_blob and 'страхован' in text_blob:
            logger.info(f"Detected format: PSB ({filepath})")
            return 'psb'

        # --- Format J: Kapital Life style ---
        if 'капитал лайф' in text_blob or ('капитал' in text_blob and 'страхован' in text_blob and 'жизни' in text_blob):
            logger.info(f"Detected format: KAPLIFE ({filepath})")
            return 'kaplife'

        # --- Format K: Euroins style ---
        if 'евроинс' in text_blob:
            logger.info(f"Detected format: EUROINS ({filepath})")
            return 'euroins'

        # --- Format L: Renessans Strakhovanie style ---
        if 'ренессанс' in text_blob:
            logger.info(f"Detected format: RENINS ({filepath})")
            return 'renins'

        # --- Format N: Лучи Здоровье style ---
        if 'лучи здоровье' in text_blob:
            logger.info(f"Detected format: LUCHI ({filepath})")
            return 'luchi'

        # --- Format O: Энергогарант style ---
        if 'энергогарант' in text_blob:
            logger.info(f"Detected format: ENERGOGARANT ({filepath})")
            return 'energogarant'

        # --- Format M: Ingosstrakh (SPISKI_LPU) style ---
        if 'ингосстрах' in text_blob:
            logger.info(f"Detected format: INGOS ({filepath})")
            return 'ingos'

        # --- Format G: VSK style ---
        if ('вск' in text_blob and 'фио' in text_blob) or 'контингента' in text_blob:
            logger.info(f"Detected format: VSK ({filepath})")
            return 'vsk'

        # --- Fallback: generic detection by column headers ---
        for row_idx in range(min(20, len(df))):
            row_values = [str(v).lower().strip() for v in df.iloc[row_idx] if pd.notna(v)]
            row_text = ' '.join(row_values)

            # Generic format with ФИО column
            if 'фио' in row_text and ('полис' in row_text or '№ полиса' in row_text):
                logger.info(f"Detected format: GENERIC_FIO ({filepath})")
                return 'generic_fio'

            # Generic format with separate Фамилия/Имя/Отчество
            if 'фамилия' in row_text and 'имя' in row_text:
                logger.info(f"Detected format: GENERIC_FIO_SPLIT ({filepath})")
                return 'generic_fio_split'

        logger.warning(f"Unknown format: {filepath}")
        return None

    except Exception as e:
        logger.error(f"Error detecting format for {filepath}: {e}")
        return None
