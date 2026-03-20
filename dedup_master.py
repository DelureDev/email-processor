#!/usr/bin/env python3
"""One-time: remove duplicate rows from master.xlsx and master.csv."""
import openpyxl
import csv
import os

# 1. Dedup master.xlsx
path = './output/master.xlsx'
wb = openpyxl.load_workbook(path)
ws = wb['Данные']
seen = set()
dupes = []
for r in range(2, ws.max_row + 1):
    key = tuple(str(ws.cell(row=r, column=c).value or '') for c in range(1, 12))
    if key in seen:
        dupes.append(r)
    seen.add(key)
for r in reversed(dupes):
    ws.delete_rows(r, 1)
wb.save(path)
wb.close()
print(f'master.xlsx: removed {len(dupes)} duplicates, {ws.max_row - 1} rows remain')

# 2. Dedup master.csv
csv_path = './output/master.csv'
if os.path.exists(csv_path):
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f, delimiter=';'))
    header = rows[0] if rows else []
    seen = set()
    kept = [header]
    removed = 0
    for row in rows[1:]:
        key = tuple(row)
        if key in seen:
            removed += 1
        else:
            seen.add(key)
            kept.append(row)
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';', lineterminator='\r\n')
        w.writerows(kept)
    print(f'master.csv: removed {removed} duplicates, {len(kept) - 1} rows remain')
