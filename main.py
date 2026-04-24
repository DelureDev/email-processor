#!/usr/bin/env python3
"""
Email → XLSX Processor
Extracts patient data from insurance company emails into a master spreadsheet.

Usage:
    python main.py                     # IMAP mode: fetch emails + process
    python main.py --local ./files     # Local mode: process files from folder
    python main.py --test ./files      # Test mode: parse + show results, no write
    python main.py --dry-run           # IMAP mode but don't write to master
"""
__version__ = "1.10.17"

import os
import re
import sys
import shutil
import yaml
import glob
import logging
from logging.handlers import RotatingFileHandler
import argparse
import subprocess
import urllib.request
from datetime import datetime
from collections import defaultdict
from functools import lru_cache

from detector import detect_format
from parsers import PARSERS
from parsers.errors import HeaderNotFoundError
from parsers.utils import record_key, clean_dedup_val, norm_date_pad
from writer import write_to_master, write_batch_to_master, load_existing_keys
from clinic_matcher import detect_clinic, extract_policy_comment
from run_summary import build_run_summary, compute_status


def setup_logging(config: dict) -> None:
    log_file = config.get('logging', {}).get('file', './logs/processor.log')
    log_level = config.get('logging', {}).get('level', 'INFO')
    os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            RotatingFileHandler(log_file, encoding='utf-8',
                                maxBytes=10 * 1024 * 1024, backupCount=5),
            logging.StreamHandler(sys.stdout),
        ]
    )

    # Audit logger — separate file for password-handling events
    audit_log_file = config.get('logging', {}).get('audit_file', './logs/audit.log')
    os.makedirs(os.path.dirname(audit_log_file) or '.', exist_ok=True)
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    if not audit_logger.handlers:
        handler = RotatingFileHandler(audit_log_file, encoding='utf-8',
                                      maxBytes=10 * 1024 * 1024, backupCount=5)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        audit_logger.addHandler(handler)


def _expand_env(obj):
    """Recursively expand ${VAR_NAME} placeholders in config values.

    Raises ValueError if any referenced env var is unset.
    """
    if isinstance(obj, str):
        unresolved = []
        def _replace(m):
            name = m.group(1)
            val = os.environ.get(name)
            if val is None:
                unresolved.append(name)
                return m.group(0)
            return val
        result = re.sub(r'\$\{(\w+)\}', _replace, obj)
        if unresolved:
            raise ValueError(f"Unresolved environment variable(s): {', '.join(unresolved)}")
        return result
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(i) for i in obj]
    return obj


def load_config(path: str = 'config.yaml') -> dict:  # type: ignore[return]
    with open(path, 'r', encoding='utf-8') as f:
        config = _expand_env(yaml.safe_load(f))
    if not isinstance(config, dict):
        raise ValueError(f"Config file {path} is empty or invalid (expected dict, got {type(config).__name__})")
    # Validate required keys exist and provide clear errors
    required = {
        'imap.server': ('imap', 'server'),
        'imap.username': ('imap', 'username'),
        'imap.password': ('imap', 'password'),
        'processing.temp_folder': ('processing', 'temp_folder'),
        'processing.processed_ids_file': ('processing', 'processed_ids_file'),
    }
    missing = []
    for label, keys in required.items():
        obj = config
        for k in keys:
            if not isinstance(obj, dict) or k not in obj:
                missing.append(label)
                break
            obj = obj[k]
    if missing:
        raise ValueError(f"Config {path} missing required keys: {', '.join(missing)}")
    return config


@lru_cache(maxsize=1)
def _build_skip_rules(skip_subs: tuple, skip_exts: tuple) -> tuple[tuple, tuple]:
    """Precompute lowercased skip rules (cached after first call)."""
    return (
        tuple(s.lower() for s in skip_subs),
        tuple(e.lower() for e in skip_exts),
    )


def should_skip_file(filename: str, config: dict) -> bool:
    """Check if file should be skipped based on config rules."""
    rules = config.get('skip_rules', {})
    skip_subs, skip_exts = _build_skip_rules(
        tuple(rules.get('filename_contains', [])),
        tuple(rules.get('ignore_extensions', [])),
    )
    lower = filename.lower()
    return any(sub in lower for sub in skip_subs) or any(lower.endswith(ext) for ext in skip_exts)


def convert_xls_to_xlsx(filepath: str) -> str | None:
    """Convert .xls to .xlsx using LibreOffice. Returns new path or None on failure."""
    logger = logging.getLogger(__name__)
    if not filepath.lower().endswith('.xls'):
        return filepath

    outdir = os.path.dirname(filepath) or '.'
    try:
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'xlsx', filepath, '--outdir', outdir],
            capture_output=True, timeout=60
        )
        if result.returncode != 0:
            logger.error(f"LibreOffice exited {result.returncode} for {os.path.basename(filepath)}: "
                         f"{result.stderr.decode(errors='replace')[:200]}")
            return None
        xlsx_path = os.path.splitext(filepath)[0] + '.xlsx'
        if os.path.exists(xlsx_path) and os.path.getsize(xlsx_path) > 0:
            logger.info(f"Converted {os.path.basename(filepath)} → .xlsx")
            return xlsx_path
        logger.error(f"LibreOffice produced no output for {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"Failed to convert {filepath}: {e}")

    return None


def _dedup_xls_xlsx(files: list[str]) -> list[str]:
    """When both .xls and .xlsx exist for the same stem, keep only .xlsx."""
    by_stem = {}
    for f in files:
        stem = os.path.splitext(f)[0]
        ext = os.path.splitext(f)[1].lower()
        if stem not in by_stem or ext == '.xlsx':
            by_stem[stem] = f
    return list(by_stem.values())


def _quarantine(filepath: str, config: dict) -> None:
    """Copy a problematic file to the quarantine folder for manual inspection."""
    logger = logging.getLogger(__name__)
    quarantine_dir = config.get('processing', {}).get('quarantine_folder', './quarantine')
    try:
        os.makedirs(quarantine_dir, exist_ok=True)
        dest = os.path.join(quarantine_dir, os.path.basename(filepath))
        shutil.copy2(filepath, dest)
        logger.warning(f"Quarantined: {os.path.basename(filepath)} → {quarantine_dir}")
    except OSError as e:
        logger.error(f"Failed to quarantine {filepath}: {e}")


def process_file(filepath: str, master_path: str, config: dict, stats: dict,
                 sender: str = None, subject: str = None,
                 existing_keys: set | None = None, dry_run: bool = False,
                 pending: list | None = None) -> int:
    """Process a single file. Returns number of new records written."""
    logger = logging.getLogger(__name__)
    filename = os.path.basename(filepath)

    if should_skip_file(filename, config):
        logger.info(f"Skipped (rule): {filename}")
        stats['files_skipped'] += 1
        stats['skipped_files'].append(filename)
        return 0

    # Convert .xls if needed
    if filepath.lower().endswith('.xls'):
        filepath = convert_xls_to_xlsx(filepath)
        if not filepath:
            stats['errors'].append(f"Failed to convert: {filename}")
            return 0

    # Detect format
    fmt = detect_format(filepath, sender=sender)
    if fmt is None:
        logger.warning(f"Unknown format: {filename}")
        stats['files_skipped'] += 1
        stats['unknown_files'].append(filename)
        return 0

    parser_fn = PARSERS.get(fmt)
    if parser_fn is None:
        logger.warning(f"No parser for format '{fmt}': {filename}")
        stats['files_skipped'] += 1
        stats['unknown_files'].append(filename)
        return 0

    # Parse
    try:
        records = parser_fn(filepath)
    except HeaderNotFoundError as e:
        logger.error(f"Header not found in {filename}: {e}")
        stats['errors'].append(f"Header not found in {filename}: {e}")
        _quarantine(filepath, config)
        return 0
    except Exception as e:
        logger.error(f"Parse error in {filename}: {e}", exc_info=True)
        stats['errors'].append(f"Parse error: {filename} ({e})")
        _quarantine(filepath, config)
        return 0

    if not records:
        logger.info(f"No records: {filename}")
        stats['files_skipped'] += 1
        stats['empty_files'].append(filename)
        return 0

    # Warn if any records have both start and end dates empty — likely a parser miss
    empty_date_records = [
        r for r in records
        if not (r.get('Начало обслуживания') or '').strip()
        and not (r.get('Конец обслуживания') or '').strip()
    ]
    if empty_date_records:
        names = ', '.join(r.get('ФИО', '?') for r in empty_date_records)
        logger.error(f"Empty dates: {len(empty_date_records)} record(s) in {filename} have no start or end date: {names}")
        stats['errors'].append(f"Пустые даты ({len(empty_date_records)} зап.) в {filename}: {names}")

    # Detect clinic (once per file) and inject into all records BEFORE dedup,
    # because Клиника is part of the dedup key.
    try:
        clinic, need_comment, clinic_id = detect_clinic(filepath, subject=subject)
    except Exception as e:
        logger.warning(f"Clinic detection failed for {filename}: {e}")
        clinic, need_comment, clinic_id = '⚠️ Не определено', False, ''
    comment = ''
    if need_comment:
        try:
            comment = extract_policy_comment(filepath)
        except Exception as e:
            logger.warning(f"Comment extraction failed for {filename}: {e}")
    records = [{
        **r,
        'Клиника': clinic,
        'ID Клиники': clinic_id,
        'Комментарий в полис': r.get('Комментарий в полис') or comment,
    } for r in records]

    if clinic == '⚠️ Не определено':
        stats['unmatched_clinics'].append(filename)
    if need_comment and not comment:
        stats['missing_comments'].append(filename)

    # Deduplicate against existing master (after clinic injection so keys match)
    if config.get('processing', {}).get('deduplicate', True) and existing_keys is not None:
        original_count = len(records)
        records = [r for r in records if _record_key(r) not in existing_keys]
        dupes = original_count - len(records)
        if dupes > 0:
            logger.info(f"Dedup: removed {dupes} duplicates from {filename}")
            stats['duplicates_removed'] += dupes

    if not records:
        logger.info(f"All records already in master: {filename}")
        return 0

    # Track stats
    stats['files_processed'] += 1
    for r in records:
        company = r.get('Страховая компания', 'Неизвестно')
        stats['by_company'][company] += 1
        stats['new_records'].append({**r, 'Источник файла': filename, 'Дата обработки': datetime.now().strftime('%d.%m.%Y')})

    # Write (or queue for batch write)
    if not dry_run:
        if pending is not None:
            pending.append((records, filename))
        else:
            write_to_master(records, master_path, source_filename=filename)
        # Update existing keys so subsequent files in same run deduplicate correctly
        if existing_keys is not None:
            for r in records:
                existing_keys.add(_record_key(r))

    stats['total_records'] += len(records)
    return len(records)


def _record_key(record: dict) -> tuple:
    """Create deduplication key from record. Delegates to shared parsers.utils.record_key."""
    return record_key(record)


def make_stats() -> dict:
    return {
        'total_records': 0,
        'files_processed': 0,
        'files_skipped': 0,
        'duplicates_removed': 0,
        'by_company': defaultdict(int),
        'errors': [],
        'unknown_files': [],
        'skipped_files': [],
        'empty_files': [],
        'new_records': [],
        'monthly_records': [],
        'master_path': '',
        'unmatched_clinics': [],
        'missing_comments': [],
        'run_start': None,         # datetime set by run_imap_mode / run_local_mode / run_test_mode
        'smtp_status': 'SKIP',     # 'OK' | 'FAIL' | 'SKIP'
        'network_status': 'SKIP',  # 'OK' | 'FAIL' | 'SKIP'
    }


def _attach_monthly_if_last_day(config: dict, stats: dict) -> None:
    """On the last day of the month, read master.xlsx and populate stats['monthly_records']."""
    import calendar
    today = datetime.now()
    last_day = calendar.monthrange(today.year, today.month)[1]
    if today.day != last_day:
        return
    master_path = config.get('output', {}).get('master_file', './output/master.xlsx')
    if not os.path.exists(master_path):
        return
    logger = logging.getLogger(__name__)
    try:
        import pandas as pd
        df = pd.read_excel(master_path, dtype=str).fillna('')
        # Zero-padded month suffix: matches end of DD.MM.YYYY (e.g. "03.2026")
        month_suffix = f"{today.month:02d}.{today.year}"
        if 'Дата обработки' in df.columns:
            normed = df['Дата обработки'].map(lambda s: norm_date_pad(str(s)))
            mask = normed.str.endswith(month_suffix, na=False)
            monthly = df[mask].to_dict('records')
        else:
            monthly = df.to_dict('records')
        stats['monthly_records'] = monthly
        logger.info(f"Monthly report: {len(monthly)} records for {today.strftime('%B %Y')}")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to build monthly records: {e}")
        stats['errors'].append(f"Monthly report build failed: {e}")


def _export_to_network(config: dict, stats: dict) -> None:
    """Write daily delta CSV and monthly master CSV to network folder if configured.
    Both probe AND writes run under daemon-thread timeouts so a kernel-hung CIFS
    mount cannot pin the process. Belt-and-suspenders when the mount is
    configured with 'soft' (recommended fstab option)."""
    folder = config.get('output', {}).get('csv_export_folder', '').strip()
    if not folder or not stats.get('new_records'):
        return
    logger = logging.getLogger(__name__)

    # Probe reachability with a daemon thread. ThreadPoolExecutor's `with` exit
    # calls shutdown(wait=True), which pins the process forever if the worker
    # is stuck in a D-state CIFS syscall (v1.9.3 incident kept recurring for
    # exactly this reason — see v1.10.14 in CHANGELOG). Daemon threads are not
    # joined at interpreter shutdown, so the main flow can complete even when
    # the probe never returns.
    import threading
    timeout_sec = config.get('output', {}).get('network_timeout', 10)
    probe_result: dict = {}

    def _probe():
        try:
            probe_result['reachable'] = os.path.isdir(folder)
        except Exception as e:
            probe_result['error'] = e

    probe_thread = threading.Thread(target=_probe, daemon=True, name='cifs-probe')
    probe_thread.start()
    probe_thread.join(timeout=timeout_sec)

    if probe_thread.is_alive():
        logger.error(f"Network share not reachable (timed out after {timeout_sec}s): {folder}")
        stats['errors'].append(f"Network share timed out: {folder}")
        stats['network_status'] = 'FAIL'
        return
    if 'error' in probe_result:
        logger.error(f"Network share probe failed: {probe_result['error']}")
        stats['errors'].append(f"Network share probe error: {probe_result['error']}")
        stats['network_status'] = 'FAIL'
        return
    if not probe_result.get('reachable'):
        logger.error(f"Network share folder does not exist: {folder}")
        stats['errors'].append(f"Network share not found: {folder}")
        stats['network_status'] = 'FAIL'
        return

    import csv
    from writer import COLUMNS, _safe

    # Network CSV includes ID Клиники for 1C integration (right after Клиника)
    csv_columns = []
    for c in COLUMNS:
        csv_columns.append(c)
        if c == 'Клиника':
            csv_columns.append('ID Клиники')

    def _migrate_csv_header(filepath: str) -> None:
        """If existing CSV has old header (without ID Клиники), rewrite with new column.
        Old data rows get empty ID Клиники; new rows will have the value.

        Reads only the first line for the common no-migration-needed path — on
        CIFS with a large master_YYYY-MM.csv, reading the entire file just to
        check the header was wasting tens of seconds per run and multiplying
        CIFS ops for no reason."""
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f, delimiter=';')
                try:
                    header = next(reader)
                except StopIteration:
                    return  # empty file
            if 'ID Клиники' in header:
                return  # already migrated — fast path, only first line was read
            if 'Клиника' not in header:
                return  # unrecognized format, don't touch
            # Migration needed — now we have to read the full file (rare, one-off).
            with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f, delimiter=';')
                rows = list(reader)
            idx = header.index('Клиника') + 1
            new_header = header[:idx] + ['ID Клиники'] + header[idx:]
            new_rows = [new_header]
            for row in rows[1:]:
                new_rows.append(row[:idx] + [''] + row[idx:])
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=';', lineterminator='\r\n')
                writer.writerows(new_rows)
            logger.info(f"Migrated CSV header: added ID Клиники column to {filepath}")
        except Exception as e:
            logger.warning(f"Failed to migrate CSV header in {filepath}: {e}")

    now = datetime.now()
    records = stats['new_records']
    write_timeout = config.get('output', {}).get('network_write_timeout', 30)

    def _write_one_with_timeout(dest: str, kind: str) -> None:
        """Run migrate-header + append under a daemon-thread timeout.
        Any syscall inside can still block indefinitely on a 'hard' CIFS mount,
        but this join() cap means the main flow moves on after write_timeout
        instead of pinning. Mutates stats on failure."""
        result: dict = {}

        def _work():
            try:
                _migrate_csv_header(dest)
                # Treat a zero-byte file the same as a missing file. A 0-byte file
                # happens when: (a) the user `touch`ed it as a CIFS-create workaround,
                # (b) a previous run crashed/hung after open() but before writing.
                # Without this check we'd skip the header AND the UTF-8 BOM, producing
                # a 1C-unreadable CSV with data rows but no column definitions.
                is_empty = not os.path.exists(dest) or os.path.getsize(dest) == 0
                encoding = 'utf-8-sig' if is_empty else 'utf-8'
                with open(dest, 'a', newline='', encoding=encoding) as f:
                    w = csv.DictWriter(f, fieldnames=csv_columns, extrasaction='ignore', delimiter=';', lineterminator='\r\n')
                    if is_empty:
                        w.writeheader()
                    for record in records:
                        w.writerow({k: _safe(v) for k, v in record.items()})
                result['ok'] = True
            except Exception as e:
                result['error'] = e

        t = threading.Thread(target=_work, daemon=True, name=f'cifs-{kind}-write')
        t.start()
        t.join(timeout=write_timeout)

        if t.is_alive():
            logger.error(f"CIFS {kind} write timed out after {write_timeout}s: {dest}")
            stats['errors'].append(f"Network {kind} CSV timed out: {dest}")
            stats['network_status'] = 'FAIL'
        elif 'error' in result:
            logger.error(f"Failed to export {kind} CSV to network: {result['error']}")
            stats['errors'].append(f"Network {kind} CSV failed: {result['error']}")
            stats['network_status'] = 'FAIL'
        else:
            logger.info(f"Exported {kind} ({len(records)} records) to {dest}")

    # 1. Daily delta — append across runs within the same day
    date_str = now.strftime('%Y-%m-%d')
    daily_dest = os.path.join(folder, f'records_{date_str}.csv')
    _write_one_with_timeout(daily_dest, 'daily')

    # 2. Monthly master — append to current month file, new file each month
    month_str = now.strftime('%Y-%m')
    monthly_dest = os.path.join(folder, f'master_{month_str}.csv')
    _write_one_with_timeout(monthly_dest, 'monthly')

    # If we got here without setting FAIL and both writes were attempted, mark OK.
    if stats.get('network_status') != 'FAIL':
        stats['network_status'] = 'OK'


def _force_exit_if_stuck_threads(exit_code: int = 0) -> None:
    """Escape hatch for when daemon threads are pinned in D-state kernel syscalls
    (dead CIFS mount, NFS server gone, etc). Even though our join(timeout=N)
    cap lets the main flow continue, the Python process itself cannot cleanly
    exit while a daemon thread is stuck in an uninterruptible syscall — the
    kernel holds the process open until the syscall returns (which for CIFS
    soft,retrans=2 can be up to ~70s). From the user's perspective the shell
    prompt hangs.

    os._exit bypasses Python shutdown entirely and tells the kernel to mark
    the process for exit. The kernel cleans up what it can immediately and
    reaps the D-state thread whenever the syscall eventually returns. User
    gets their prompt back now, not in a minute."""
    import threading
    live = [t for t in threading.enumerate()
            if t.daemon and t.is_alive() and t is not threading.main_thread()]
    if not live:
        return
    names = [t.name for t in live]
    logger = logging.getLogger(__name__)
    logger.warning(f"Forcing exit — {len(live)} daemon thread(s) still alive "
                   f"(likely D-state CIFS syscall): {names}")
    sys.stderr.write(f"[force-exit] {len(live)} stuck daemon thread(s): {names}\n")
    sys.stderr.flush()
    os._exit(exit_code)


def _ping_healthcheck(config: dict, stats: dict) -> None:
    """Ping healthchecks.io (or compatible) URL to confirm cron is alive."""
    url = config.get('healthcheck_url', '').strip()
    if not url:
        return
    if not url.startswith('https://'):
        logging.getLogger(__name__).warning(f"Healthcheck URL must start with https:// — skipping: {url[:50]}")
        return
    logger = logging.getLogger(__name__)
    body = (
        f"records={stats['total_records']} "
        f"files={stats['files_processed']} "
        f"errors={len(stats['errors'])}"
    ).encode()
    # Append /fail if there were errors so healthchecks.io marks it red
    if stats['errors']:
        url = url.rstrip('/') + '/fail'
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=body, method='POST'),
            timeout=10,
        )
        logger.debug(f"Healthcheck pinged: {url}")
    except Exception as e:
        msg = f"Healthcheck ping failed: {e}"
        logger.error(msg)
        if stats is not None:
            stats['errors'].append(msg)


def run_imap_mode(config: dict, dry_run: bool = False):
    """Full pipeline: fetch from IMAP → detect → parse → write → notify."""
    logger = logging.getLogger(__name__)
    from fetcher import IMAPFetcher

    stats = make_stats()
    stats['run_start'] = datetime.now()
    master_path = config.get('output', {}).get('master_file', './output/master.xlsx')
    stats['master_path'] = master_path

    exception_class: str | None = None
    try:
        # Load existing records for dedup
        existing_keys = None
        if config.get('processing', {}).get('deduplicate', True):
            existing_keys = load_existing_keys(master_path)
            logger.info(f"Loaded {len(existing_keys)} existing records for dedup")

        fetcher = IMAPFetcher(config, dry_run=dry_run)
        pending = []
        processed_imap_ids = []
        # Track all Zetta extract dirs up front so we can clean them in finally,
        # even if process_file throws mid-loop (otherwise dirs for later files in
        # the same zip would leak because only the last att carries _extract_dir).
        extract_dirs_to_clean: set[str] = set()
        try:
            fetcher.connect()
            days_back = config.get('imap', {}).get('days_back', 7)
            attachments = fetcher.fetch_attachments(days_back=days_back)
            for att in attachments:
                if att.get('_extract_dir'):
                    extract_dirs_to_clean.add(att['_extract_dir'])

            for att in attachments:
                process_file(att['filepath'], master_path, config, stats,
                            sender=att.get('sender', ''),
                            subject=att.get('subject', ''),
                            existing_keys=existing_keys, dry_run=dry_run,
                            pending=pending)
                # Always mark email as processed — dedup handles duplicates,
                # no need to re-download and re-parse the same attachment every run
                if att.get('imap_id'):
                    processed_imap_ids.append(att['imap_id'])
                try:
                    os.remove(att['filepath'])
                except OSError:
                    pass
                # Clean up converted .xlsx if original was .xls
                if att['filepath'].lower().endswith('.xls'):
                    try:
                        os.remove(os.path.splitext(att['filepath'])[0] + '.xlsx')
                    except OSError:
                        pass
        except Exception as e:
            logger.error(f"IMAP error: {e}", exc_info=True)
            stats['errors'].append(f"IMAP error: {e}")
        finally:
            # Clean up every Zetta extract dir we collected, regardless of how we exited
            for extract_dir in extract_dirs_to_clean:
                try:
                    shutil.rmtree(extract_dir, ignore_errors=True)
                except OSError:
                    pass

        # Surface Zetta zip failures in email report
        if fetcher.failed_zips:
            for name in fetcher.failed_zips:
                stats['errors'].append(f"Zetta zip not extracted: {name}")

        # Write batch BEFORE marking emails as processed — if write fails,
        # emails stay in inbox and will be re-fetched on next run (no data loss).
        write_ok = True
        if pending and not dry_run:
            try:
                write_batch_to_master(pending, master_path)
            except Exception as e:
                logger.error(f"Failed to write batch to master: {e}", exc_info=True)
                stats['errors'].append(f"Master write failed: {e}")
                pending.clear()
                processed_imap_ids.clear()
                stats['new_records'].clear()
                stats['total_records'] = 0
                write_ok = False

        # Move emails and save IDs only AFTER successful write
        try:
            if not dry_run and write_ok:
                dest = config.get('imap', {}).get('processed_folder', '').strip()
                if dest and processed_imap_ids:
                    fetcher.move_to_folder(processed_imap_ids, dest)
                fetcher._save_processed_ids()
            elif dry_run:
                logger.info("Dry-run: not saving processed IDs")
            else:
                logger.warning("Write failed — skipping processed IDs save so emails re-fetch next run")
        finally:
            fetcher.disconnect()

        _print_summary(stats)

        # Order matters: email and healthcheck MUST run before the CIFS export.
        # The export probe can leak a daemon thread stuck in a D-state syscall
        # if the SMB server is dead; putting it last means the run's email and
        # health ping still complete before the process gets pinned at exit.
        if not dry_run:
            try:
                _attach_monthly_if_last_day(config, stats)
            except Exception as e:
                logger.error(f"Monthly attachment failed: {e}", exc_info=True)
            try:
                from notifier import send_report
                send_report(config, stats)
            except Exception as e:
                logger.error(f"Notifier failed: {e}", exc_info=True)

        # Healthcheck ping — always fires so we know if cron stopped running
        _ping_healthcheck(config, stats)

        if not dry_run:
            try:
                _export_to_network(config, stats)
            except Exception as e:
                logger.error(f"Network export failed: {e}", exc_info=True)
                stats['errors'].append(f"Network export failed: {e}")

    except Exception as e:
        exception_class = type(e).__name__
        raise
    finally:
        duration_s = int((datetime.now() - stats['run_start']).total_seconds())
        status = 'CRASH' if exception_class else compute_status(stats)
        logger.info(build_run_summary(
            stats,
            status=status,
            duration_s=duration_s,
            mode='imap',
            exception_class=exception_class,
        ))

    return stats


def run_local_mode(folder: str, config: dict, dry_run: bool = False):
    """Process files from a local folder."""
    logger = logging.getLogger(__name__)
    stats = make_stats()
    stats['run_start'] = datetime.now()
    master_path = config.get('output', {}).get('master_file', './output/master.xlsx')
    stats['master_path'] = master_path

    exception_class: str | None = None
    try:
        existing_keys = None
        if config.get('processing', {}).get('deduplicate', True):
            existing_keys = load_existing_keys(master_path)
            logger.info(f"Loaded {len(existing_keys)} existing records for dedup")

        files = _dedup_xls_xlsx(
            glob.glob(os.path.join(folder, '*.xlsx')) + glob.glob(os.path.join(folder, '*.xls'))
        )
        logger.info(f"Found {len(files)} files in {folder}")

        pending = []
        for filepath in sorted(files):
            process_file(filepath, master_path, config, stats,
                        existing_keys=existing_keys, dry_run=dry_run,
                        pending=pending)

        if pending and not dry_run:
            try:
                write_batch_to_master(pending, master_path)
            except Exception as e:
                logger.error(f"Failed to write batch to master: {e}", exc_info=True)
                stats['errors'].append(f"Master write failed: {e}")
                stats['new_records'].clear()
                stats['total_records'] = 0

        _print_summary(stats)

        # Same ordering as run_imap_mode: email first, export last.
        if not dry_run:
            try:
                _attach_monthly_if_last_day(config, stats)
            except Exception as e:
                logger.error(f"Monthly attachment failed: {e}", exc_info=True)
            try:
                from notifier import send_report
                send_report(config, stats)
            except Exception as e:
                logger.error(f"Notifier failed: {e}", exc_info=True)
            try:
                _export_to_network(config, stats)
            except Exception as e:
                logger.error(f"Network export failed: {e}", exc_info=True)
                stats['errors'].append(f"Network export failed: {e}")
    except Exception as e:
        exception_class = type(e).__name__
        raise
    finally:
        duration_s = int((datetime.now() - stats['run_start']).total_seconds())
        status = 'CRASH' if exception_class else compute_status(stats)
        logger.info(build_run_summary(
            stats,
            status=status,
            duration_s=duration_s,
            mode='local',
            exception_class=exception_class,
        ))

    return stats


def run_test_mode(folder: str, config: dict):
    """Test mode: parse files and show results, don't write anything."""
    import io
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') != 'utf8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logger = logging.getLogger(__name__)

    stats = make_stats()
    stats['run_start'] = datetime.now()

    exception_class: str | None = None
    try:
        files = _dedup_xls_xlsx(
            glob.glob(os.path.join(folder, '*.xlsx')) + glob.glob(os.path.join(folder, '*.xls'))
        )
        print(f"\n{'='*70}")
        print(f"TEST MODE - {len(files)} files found")
        print(f"{'='*70}\n")

        total = 0
        for filepath in sorted(files):
            filename = os.path.basename(filepath)

            if should_skip_file(filename, config):
                print(f"[SKIP] {filename}")
                continue

            if filepath.lower().endswith('.xls'):
                converted = convert_xls_to_xlsx(filepath)
                if converted is None:
                    print(f"[ERR]  CONVERT FAILED: {filename}")
                    continue
                filepath = converted

            fmt = detect_format(filepath)
            if fmt is None:
                print(f"[ERR]  UNKNOWN: {filename}")
                continue

            parser_fn = PARSERS.get(fmt)
            if not parser_fn:
                print(f"[ERR]  NO PARSER ({fmt}): {filename}")
                continue

            try:
                records = parser_fn(filepath)
            except Exception as e:
                print(f"[ERR]  ERROR: {filename} -- {e}")
                continue

            if not records:
                print(f"[---]  EMPTY: {filename} (format: {fmt})")
                continue

            clinic, need_comment, clinic_id = detect_clinic(filepath)
            comment = extract_policy_comment(filepath) if need_comment else ''
            total += len(records)
            print(f"[OK]  {fmt.upper():12s} | {len(records):3d} records | {filename} | clinic: {clinic}")
            if comment:
                print(f"   comment: {comment[:80]}")
            elif need_comment:
                print(f"   comment: (!) ne najden (extract_comment=true)")
            for r in records[:3]:  # show first 3
                fio = (r.get('ФИО') or '')[:35]
                polis = (r.get('№ полиса') or '')[:20]
                start = r.get('Начало обслуживания') or ''
                end = r.get('Конец обслуживания') or ''
                company = r.get('Страховая компания') or ''
                print(f"   > {fio:35s} | {polis:20s} | {start:10s}-{end:10s} | {company}")
            if len(records) > 3:
                print(f"   ... and {len(records) - 3} more")

        print(f"\n{'='*70}")
        print(f"TOTAL: {total} records from {len(files)} files")
        print(f"{'='*70}\n")
    except Exception as e:
        exception_class = type(e).__name__
        raise
    finally:
        duration_s = int((datetime.now() - stats['run_start']).total_seconds())
        status = 'CRASH' if exception_class else compute_status(stats)
        logger.info(build_run_summary(
            stats,
            status=status,
            duration_s=duration_s,
            mode='test',
            exception_class=exception_class,
        ))


def _print_summary(stats: dict) -> None:
    """Log processing summary."""
    _log = logging.getLogger(__name__)
    _log.info("=" * 50)
    _log.info(f"  Records:    {stats['total_records']}")
    _log.info(f"  Files OK:   {stats['files_processed']}")
    _log.info(f"  Skipped:    {stats['files_skipped']}")
    _log.info(f"  Duplicates: {stats['duplicates_removed']}")
    if stats['by_company']:
        _log.info("  By company:")
        for company, count in sorted(stats['by_company'].items(), key=lambda x: -x[1]):
            _log.info(f"    {company}: {count}")
    if stats.get('unknown_files'):
        _log.info(f"  Unknown format ({len(stats['unknown_files'])}):")
        for f in stats['unknown_files'][:10]:
            _log.info(f"    {f}")
    if stats.get('empty_files'):
        _log.info(f"  Empty files ({len(stats['empty_files'])}):")
        for f in stats['empty_files'][:10]:
            _log.info(f"    {f}")
    if stats['errors']:
        _log.info(f"  Errors: {len(stats['errors'])}")
        for e in stats['errors'][:5]:
            _log.info(f"    ! {e}")
    _log.info("=" * 50)


if __name__ == '__main__':
    if sys.platform != 'win32':
        import fcntl
        _LOCK_PATH = './logs/main.lock'
        os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
        _lock_fh = open(_LOCK_PATH, 'w')
        try:
            fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Another instance holds the lock — normal collision, not an error
            print("Another instance of main.py is already running (./logs/main.lock). Exiting.")
            sys.exit(0)
        except PermissionError as e:
            # Usually: lockfile owned by another UID (e.g. leftover from 'sudo python3 main.py').
            # This must NOT be treated as "already running" — cron would silently no-op forever.
            print(f"Cannot acquire ./logs/main.lock — permission denied ({e}). "
                  "Check file ownership: ls -la ./logs/main.lock", file=sys.stderr)
            sys.exit(2)

    parser = argparse.ArgumentParser(
        description='Email → XLSX Processor — extracts insurance data into master spreadsheet',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('--local', type=str, metavar='FOLDER',
                       help='Process files from local folder instead of IMAP')
    parser.add_argument('--test', type=str, metavar='FOLDER',
                       help='Test mode: parse and show results, no writing')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run full pipeline but don\'t write to master or send emails')
    parser.add_argument('--config', type=str, default='config.yaml',
                       help='Path to config file (default: config.yaml)')
    parser.add_argument('--no-dedup', action='store_true',
                       help='Disable deduplication')
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config)

    if args.no_dedup:
        config.setdefault('processing', {})['deduplicate'] = False

    if args.test:
        run_test_mode(args.test, config)
    elif args.local:
        run_local_mode(args.local, config, dry_run=args.dry_run)
    else:
        run_imap_mode(config, dry_run=args.dry_run)

    _force_exit_if_stuck_threads()
