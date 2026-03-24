#!/usr/bin/env python3
"""One-time script: re-export today's records to network share."""
from main import _export_to_network
import yaml
import pandas as pd

cfg = yaml.safe_load(open('config.yaml'))
df = pd.read_excel('./output/master.xlsx', dtype=str)
today_records = df[df['Дата обработки'] == '24.03.2026'].to_dict('records')
print(f'Found {len(today_records)} records for today')
stats = {'new_records': today_records, 'errors': []}
_export_to_network(cfg, stats)
print('Done. Errors:', stats['errors'] or 'none')
