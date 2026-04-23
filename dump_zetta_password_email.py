"""Print body of Zetta monthly password emails so we can fix the regex."""
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
print(f"Found {len(uids)} email(s)\n")

for uid in uids[-1:]:  # just the most recent one
    _, data = m.uid('FETCH', uid, '(RFC822)')
    msg = email.message_from_bytes(data[0][1])
    print(f"Subject: {msg.get('Subject')}")
    print(f"Date: {msg.get('Date')}")
    print("-" * 60)
    for part in msg.walk():
        ct = part.get_content_type()
        if ct in ('text/plain', 'text/html'):
            charset = part.get_content_charset() or 'utf-8'
            body = part.get_payload(decode=True).decode(charset, errors='replace')
            body = re.sub(r'<[^>]+>', ' ', body)  # strip html tags
            print(f"[{ct}]\n{body[:1000]}")
            print("-" * 60)

m.logout()
