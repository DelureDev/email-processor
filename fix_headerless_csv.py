#!/usr/bin/env python3
"""One-off: prepend UTF-8 BOM + column header to a headerless network CSV
that was produced by the v1.10.15/v1.10.16 code path when the file existed
as zero bytes (e.g. after `touch` workaround on a flaky CIFS mount).

Minimises CIFS ops: one read of the original content, one write of
BOM + header + content. Wraps both in a daemon-thread timeout and a
force-exit escape hatch so a hung CIFS mount doesn't pin the shell.

Idempotent — detects an existing BOM and exits 0 without touching the file.

    cd /home/adminos/email-processor && python3 fix_headerless_csv.py /mnt/storage/records_2026-04-24.csv
"""
import os
import sys
import threading

from writer import COLUMNS
from main import _force_exit_if_stuck_threads

BOM = '﻿'
DELIMITER = ';'
LINE = '\r\n'
OP_TIMEOUT_SEC = 30


def build_header() -> str:
    cols = []
    for c in COLUMNS:
        cols.append(c)
        if c == 'Клиника':
            cols.append('ID Клиники')
    return DELIMITER.join(cols)


def _run_with_timeout(fn, name: str) -> dict:
    """Run fn() in a daemon thread with OP_TIMEOUT_SEC cap.
    Returns a dict with {ok: True} / {error: ...} / {timeout: True}."""
    result: dict = {}

    def _work():
        try:
            result['value'] = fn()
            result['ok'] = True
        except Exception as e:
            result['error'] = e

    t = threading.Thread(target=_work, daemon=True, name=name)
    t.start()
    t.join(timeout=OP_TIMEOUT_SEC)
    if t.is_alive():
        result['timeout'] = True
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <csv_path>", file=sys.stderr)
        return 2

    path = sys.argv[1]

    # Do NOT probe with os.path.isfile() — it's a blocking syscall on CIFS
    # that can hang indefinitely when the mount is half-dead, defeating all
    # our per-op timeouts. Instead, let _read_head fail naturally; a missing
    # file surfaces as FileNotFoundError inside the timeout-wrapped thread.
    sniff = _run_with_timeout(lambda: _read_head(path), name='bom-sniff')
    if sniff.get('timeout'):
        print(f"timeout reading first bytes of {path} — CIFS hung", file=sys.stderr)
        return 3
    if 'error' in sniff:
        if isinstance(sniff['error'], FileNotFoundError):
            print(f"not a file: {path}", file=sys.stderr)
            return 2
        print(f"error reading {path}: {sniff['error']}", file=sys.stderr)
        return 3
    head = sniff['value']
    if head.startswith(b'\xef\xbb\xbf'):
        print(f"already has UTF-8 BOM — leaving alone: {path}")
        return 0

    header = build_header()
    prefix = (BOM + header + LINE).encode('utf-8')

    # One read of the whole file
    read_res = _run_with_timeout(lambda: _read_all(path), name='csv-read')
    if read_res.get('timeout'):
        print(f"timeout reading full {path} — CIFS hung", file=sys.stderr)
        return 3
    if 'error' in read_res:
        print(f"error reading {path}: {read_res['error']}", file=sys.stderr)
        return 3
    original = read_res['value']

    new_content = prefix + original

    # One write of BOM + header + original content
    write_res = _run_with_timeout(lambda: _write_all(path, new_content), name='csv-write')
    if write_res.get('timeout'):
        print(f"timeout writing {path} — CIFS hung, content unchanged", file=sys.stderr)
        return 3
    if 'error' in write_res:
        print(f"error writing {path}: {write_res['error']}", file=sys.stderr)
        return 3

    print(f"Prepended BOM + header to {path} ({len(original)} -> {len(new_content)} bytes)")
    return 0


def _read_head(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read(4)


def _read_all(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def _write_all(path: str, content: bytes) -> None:
    with open(path, 'wb') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())


if __name__ == '__main__':
    code = main()
    _force_exit_if_stuck_threads(code)
    sys.exit(code)
