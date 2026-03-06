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
import os
import sys
import yaml
import glob
import logging
import argparse
import subprocess
from datetime import datetime
from collections import defaultdict

from detector import detect_format
from parsers import PARSERS
from writer import write_to_master, load_existing_keys


def setup_logging(config: dict):
    log_file = config.get('logging', {}).get('file', './logs/processor.log')
    log_level = config.get('logging', {}).get('level', 'INFO')
    os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ]
    )


def load_config(path: str = 'config.yaml') -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def should_skip_file(filename: str, config: dict) -> bool:
    """Check if file should be skipped based on config rules."""
    lower = filename.lower()

    # Skip by filename substring
    skip_subs = config.get('skip_rules', {}).get('filename_contains', [])
    for sub in skip_subs:
        if sub.lower() in lower:
            return True

    # Skip by extension
    skip_exts = config.get('skip_rules', {}).get('ignore_extensions', [])
    for ext in skip_exts:
        if lower.endswith(ext.lower()):
            return True

    return False


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
        xlsx_path = os.path.splitext(filepath)[0] + '.xlsx'
        if os.path.exists(xlsx_path):
            logger.info(f"Converted {os.path.basename(filepath)} → .xlsx")
            return xlsx_path
    except Exception as e:
        logger.error(f"Failed to convert {filepath}: {e}")

    # Fallback: try reading directly with xlrd (if installed)
    return filepath


def process_file(filepath: str, master_path: str, config: dict, stats: dict,
                 sender: str = None,
                 existing_keys: set | None = None, dry_run: bool = False) -> int:
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
    except Exception as e:
        logger.error(f"Parse error in {filename}: {e}", exc_info=True)
        stats['errors'].append(f"Parse error: {filename} ({e})")
        return 0

    if not records:
        logger.info(f"No records: {filename}")
        stats['files_skipped'] += 1
        stats['empty_files'].append(filename)
        return 0

    # Deduplicate against existing master
    if config.get('processing', {}).get('deduplicate', True) and existing_keys:
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

    # Write
    if not dry_run:
        write_to_master(records, master_path, source_filename=filename)
        # Update existing keys with new records
        if existing_keys is not None:
            for r in records:
                existing_keys.add(_record_key(r))

    stats['total_records'] += len(records)
    return len(records)


def _record_key(record: dict) -> tuple:
    """Create deduplication key from record."""
    def clean(val):
        s = str(val).strip() if val is not None else ''
        return '' if s == 'nan' or s == 'None' or s == 'NaT' else s

    return (
        clean(record.get('ФИО', '')).upper(),
        clean(record.get('№ полиса', '')),
        clean(record.get('Начало обслуживания', '')),
        clean(record.get('Конец обслуживания', '')),
    )


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
        'master_path': '',
    }


def run_imap_mode(config: dict, dry_run: bool = False):
    """Full pipeline: fetch from IMAP → detect → parse → write → notify."""
    logger = logging.getLogger(__name__)
    from fetcher import IMAPFetcher

    stats = make_stats()
    master_path = config['output']['master_file']
    stats['master_path'] = master_path

    # Load existing records for dedup
    existing_keys = None
    if config.get('processing', {}).get('deduplicate', True):
        existing_keys = load_existing_keys(master_path)
        logger.info(f"Loaded {len(existing_keys)} existing records for dedup")

    fetcher = IMAPFetcher(config, dry_run=dry_run)
    try:
        fetcher.connect()
        days_back = config.get('imap', {}).get('days_back', 7)
        attachments = fetcher.fetch_attachments(days_back=days_back)

        for att in attachments:
            process_file(att['filepath'], master_path, config, stats,
                        sender=att.get('sender', ''),
                        existing_keys=existing_keys, dry_run=dry_run)
            try:
                os.remove(att['filepath'])
            except OSError:
                pass
    except Exception as e:
        logger.error(f"IMAP error: {e}", exc_info=True)
        stats['errors'].append(f"IMAP error: {e}")
    finally:
        fetcher.disconnect()

    _print_summary(stats)

    # Send email report
    if not dry_run:
        from notifier import send_report
        send_report(config, stats)

    return stats


def run_local_mode(folder: str, config: dict, dry_run: bool = False):
    """Process files from a local folder."""
    logger = logging.getLogger(__name__)
    stats = make_stats()
    master_path = config['output']['master_file']
    stats['master_path'] = master_path

    existing_keys = None
    if config.get('processing', {}).get('deduplicate', True):
        existing_keys = load_existing_keys(master_path)
        if existing_keys:
            logger.info(f"Loaded {len(existing_keys)} existing records for dedup")

    files = glob.glob(os.path.join(folder, '*.xlsx')) + glob.glob(os.path.join(folder, '*.xls'))
    logger.info(f"Found {len(files)} files in {folder}")

    for filepath in sorted(files):
        process_file(filepath, master_path, config, stats,
                    existing_keys=existing_keys, dry_run=dry_run)

    _print_summary(stats)

    if not dry_run:
        from notifier import send_report
        send_report(config, stats)

    return stats


def run_test_mode(folder: str, config: dict):
    """Test mode: parse files and show results, don't write anything."""
    logger = logging.getLogger(__name__)
    files = glob.glob(os.path.join(folder, '*.xlsx')) + glob.glob(os.path.join(folder, '*.xls'))
    print(f"\n{'='*70}")
    print(f"TEST MODE — {len(files)} files found")
    print(f"{'='*70}\n")

    total = 0
    for filepath in sorted(files):
        filename = os.path.basename(filepath)

        if should_skip_file(filename, config):
            print(f"⏭  SKIP: {filename}")
            continue

        if filepath.lower().endswith('.xls'):
            filepath = convert_xls_to_xlsx(filepath) or filepath

        fmt = detect_format(filepath)
        if fmt is None:
            print(f"❌ UNKNOWN: {filename}")
            continue

        parser_fn = PARSERS.get(fmt)
        if not parser_fn:
            print(f"❌ NO PARSER ({fmt}): {filename}")
            continue

        try:
            records = parser_fn(filepath)
        except Exception as e:
            print(f"❌ ERROR: {filename} — {e}")
            continue

        if not records:
            print(f"⚠  EMPTY: {filename} (format: {fmt})")
            continue

        total += len(records)
        print(f"✅ {fmt.upper():12s} | {len(records):3d} records | {filename}")
        for r in records[:3]:  # show first 3
            fio = (r.get('ФИО') or '')[:35]
            polis = (r.get('№ полиса') or '')[:20]
            start = r.get('Начало обслуживания') or ''
            end = r.get('Конец обслуживания') or ''
            company = r.get('Страховая компания') or ''
            print(f"   → {fio:35s} | {polis:20s} | {start:10s}-{end:10s} | {company}")
        if len(records) > 3:
            print(f"   ... and {len(records) - 3} more")

    print(f"\n{'='*70}")
    print(f"TOTAL: {total} records from {len(files)} files")
    print(f"{'='*70}\n")


def _print_summary(stats: dict):
    """Print processing summary to console."""
    print(f"\n{'='*50}")
    print(f"  Records:    {stats['total_records']}")
    print(f"  Files OK:   {stats['files_processed']}")
    print(f"  Skipped:    {stats['files_skipped']}")
    print(f"  Duplicates: {stats['duplicates_removed']}")
    if stats['by_company']:
        print(f"  By company:")
        for company, count in sorted(stats['by_company'].items(), key=lambda x: -x[1]):
            print(f"    {company}: {count}")
    if stats.get('unknown_files'):
        print(f"  ❓ Unknown format ({len(stats['unknown_files'])}):")
        for f in stats['unknown_files'][:10]:
            print(f"    {f}")
    if stats.get('empty_files'):
        print(f"  📭 Empty files ({len(stats['empty_files'])}):")
        for f in stats['empty_files'][:10]:
            print(f"    {f}")
    if stats['errors']:
        print(f"  Errors: {len(stats['errors'])}")
        for e in stats['errors'][:5]:
            print(f"    ⚠ {e}")
    print(f"{'='*50}\n")


if __name__ == '__main__':
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
