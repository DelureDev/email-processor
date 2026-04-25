#!/usr/bin/env python3
"""One-off: build today's records_YYYY-MM-DD.csv LOCALLY from master.xlsx.

For when the CIFS share is fully dead but you need a correct daily CSV
for 1C import. Writes to the current directory with BOM + 12-column
header. When CIFS recovers, copy the result up manually:

    python3 build_local_daily_csv.py
    # → writes records_2026-04-24.csv to cwd
    cp records_2026-04-24.csv /mnt/storage/

No network ops at all — master.xlsx is local, output is local.
"""
import csv
import os
import sys
from datetime import datetime

import pandas as pd

from main import load_config
from parsers.utils import norm_date_pad
from writer import COLUMNS, _safe
from clinic_matcher import clinic_id_for_name


def main() -> int:
    config = load_config('config.yaml')
    master_path = config.get('output', {}).get('master_file', './output/master.xlsx')
    if not os.path.isfile(master_path):
        print(f"master.xlsx not found: {master_path}", file=sys.stderr)
        return 2

    df = pd.read_excel(master_path, dtype=str).fillna('')
    if 'Дата обработки' not in df.columns:
        print("master.xlsx has no 'Дата обработки' column", file=sys.stderr)
        return 2

    today = datetime.now().strftime('%d.%m.%Y')
    normed = df['Дата обработки'].map(lambda s: norm_date_pad(str(s)))
    todays = df[normed == today].to_dict('records')

    if not todays:
        print(f"no records with Дата обработки={today}", file=sys.stderr)
        return 1

    # master.xlsx doesn't persist ID Клиники — repopulate from clinics.yaml
    # so the resulting CSV is 1C-ready (otherwise that column is all blank).
    for r in todays:
        r['ID Клиники'] = clinic_id_for_name(r.get('Клиника', ''))

    csv_columns = []
    for c in COLUMNS:
        csv_columns.append(c)
        if c == 'Клиника':
            csv_columns.append('ID Клиники')

    date_str = datetime.now().strftime('%Y-%m-%d')
    out = f'records_{date_str}.csv'

    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=csv_columns, extrasaction='ignore',
                           delimiter=';', lineterminator='\r\n')
        w.writeheader()
        for record in todays:
            w.writerow({k: _safe(v) for k, v in record.items()})

    print(f"Wrote {len(todays)} records to ./{out}")
    print(f"When CIFS is alive: cp {out} /mnt/storage/")
    return 0


if __name__ == '__main__':
    sys.exit(main())
