#!/usr/bin/env python3
"""One-time script: check where Zetta password emails ended up."""
import imaplib, yaml, os

cfg = yaml.safe_load(open('config.yaml'))
m = imaplib.IMAP4_SSL(cfg['imap']['server'])
pwd = os.environ.get('IMAP_PASSWORD', cfg['imap']['password'])
m.login(cfg['imap']['username'], pwd)
for folder in ['INBOX', 'Обработанные', 'Spam', 'Trash', 'Junk']:
    try:
        m.select(folder)
        s, msgs = m.uid('SEARCH', None, '(SINCE 20-Feb-2026 FROM "parollpu@zettains.ru")')
        count = len(msgs[0].split()) if s == 'OK' and msgs[0] else 0
        print(f'{folder}: {count} emails from parollpu')
    except Exception as e:
        print(f'{folder}: error - {e}')
m.logout()
