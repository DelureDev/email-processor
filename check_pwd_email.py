#!/usr/bin/env python3
"""One-time script: fetch and debug Zetta monthly password email."""
import imaplib, yaml, os, email, re
from email.header import decode_header

cfg = yaml.safe_load(open('config.yaml'))
m = imaplib.IMAP4_SSL(cfg['imap']['server'])
pwd = os.environ.get('IMAP_PASSWORD', cfg['imap']['password'])
m.login(cfg['imap']['username'], pwd)
m.select('INBOX')

s, msgs = m.uid('SEARCH', None, '(SINCE 20-Feb-2026 FROM "parollpu@zettains.ru")')
if s != 'OK' or not msgs[0]:
    print("No password emails found")
    m.logout()
    exit()

for uid in msgs[0].split():
    s, data = m.uid('FETCH', uid, '(RFC822)')
    if s != 'OK':
        continue
    msg = email.message_from_bytes(data[0][1])
    subj = str(msg.get('Subject', ''))
    date = msg.get('Date', '')
    print(f"=== UID={uid.decode()} Date={date}")
    print(f"Subject: {subj}")

    # Extract all text parts
    for part in msg.walk():
        ct = part.get_content_type()
        if ct in ('text/plain', 'text/html'):
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or 'utf-8'
            try:
                body = payload.decode(charset)
            except Exception:
                body = payload.decode('utf-8', errors='replace')
            print(f"\n--- {ct} (first 1000 chars) ---")
            print(body[:1000])

            # Try the extraction regex
            text = re.sub(r'<br\s*/?>', '\n', body)
            text = re.sub(r'<[^>]+>', '', text)
            text = text.replace('&quot;', '"').replace('&amp;', '&').replace('&nbsp;', ' ')
            period = re.search(r'в период с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})', text)
            if period:
                print(f"\nPeriod found: {period.group(1)} - {period.group(2)}")
                lines = text.split('\n')
                found = False
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if 'в период с' in line:
                        found = True
                        continue
                    if found:
                        print(f"Next non-empty line after period: [{line}] len={len(line)} repr={repr(line)}")
                        match = re.match(r'^[A-Za-z0-9!@#$%^&*()_+\-=]+$', line)
                        print(f"Regex match: {bool(match)}")
                        break
            else:
                print("No period pattern found in text")

m.logout()
