#!/usr/bin/env python3
"""One-off: resend the daily email report for records written today.

Use case: a cron run wrote master.xlsx but never reached send_report()
(e.g. it hung on a CIFS syscall before v1.10.14). Reads today's rows
from master.xlsx by Дата обработки, builds a stats dict, reuses the
existing notifier to send the report.

Run once, then delete (or keep under scripts/ for next incident):
    cd /home/adminos/email-processor && python3 resend_today.py
"""
import sys
from datetime import datetime

import pandas as pd

from main import load_config, setup_logging, make_stats
from parsers.utils import norm_date_pad
from notifier import send_report


def main() -> int:
    config = load_config('config.yaml')
    setup_logging(config)

    master_path = config.get('output', {}).get('master_file', './output/master.xlsx')
    df = pd.read_excel(master_path, dtype=str).fillna('')

    if 'Дата обработки' not in df.columns:
        print(f"master.xlsx has no 'Дата обработки' column — cannot filter by date.", file=sys.stderr)
        return 2

    today = datetime.now().strftime('%d.%m.%Y')
    normed = df['Дата обработки'].map(lambda s: norm_date_pad(str(s)))
    todays = df[normed == today].to_dict('records')

    if not todays:
        print(f"No records with Дата обработки={today}. Nothing to send.")
        return 1

    stats = make_stats()
    stats['run_start'] = datetime.now()
    stats['new_records'] = todays
    stats['total_records'] = len(todays)
    stats['files_processed'] = len({r.get('Источник файла', '') for r in todays if r.get('Источник файла')})
    stats['master_path'] = master_path
    for r in todays:
        company = r.get('Страховая компания') or 'Неизвестно'
        stats['by_company'][company] += 1

    send_report(config, stats)

    if stats.get('smtp_status') == 'OK':
        print(f"Report sent: {len(todays)} records dated {today}.")
        return 0
    print(f"send_report returned without SMTP success. smtp_status={stats.get('smtp_status')}, "
          f"errors={stats.get('errors')}", file=sys.stderr)
    return 3


if __name__ == '__main__':
    sys.exit(main())
