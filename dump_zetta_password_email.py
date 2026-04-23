"""Print body of Zetta monthly password emails and test the extraction regex."""
import imaplib
import ssl
import os
import email
import re
import time
import yaml
from datetime import datetime, timedelta

cfg = yaml.safe_load(open('config.yaml'))
imap_cfg = cfg['imap']
pwd = os.environ.get('IMAP_PASSWORD', imap_cfg.get('password', ''))

ctx = ssl.create_default_context()
m = imaplib.IMAP4_SSL(imap_cfg['server'], imap_cfg.get('port', 993), ssl_context=ctx)
m.login(imap_cfg['username'], pwd)

from fetcher import imap_utf7_encode
from zetta_handler import extract_monthly_password

folders_to_check = ['INBOX']
processed = imap_cfg.get('processed_folder', '')
if processed:
    folders_to_check.append(processed)

since_date = (datetime.now() - timedelta(days=35)).strftime('%d-%b-%Y')

found_any = False
for folder in folders_to_check:
    print(f"\n=== Searching in: {folder} ===")
    encoded = imap_utf7_encode(folder)
    typ, _ = m.select(encoded)
    if typ != 'OK':
        print(f"  Could not select folder: {typ}")
        continue

    # Retry SEARCH up to 3 times — some servers return [UNAVAILABLE] transiently
    uids = []
    for attempt in range(1, 4):
        typ, msgs = m.uid('SEARCH', None, f'SINCE {since_date} FROM "parollpu@zettains.ru"')
        if typ == 'OK':
            uids = msgs[0].split() if msgs[0] else []
            break
        print(f"  SEARCH attempt {attempt} failed: {msgs[0]}")
        if attempt < 3:
            time.sleep(3)
    else:
        print("  SEARCH failed after 3 attempts, skipping folder")
        continue

    print(f"  Found {len(uids)} email(s) since {since_date}")
    if not uids:
        continue

    for uid in reversed(uids):
        uid_str = uid.decode()
        print(f"\n  Fetching UID {uid_str} ...")
        try:
            typ2, data = m.uid('FETCH', uid_str, 'RFC822')
            if typ2 != 'OK' or not data or data[0] is None:
                print(f"  FETCH failed: {typ2}")
                continue
            msg = email.message_from_bytes(data[0][1])
            print(f"  Subject: {msg.get('Subject')}")
            print(f"  Date:    {msg.get('Date')}")
            for part in msg.walk():
                ct = part.get_content_type()
                if ct in ('text/plain', 'text/html'):
                    charset = part.get_content_charset() or 'utf-8'
                    raw_body = part.get_payload(decode=True).decode(charset, errors='replace')
                    stripped = re.sub(r'<[^>]+>', ' ', raw_body)
                    print(f"  [{ct}]\n{stripped[:600]}")
                    print("  " + "-" * 56)
                    result = extract_monthly_password(raw_body)
                    if result:
                        print(f"  [EXTRACTION OK] password={result['password']!r}  valid {result['valid_from']} - {result['valid_to']}")
                        found_any = True
                    else:
                        print("  [EXTRACTION FAILED] extract_monthly_password returned None")
            break
        except Exception as e:
            print(f"  ERROR fetching UID {uid_str}: {e}")
            continue

m.logout()
if not found_any:
    print("\n[RESULT] No password extracted from any folder.")
