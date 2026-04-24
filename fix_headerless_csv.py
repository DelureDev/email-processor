#!/usr/bin/env python3
"""One-off: prepend UTF-8 BOM + column header to a headerless network CSV
that was produced by the v1.10.15/v1.10.16 code path when the file existed
as zero bytes (e.g. after `touch` workaround on a flaky CIFS mount).

Writes atomically via tmp + rename so a concurrent cron run can't see the
file half-repaired. Safe to run multiple times — detects existing header.

    cd /home/adminos/email-processor && python3 fix_headerless_csv.py /mnt/storage/records_2026-04-24.csv
"""
import os
import sys
import tempfile

from writer import COLUMNS

BOM = '﻿'
DELIMITER = ';'
LINE = '\r\n'


def build_header() -> str:
    cols = []
    for c in COLUMNS:
        cols.append(c)
        if c == 'Клиника':
            cols.append('ID Клиники')
    return DELIMITER.join(cols)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <csv_path>", file=sys.stderr)
        return 2

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"not a file: {path}", file=sys.stderr)
        return 2

    header = build_header()

    with open(path, 'rb') as f:
        head = f.read(4)

    if head.startswith(b'\xef\xbb\xbf'):
        print(f"already has UTF-8 BOM — leaving alone: {path}")
        return 0

    # Not BOM-prefixed. Prepend BOM + header row, keep the rest.
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix='.fix_headerless_', suffix='.csv',
        dir=os.path.dirname(path) or '.'
    )
    try:
        with os.fdopen(tmp_fd, 'wb') as out:
            out.write((BOM + header + LINE).encode('utf-8'))
            with open(path, 'rb') as src:
                while True:
                    chunk = src.read(64 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    print(f"Prepended BOM + header to {path}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
