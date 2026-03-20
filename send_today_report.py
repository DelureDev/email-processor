#!/usr/bin/env python3
"""One-time: send today's report and export CSV from existing master data."""
import pandas as pd
from main import load_config, setup_logging, _export_to_network, make_stats
from main import _attach_monthly_if_last_day
from notifier import send_report
from parsers.utils import norm_date_pad
from collections import defaultdict

config = load_config()
setup_logging(config)

# Read today's records from backup (cleanup_rerun.py removed them from master)
master = config.get('output', {}).get('master_file', './output/master.xlsx')
backup = master.replace('.xlsx', '_pre_rerun.xlsx')
import os
source = backup if os.path.exists(backup) else master
df = pd.read_excel(source, dtype=str).fillna('')
today_mask = df['Дата обработки'].map(lambda s: norm_date_pad(str(s))) == '20.03.2026'
today_df = df[today_mask]
records = today_df.to_dict('records')

print(f"Found {len(records)} records for 20.03.2026 (from {os.path.basename(source)})")

# Restore records to master if they were removed
if source == backup and records:
    from writer import write_batch_to_master
    batch = [(records, 'restored_from_backup')]
    write_batch_to_master(batch, master)
    print(f"Restored {len(records)} records to master.xlsx")

if not records:
    print("No records found, nothing to send.")
    exit(0)

# Build stats as if pipeline just ran
stats = make_stats()
stats['total_records'] = len(records)
stats['files_processed'] = len(set(r.get('Источник файла', '') for r in records))
stats['new_records'] = records
stats['master_path'] = master
for r in records:
    company = r.get('Страховая компания', 'Неизвестно')
    stats['by_company'][company] += 1

# Send report
_attach_monthly_if_last_day(config, stats)
send_report(config, stats)
print("Email report sent!")

# Export to network share
_export_to_network(config, stats)
print("CSV exported to network share!")
