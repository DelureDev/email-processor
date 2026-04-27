#!/usr/bin/env python3
"""Standalone SMB connection test.

Loads config.yaml the same way main.py does (so ${SMB_PASSWORD} and any other
env placeholders expand identically), then:
  1. lists the configured share folder        — proves auth + path
  2. writes a tiny _conntest_<ts>.txt          — proves write
  3. reads it back and compares                — proves read
  4. deletes it                                — leaves no trace

Usage on VM:
    git pull
    set -a; source .env; set +a   # so SMB_PASSWORD is in env
    python3 test_smb_conn.py

Exit code 0 on success, 1 on any failure. Safe to run anytime — does not
touch master.xlsx, processed_ids.db, IMAP, or SMTP.
"""
import os
import sys
import threading
import time
import uuid

# Reuse main.py's config loader so env-var expansion + validation are identical
from main import load_config

TIMEOUT_SEC = 20


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"  OK: {msg}")


def main() -> None:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else 'config.yaml'
    print(f"Loading {cfg_path} ...")
    try:
        config = load_config(cfg_path)
    except ValueError as e:
        _fail(f"config load: {e}")
    except FileNotFoundError:
        _fail(f"config file not found: {cfg_path}")

    out = config.get('output', {}) or {}
    folder = (out.get('csv_export_folder') or '').strip()
    creds = out.get('smb_credentials', {}) or {}
    username = (creds.get('username') or '').strip()
    password = (creds.get('password') or '').strip()
    domain = (creds.get('domain') or '').strip()

    if not folder:
        _fail("output.csv_export_folder is empty in config.yaml")
    if not folder.startswith('\\\\') and not folder.startswith('//'):
        _fail(f"csv_export_folder is not a UNC path: {folder!r}")
    if not username or not password:
        _fail("output.smb_credentials.username/password missing or empty")

    user_spec = f"{domain}\\{username}" if domain else username
    base = folder.replace('/', '\\').rstrip('\\')

    # Print what we're about to use — but never print the password.
    print(f"  share : {base}")
    print(f"  user  : {user_spec}")
    print(f"  pwd   : ({len(password)} chars)")

    try:
        import smbclient
        import smbprotocol.exceptions
    except ImportError as e:
        _fail(f"smbprotocol not installed: {e}  (pip install smbprotocol)")

    # --- 1. list folder ---
    print("Listing share ...")
    listing_result: dict = {}

    def _do_list():
        try:
            listing_result['names'] = list(smbclient.listdir(
                base, username=user_spec, password=password,
            ))
        except Exception as e:
            listing_result['error'] = e

    t = threading.Thread(target=_do_list, daemon=True, name='smb-test-list')
    t.start()
    t.join(timeout=TIMEOUT_SEC)
    if t.is_alive():
        _fail(f"listdir timed out after {TIMEOUT_SEC}s — server unreachable or hung")
    if 'error' in listing_result:
        _fail(f"listdir: {listing_result['error']}")
    names = listing_result['names']
    _ok(f"listdir returned {len(names)} entries")
    if names:
        sample = ', '.join(names[:5])
        print(f"      sample: {sample}{' ...' if len(names) > 5 else ''}")

    # --- 2. write tiny test file ---
    stamp = time.strftime('%Y%m%d_%H%M%S')
    test_name = f"_conntest_{stamp}_{uuid.uuid4().hex[:6]}.txt"
    test_path = f"{base}\\{test_name}"
    payload = f"smb conntest {stamp} pid={os.getpid()}\n".encode('utf-8')

    print(f"Writing {test_name} ...")
    write_err: dict = {}

    def _do_write():
        try:
            with smbclient.open_file(
                test_path, mode='wb',
                username=user_spec, password=password,
            ) as f:
                f.write(payload)
        except Exception as e:
            write_err['error'] = e

    t = threading.Thread(target=_do_write, daemon=True, name='smb-test-write')
    t.start()
    t.join(timeout=TIMEOUT_SEC)
    if t.is_alive():
        _fail(f"write timed out after {TIMEOUT_SEC}s")
    if 'error' in write_err:
        _fail(f"write: {write_err['error']}")
    _ok(f"wrote {len(payload)} bytes")

    # --- 3. read back ---
    print("Reading back ...")
    read_result: dict = {}

    def _do_read():
        try:
            with smbclient.open_file(
                test_path, mode='rb',
                username=user_spec, password=password,
            ) as f:
                read_result['data'] = f.read()
        except Exception as e:
            read_result['error'] = e

    t = threading.Thread(target=_do_read, daemon=True, name='smb-test-read')
    t.start()
    t.join(timeout=TIMEOUT_SEC)
    if t.is_alive():
        # Try to clean up before bailing out
        try:
            smbclient.remove(test_path, username=user_spec, password=password)
        except Exception:
            pass
        _fail(f"read timed out after {TIMEOUT_SEC}s")
    if 'error' in read_result:
        try:
            smbclient.remove(test_path, username=user_spec, password=password)
        except Exception:
            pass
        _fail(f"read: {read_result['error']}")
    if read_result['data'] != payload:
        try:
            smbclient.remove(test_path, username=user_spec, password=password)
        except Exception:
            pass
        _fail(f"read mismatch: wrote {len(payload)} bytes, got {len(read_result['data'])}")
    _ok("read matches written payload")

    # --- 4. delete ---
    print("Cleaning up ...")
    try:
        smbclient.remove(test_path, username=user_spec, password=password)
        _ok(f"removed {test_name}")
    except Exception as e:
        # Not fatal — the test itself succeeded; just warn loudly.
        print(f"  WARN: could not remove {test_path}: {e}")
        print("  WARN: please remove it manually so the share stays clean")

    print()
    print("ALL OK — credentials work, share is reachable, read/write/delete succeeded.")
    sys.exit(0)


if __name__ == '__main__':
    main()
