"""Diagnostic: check which folders contain the Zetta monthly password email."""
import imaplib
import ssl
import os
import yaml

cfg = yaml.safe_load(open('config.yaml'))
imap_cfg = cfg['imap']
pwd = os.environ.get('IMAP_PASSWORD', imap_cfg.get('password', ''))

ctx = ssl.create_default_context()
m = imaplib.IMAP4_SSL(imap_cfg['server'], imap_cfg.get('port', 993), ssl_context=ctx)
m.login(imap_cfg['username'], pwd)

folders_to_check = ['INBOX', imap_cfg.get('processed_folder', 'Обработанные')]

for folder in folders_to_check:
    try:
        status, _ = m.select(f'"{folder}"')
        if status != 'OK':
            print(f"{folder}: could not select")
            continue
        _, msgs = m.uid('SEARCH', None, 'FROM "parollpu@zettains.ru"')
        count = len(msgs[0].split()) if msgs[0] else 0
        print(f"{folder}: {count} email(s) from parollpu@zettains.ru")
    except Exception as e:
        print(f"{folder}: error — {e}")

m.logout()
