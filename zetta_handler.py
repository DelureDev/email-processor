"""
Zetta Handler — handles password-protected zip files from Zetta and Sber Insurance.

Zetta password flows:
  1. parollpu@zettains.ru — MONTHLY password email, sent 1st of month, valid for entire month
     Body: "...в период с DD.MM.YYYY по DD.MM.YYYY" then password on standalone line
  2. pulse.letter@zettains.ru — per-email passwords (fallback)
  3. zetta_life_spiski@zettains.ru — bulk lists (uses monthly or pulse passwords)

Sber password flow:
  - digital.assistant@sberins.ru — password email ("Пароль:XXXX") then zip email

Strategy: collect monthly password first, then per-email passwords, try all against zips.
"""
import os
import re
import zipfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger('audit')

ZETTA_DOMAINS = ['zettains.ru']
SBER_DOMAINS = ['sberins.ru']
PASSWORD_ZIP_DOMAINS = ['zettains.ru', 'sberins.ru']
ZETTA_SENDERS = ['pulse.letter@zettains.ru', 'zetta_life_spiski@zettains.ru']
ZETTA_MONTHLY_PASSWORD_SENDER = 'parollpu@zettains.ru'


def is_zetta_email(sender: str) -> bool:
    """Check if email is from Zetta."""
    sender_lower = sender.lower()
    return any(domain in sender_lower for domain in ZETTA_DOMAINS)


def is_sber_email(sender: str) -> bool:
    """Check if email is from Sberbank Strakhovanie."""
    return 'sberins.ru' in sender.lower()


def is_password_zip_email(sender: str) -> bool:
    """Check if email is from a sender that uses password-protected zips."""
    sender_lower = sender.lower()
    return any(domain in sender_lower for domain in PASSWORD_ZIP_DOMAINS)


def is_zetta_monthly_password_email(sender: str) -> bool:
    """Check if this is Zetta's monthly password email from parollpu@zettains.ru."""
    return ZETTA_MONTHLY_PASSWORD_SENDER in sender.lower()


def extract_monthly_password(body: str) -> dict | None:
    """
    Extract monthly password from Zetta monthly password email.
    Returns {'password': str, 'valid_from': str, 'valid_to': str} or None.
    Body pattern:
      "...в период с DD.MM.YYYY по DD.MM.YYYY ."
      <blank line>
      <password>
    """
    if not body:
        return None

    # Clean HTML if present
    text = re.sub(r'<br\s*/?>', '\n', body)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&quot;', '"').replace('&amp;', '&').replace('&nbsp;', ' ')

    # Find the period dates
    period_match = re.search(r'в период с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})', text)
    if not period_match:
        return None

    valid_from = period_match.group(1)
    valid_to = period_match.group(2)

    # Password is on a standalone line after the period line
    # Split by lines, find the period line, then grab the next non-empty line
    lines = text.split('\n')
    found_period = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if 'в период с' in line:
            found_period = True
            continue
        if found_period and 4 <= len(line) <= 30 and re.match(r'^[\x21-\x7e]+$', line):
            password = line.strip()
            logger.info(f"Found Zetta monthly password: {len(password)} chars (valid {valid_from} - {valid_to})")
            audit_logger.info(f"ZETTA_MONTHLY_PASSWORD_EXTRACTED len={len(password)} valid={valid_from}_{valid_to}")
            return {
                'password': password,
                'valid_from': valid_from,
                'valid_to': valid_to,
            }

    return None


def extract_password_from_body(body: str) -> str | None:
    """Extract password from per-email password body (Zetta pulse or Sber)."""
    if not body:
        return None

    # Pattern 1: "Пароль для открытия гарантийного письма ГП...zip:\n<password>"
    match = re.search(r'\.zip[:\s]*\s*\n?\s*([^\s<\r\n]+)', body)
    if match:
        password = match.group(1).strip()
        if len(password) >= 4:
            logger.info(f"Found password (zip pattern): {len(password)} chars")
            audit_logger.info(f"PASSWORD_EXTRACTED pattern=zip len={len(password)}")
            return password

    # Pattern 2: "Пароль:XXXX" or "Пароль: XXXX" (Sber style)
    match = re.search(r'[Пп]ароль[:\s]+([^\s<\r\n]+)', body)
    if match:
        password = match.group(1).strip()
        if len(password) >= 3 and 'поступит' not in password.lower() and 'от' not in password.lower():
            logger.info(f"Found password (direct pattern): {len(password)} chars")
            audit_logger.info(f"PASSWORD_EXTRACTED pattern=direct len={len(password)}")
            return password

    return None


def extract_password_from_html(html_body: str) -> str | None:
    """Extract password from HTML email body."""
    if not html_body:
        return None

    text = re.sub(r'<br\s*/?>', '\n', html_body)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&quot;', '"').replace('&amp;', '&').replace('&nbsp;', ' ')

    return extract_password_from_body(text)


def unzip_with_password(zip_path: str, password: str, extract_to: str) -> list[str]:
    """
    Extract xlsx files from password-protected zip.
    Returns list of extracted xlsx file paths.
    """
    os.makedirs(extract_to, exist_ok=True)
    extracted = []
    MAX_ENTRY_SIZE = 100 * 1024 * 1024    # 100 MB per entry
    MAX_TOTAL_SIZE = 500 * 1024 * 1024    # 500 MB cumulative

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            total_extracted_size = 0
            for name in zf.namelist():
                if name.lower().endswith(('.xlsx', '.xls')):
                    # Zip Slip guard
                    full_path = os.path.realpath(os.path.join(extract_to, name))
                    if not full_path.startswith(os.path.realpath(extract_to) + os.sep):
                        logger.error(f"Zip Slip blocked: {name}")
                        continue
                    # Reject entries over 100 MB (zip bomb guard)
                    info = zf.getinfo(name)
                    if info.file_size > MAX_ENTRY_SIZE:
                        logger.warning(f"Zip entry too large ({info.file_size} bytes), skipping: {name}")
                        continue
                    # Cumulative size guard
                    if total_extracted_size + info.file_size > MAX_TOTAL_SIZE:
                        logger.warning(f"Cumulative extraction limit ({MAX_TOTAL_SIZE} bytes) reached, stopping: {name}")
                        break
                    # Try cp866 first (7-Zip default for Cyrillic), fall back to utf-8
                    success = False
                    for encoding in ('cp866', 'utf-8'):
                        try:
                            zf.extract(name, extract_to, pwd=password.encode(encoding))
                            success = True
                            break
                        except RuntimeError:
                            continue
                    if not success:
                        continue
                    total_extracted_size += info.file_size
                    extracted.append(full_path)
                    logger.info(f"Extracted: {name}")

        if not extracted:
            # Maybe there are xlsx inside but also PDFs — log what's in there
            with zipfile.ZipFile(zip_path, 'r') as zf:
                all_files = zf.namelist()
                logger.info(f"Zip extraction failed (wrong password?), contents: {all_files}")

    except RuntimeError as e:
        logger.error(f"Failed to extract {zip_path}: {e} (wrong password?)")
    except Exception as e:
        logger.error(f"Error extracting {zip_path}: {e}")

    return extracted


def try_passwords(zip_path: str, passwords: list[str], extract_to: str) -> list[str]:
    """Try multiple passwords against a zip file. Returns extracted xlsx paths."""
    # Check if zip contains any xlsx/xls files at all
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            has_xlsx = any(n.lower().endswith(('.xlsx', '.xls')) for n in zf.namelist())
        if not has_xlsx:
            logger.warning(f"Zip {os.path.basename(zip_path)} contains no xlsx/xls files — skipping password attempts")
            audit_logger.info(f"ZIP_EXTRACT zip={os.path.basename(zip_path)} result=NO_XLSX")
            return []
    except Exception as e:
        logger.error(f"Cannot read zip {zip_path}: {e}")
        return []

    for pwd_idx, pwd in enumerate(passwords, 1):
        result = unzip_with_password(zip_path, pwd, extract_to)
        if result:
            audit_logger.info(f"ZIP_EXTRACT zip={os.path.basename(zip_path)} passwords_tried={pwd_idx}/{len(passwords)} result=SUCCESS")
            return result

    audit_logger.info(f"ZIP_EXTRACT zip={os.path.basename(zip_path)} passwords_tried={len(passwords)}/{len(passwords)} result=FAILED")
    logger.error(f"All passwords failed for {zip_path}")
    return []
