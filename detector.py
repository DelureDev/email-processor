"""
Format Detector — identifies which of the known formats an xlsx file matches.
"""
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def detect_format(filepath: str) -> str | None:
    """
    Detect which format the xlsx file is.
    Returns format name string or None if unknown.
    """
    try:
        xl = pd.ExcelFile(filepath)
        sheet_name = xl.sheet_names[0]
        df = pd.read_excel(filepath, sheet_name=sheet_name, header=None, nrows=20)
        text_blob = df.to_string().lower()

        # --- Format A: RESO-Garantiya style ---
        # Markers: "ресо-гарантия", header row with "№\nп/п", "ФИО", "Дата рождения", "№ полиса"
        if 'ресо-гарантия' in text_blob or 'ресо' in text_blob:
            logger.info(f"Detected format: RESO ({filepath})")
            return 'reso'

        # --- Format B: Yugoriya style ---
        # Markers: "югория", header with "Полис", "Фамилия", "Имя", "Отчество", "Дата рождения"
        if 'югория' in text_blob:
            logger.info(f"Detected format: YUGORIYA ({filepath})")
            return 'yugoriya'

        # --- Format C: Zetta style ---
        # Markers: "зетта страхование жизни", header with "ФИО", "Номер полиса"
        if 'зетта' in text_blob and 'страхован' in text_blob:
            logger.info(f"Detected format: ZETTA ({filepath})")
            return 'zetta'

        # --- Format D: AlfaStrakhovanie style ---
        # Markers: "альфастрахование", repeating blocks with "Период обслуживания"
        if 'альфастрахован' in text_blob:
            logger.info(f"Detected format: ALFA ({filepath})")
            return 'alfa'

        # --- Format E: Sberbank Strakhovanie style ---
        # Markers: "сбербанк страхование" or "список застрахованных лиц" + "фамилия"/"имя"/"отчество"
        if 'сбербанк страхован' in text_blob or ('список застрахованных лиц' in text_blob and 'фамилия' in text_blob):
            logger.info(f"Detected format: SBER ({filepath})")
            return 'sber'

        # --- Format F: Soglasie style ---
        # Markers: "согласие", header with "полис" + "фамилия"
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
        if 'капитал лайф' in text_blob or 'капитал' in text_blob and 'страхован' in text_blob and 'жизни' in text_blob:
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
        # Markers: "лучи здоровье" in header area
        if 'лучи здоровье' in text_blob:
            logger.info(f"Detected format: LUCHI ({filepath})")
            return 'luchi'

        # --- Format O: Энергогарант style ---
        # Markers: "энергогарант" in text
        if 'энергогарант' in text_blob:
            logger.info(f"Detected format: ENERGOGARANT ({filepath})")
            return 'energogarant'

        # --- Format O: Энергогарант style ---
        # Markers: "энергогарант" in text
        if 'энергогарант' in text_blob:
            logger.info(f"Detected format: ENERGOGARANT ({filepath})")
            return 'energogarant'

        # --- Format M: Ingosstrakh (SPISKI_LPU) style ---
        # Markers: "ингосстрах" or header with split ФИО + "полис" + "д.рожд"
        if 'ингосстрах' in text_blob:
            logger.info(f"Detected format: INGOS ({filepath})")
            return 'ingos'

        # --- Format G: VSK style ---
        # Markers: "вск" + "фио", or "контингента" (прикрепляемого/открепляемого)
        if ('вск' in text_blob and 'фио' in text_blob) or 'контингента' in text_blob:
            logger.info(f"Detected format: VSK ({filepath})")
            return 'vsk'

        # --- Fallback: try to detect by column headers ---
        for row_idx in range(min(15, len(df))):
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
