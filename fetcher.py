"""
IMAP Fetcher — connects to Yandex, downloads .xlsx attachments
"""
import imaplib
import email
import email.utils
import ssl
import time
from email.header import decode_header
import os
import re
import json
import tempfile
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# English month names for IMAP SEARCH (strftime %b is locale-dependent)
_IMAP_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _imap_date(dt) -> str:
    """Format date for IMAP SEARCH (always English month names)."""
    return f"{dt.day:02d}-{_IMAP_MONTHS[dt.month - 1]}-{dt.year}"


def _extract_email_addr(from_header: str) -> str:
    """Extract just the email address from a From header (strips display name)."""
    _, addr = email.utils.parseaddr(from_header)
    return addr.lower()


def decode_mime_header(header_value):
    """Decode MIME encoded header (supports Russian encodings)."""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return " ".join(result)


def _extract_monthly_pwd_from_msg(msg) -> dict | None:
    """Extract Zetta monthly password from all text parts of an email message."""
    from zetta_handler import extract_monthly_password
    for part in msg.walk():
        ct = part.get_content_type()
        if ct in ('text/plain', 'text/html'):
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace')
            result = extract_monthly_password(body)
            if result:
                return result
    return None


class IMAPFetcher:
    def __init__(self, config: dict, dry_run: bool = False):
        self.server = config['imap']['server']
        self.port = config['imap']['port']
        self.username = config['imap']['username']
        self.password = config['imap']['password']
        self.folder = config['imap']['folder']
        self.allowed_senders = config['imap'].get('allowed_senders', [])
        self.subject_keywords = config['imap'].get('subject_keywords', [])
        self.temp_folder = config['processing']['temp_folder']
        self.processed_file = config['processing']['processed_ids_file']
        self.dry_run = dry_run
        self.processed_ids = self._load_processed_ids()

        os.makedirs(self.temp_folder, exist_ok=True)

    def _load_processed_ids(self) -> set:
        if os.path.exists(self.processed_file):
            with open(self.processed_file, 'r') as f:
                return set(json.load(f))
        return set()

    def _save_processed_ids(self):
        # Cap to last 5000 IDs to prevent unbounded growth
        ids_list = list(self.processed_ids)
        if len(ids_list) > 5000:
            ids_list = ids_list[-5000:]
            self.processed_ids = set(ids_list)
        with open(self.processed_file, 'w') as f:
            json.dump(ids_list, f, indent=2)

    def connect(self, retries: int = 3, delay: float = 5.0):
        """Connect to Yandex IMAP. Retries up to `retries` times on failure."""
        logger.info(f"Connecting to {self.server}:{self.port}...")
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                self.mail = imaplib.IMAP4_SSL(self.server, self.port, ssl_context=ssl.create_default_context())
                self.mail.login(self.username, self.password)
                self.mail.select(self.folder)
                logger.info("Connected successfully")
                return
            except Exception as e:
                last_exc = e
                if attempt < retries:
                    logger.warning(f"Connection attempt {attempt} failed: {e} — retrying in {delay}s")
                    time.sleep(delay)
        raise ConnectionError(f"Failed to connect after {retries} attempts: {last_exc}")

    def disconnect(self):
        try:
            self.mail.logout()
        except Exception:
            pass

    def _matches_filter(self, msg) -> bool:
        """Check if email matches sender/subject filters."""
        sender = decode_mime_header(msg.get('From', ''))
        subject = decode_mime_header(msg.get('Subject', ''))

        if self.allowed_senders:
            sender_addr = _extract_email_addr(sender)
            if not any(s.lower() in sender_addr for s in self.allowed_senders):
                return False

        if self.subject_keywords:
            subject_lower = subject.lower()
            if not any(kw.lower() in subject_lower for kw in self.subject_keywords):
                return False

        return True

    def fetch_attachments(self, days_back: int = 7) -> list[dict]:
        """
        Fetch .xlsx attachments from recent emails.
        Handles Zetta password-protected zips automatically.
        Returns list of dicts: {filepath, sender, subject, date, message_id}
        """
        from zetta_handler import is_zetta_email, is_sber_email, is_password_zip_email, is_zetta_monthly_password_email, extract_password_from_body, extract_password_from_html, extract_monthly_password, try_passwords

        results = []
        zetta_zips = []       # [(filepath, message_info), ...]
        zetta_passwords = []  # passwords found in Zetta emails (monthly first, then per-email)

        # Pre-scan: search for Zetta monthly password (go back 35 days to catch 1st-of-month email)
        pwd_since = _imap_date(datetime.now() - timedelta(days=35))
        status, pwd_msgs = self.mail.search(None, f'(SINCE {pwd_since} FROM "parollpu@zettains.ru")')
        if status == 'OK' and pwd_msgs[0]:
            for msg_id in pwd_msgs[0].split():
                try:
                    msg_data = None
                    for attempt in range(1, 4):
                        st, data = self.mail.fetch(msg_id, '(RFC822)')
                        if st == 'OK':
                            msg_data = data
                            break
                        time.sleep(2)
                    if msg_data is None:
                        continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    monthly = _extract_monthly_pwd_from_msg(msg)
                    if monthly and monthly['password'] not in zetta_passwords:
                        zetta_passwords.insert(0, monthly['password'])
                        logger.info(f"Got Zetta monthly password (valid {monthly['valid_from']} - {monthly['valid_to']})")
                except Exception as e:
                    logger.debug(f"Error reading password email: {e}")

        # Main search for recent emails
        since_date = _imap_date(datetime.now() - timedelta(days=days_back))
        status, messages = self.mail.search(None, f'(SINCE {since_date})')

        if status != 'OK':
            logger.error("Failed to search emails")
            return []

        msg_ids = messages[0].split()
        logger.info(f"Found {len(msg_ids)} emails in last {days_back} days")

        # First pass: collect all attachments and passwords
        for msg_id in msg_ids:
            msg_id_str = msg_id.decode()

            msg_data = None
            for attempt in range(1, 4):
                status, data = self.mail.fetch(msg_id, '(RFC822)')
                if status == 'OK':
                    msg_data = data
                    break
                logger.warning(f"Fetch attempt {attempt} failed for msg {msg_id_str}, retrying...")
                time.sleep(2)
            if msg_data is None:
                logger.error(f"Skipping message {msg_id_str} after 3 failed fetch attempts")
                continue

            msg = email.message_from_bytes(msg_data[0][1])
            message_id = msg.get('Message-ID', msg_id_str)

            if message_id in self.processed_ids:
                continue

            if not self._matches_filter(msg):
                # Still check for Zetta monthly password emails even if they don't match subject filter
                sender_addr = _extract_email_addr(decode_mime_header(msg.get('From', '')))
                if is_zetta_monthly_password_email(sender_addr):
                    monthly = _extract_monthly_pwd_from_msg(msg)
                    if monthly and monthly['password'] not in zetta_passwords:
                        zetta_passwords.insert(0, monthly['password'])
                        logger.info(f"Got Zetta monthly password (valid {monthly['valid_from']} - {monthly['valid_to']})")
                    self.processed_ids.add(message_id)
                continue

            sender_raw = decode_mime_header(msg.get('From', ''))
            sender = _extract_email_addr(sender_raw)
            subject = decode_mime_header(msg.get('Subject', ''))
            date = msg.get('Date', '')

            # If password-zip email (Zetta or Sber) — check for passwords in body
            if is_password_zip_email(sender):
                # First check if it's a monthly password email
                if is_zetta_monthly_password_email(sender):
                    monthly = _extract_monthly_pwd_from_msg(msg)
                    if monthly and monthly['password'] not in zetta_passwords:
                        zetta_passwords.insert(0, monthly['password'])
                        logger.info(f"Got Zetta monthly password (valid {monthly['valid_from']} - {monthly['valid_to']})")
                else:
                    # Per-email password (pulse.letter or Sber)
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct == 'text/plain':
                            payload = part.get_payload(decode=True)
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='replace')
                            pwd = extract_password_from_body(body)
                            if pwd and pwd not in zetta_passwords:
                                zetta_passwords.append(pwd)
                        elif ct == 'text/html':
                            payload = part.get_payload(decode=True)
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='replace')
                            pwd = extract_password_from_html(body)
                            if pwd and pwd not in zetta_passwords:
                                zetta_passwords.append(pwd)

            # Walk through parts looking for attachments
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue

                filename = part.get_filename()
                if not filename:
                    continue

                filename = decode_mime_header(filename)
                safe_name = f"{msg_id_str}_{re.sub(r'[\\/:*?\"<>|]', '_', os.path.basename(filename))}"
                filepath = os.path.join(self.temp_folder, safe_name)

                try:
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    # Reject attachments over 50 MB
                    if len(payload) > 50 * 1024 * 1024:
                        logger.warning(f"Attachment too large ({len(payload)} bytes), skipping: {filename}")
                        continue
                    with open(filepath, 'wb') as f:
                        f.write(payload)
                except OSError as e:
                    logger.error(f"Failed to save attachment {safe_name}: {e}")
                    continue

                if filename.lower().endswith('.zip') and is_password_zip_email(sender):
                    # Password-protected zip (Zetta or Sber) — save for second pass
                    zetta_zips.append((filepath, {
                        'filename': filename,
                        'sender': sender,
                        'subject': subject,
                        'date': date,
                        'message_id': message_id,
                    }))
                    logger.info(f"Downloaded Zetta zip: {filename}")

                elif filename.lower().endswith(('.xlsx', '.xls')):
                    logger.info(f"Downloaded: {filename} from '{subject}'")
                    results.append({
                        'filepath': filepath,
                        'filename': filename,
                        'sender': sender,
                        'subject': subject,
                        'date': date,
                        'message_id': message_id,
                    })

            # Mark as processed (Message-ID only — IMAP sequence numbers are not stable)
            self.processed_ids.add(message_id)

        # Second pass: extract Zetta zips using collected passwords
        if zetta_zips and zetta_passwords:
            logger.info(f"Processing {len(zetta_zips)} Zetta zips with {len(zetta_passwords)} passwords")
            for zip_path, info in zetta_zips:
                extract_dir = tempfile.mkdtemp(dir=self.temp_folder, prefix='zetta_')
                xlsx_files = try_passwords(zip_path, zetta_passwords, extract_dir)
                for xlsx_path in xlsx_files:
                    results.append({
                        'filepath': xlsx_path,
                        'filename': os.path.basename(xlsx_path),
                        'sender': info['sender'],
                        'subject': info['subject'],
                        'date': info['date'],
                        'message_id': info['message_id'],
                        '_extract_dir': extract_dir,
                    })
                # Clean up zip
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
        elif zetta_zips and not zetta_passwords:
            logger.warning(f"Found {len(zetta_zips)} Zetta zips but no passwords!")

        if not self.dry_run:
            self._save_processed_ids()
        else:
            logger.info("Dry-run: not saving processed IDs")
        logger.info(f"Downloaded {len(results)} new attachments")
        return results
