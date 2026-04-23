"""Print body of Zetta monthly password emails and test the extraction regex."""
import imaplib
import ssl
import os
import email
import re
import yaml

cfg = yaml.safe_load(open('config.yaml'))
imap_cfg = cfg['imap']
pwd = os.environ.get('IMAP_PASSWORD', imap_cfg.get('password', ''))

ctx = ssl.create_default_context()
m = imaplib.IMAP4_SSL(imap_cfg['server'], imap_cfg.get('port', 993), ssl_context=ctx)
m.login(imap_cfg['username'], pwd)
m.select('INBOX')

_, msgs = m.uid('SEARCH', None, 'FROM "parollpu@zettains.ru"')
uids = msgs[0].split() if msgs[0] else []
print(f"Found {len(uids)} email(s): {[u.decode() for u in uids]}\n")

from zetta_handler import extract_monthly_password

for uid in reversed(uids):  # most recent first
    uid_str = uid.decode()
    print(f"--- Fetching UID {uid_str} ---")
    try:
        _, data = m.uid('FETCH', uid_str, 'RFC822')
        if not data or data[0] is None:
            print(f"  FETCH returned no data, skipping")
            continue
        msg = email.message_from_bytes(data[0][1])
        print(f"Subject: {msg.get('Subject')}")
        print(f"Date: {msg.get('Date')}")
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ('text/plain', 'text/html'):
                charset = part.get_content_charset() or 'utf-8'
                raw_body = part.get_payload(decode=True).decode(charset, errors='replace')
                stripped = re.sub(r'<[^>]+>', ' ', raw_body)
                print(f"[{ct}]\n{stripped[:800]}")
                print("-" * 60)
                result = extract_monthly_password(raw_body)
                if result:
                    print(f"[EXTRACTION OK] password={result['password']!r}  valid {result['valid_from']} - {result['valid_to']}")
                else:
                    print("[EXTRACTION FAILED] extract_monthly_password returned None")
        print("=" * 60)
        break  # stop after first successful fetch
    except Exception as e:
        print(f"  ERROR: {e}")
        continue

m.logout()
