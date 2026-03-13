#!/usr/bin/env python3
"""
diagnostic.py — Email Processor Diagnostic Tool v1.0
Compares Yandex inbox contents vs master.xlsx to find gaps.

Usage:
    python3 diagnostic.py                  # Use days_back from config.yaml
    python3 diagnostic.py --days 30        # Override to 30 days
    python3 diagnostic.py --days 30 --json # Also dump machine-readable JSON

Drop this file into the email-processor/ directory and run from there.
"""

import argparse
import email
import email.header
import imaplib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
import yaml


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def decode_header_value(raw):
    """Decode RFC2047-encoded email header into a string."""
    if raw is None:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def decode_filename(part):
    """Extract and decode attachment filename from a MIME part."""
    filename = part.get_filename()
    if filename:
        return decode_header_value(filename)
    # Fallback: Content-Disposition
    cd = part.get("Content-Disposition", "")
    match = re.search(r"filename\*?=['\"]?(?:UTF-8''|utf-8'')?(.*?)(?:['\";]|$)", cd, re.I)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))
    return None


SKIP_EXTENSIONS = {".pdf", ".docx", ".doc", ".jpg", ".png"}
SKIP_PATTERNS = ["_all.", "_all_"]


def should_skip(filename):
    """Check if a file would be skipped by email-processor rules."""
    if not filename:
        return True, "no filename"
    lower = filename.lower()
    _, ext = os.path.splitext(lower)
    if ext in SKIP_EXTENSIONS:
        return True, f"extension {ext}"
    for pat in SKIP_PATTERNS:
        if pat in lower:
            return True, f"pattern '{pat}'"
    return False, ""


# ─── IMAP Scanner ────────────────────────────────────────────────────────────

def scan_inbox(config, days_back):
    """Connect to IMAP and list all emails with attachments."""
    imap_cfg = config.get("imap", config)  # handle both nested and flat config
    host = imap_cfg.get("host", "imap.yandex.ru")
    port = imap_cfg.get("port", 993)
    user = imap_cfg.get("user") or imap_cfg.get("username") or imap_cfg.get("login")
    password = imap_cfg.get("password") or imap_cfg.get("app_password")
    folder = imap_cfg.get("folder", "INBOX")

    print(f"\n📡 Connecting to {host}:{port} as {user}...")
    conn = imaplib.IMAP4_SSL(host, port)
    conn.login(user, password)
    conn.select(folder, readonly=True)

    since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
    print(f"🔍 Searching emails since {since_date} (days_back={days_back})...")

    status, msg_ids = conn.search(None, f'(SINCE "{since_date}")')
    if status != "OK" or not msg_ids[0]:
        print("   No emails found.")
        conn.logout()
        return []

    id_list = msg_ids[0].split()
    print(f"   Found {len(id_list)} emails total.")

    emails = []
    for i, mid in enumerate(id_list, 1):
        status, data = conn.fetch(mid, "(RFC822)")
        if status != "OK":
            continue
        raw = data[0][1]
        msg = email.message_from_bytes(raw)

        msg_id = msg.get("Message-ID", f"unknown-{mid.decode()}")
        from_addr = decode_header_value(msg.get("From", ""))
        subject = decode_header_value(msg.get("Subject", ""))
        date_str = msg.get("Date", "")

        # Parse date
        try:
            from email.utils import parsedate_to_datetime
            msg_date = parsedate_to_datetime(date_str)
        except Exception:
            msg_date = None

        # Extract attachments
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                cd = part.get("Content-Disposition", "")
                if "attachment" in cd.lower() or part.get_content_maintype() == "application":
                    fname = decode_filename(part)
                    if fname:
                        skip, reason = should_skip(fname)
                        size = len(part.get_payload(decode=True) or b"")
                        attachments.append({
                            "filename": fname,
                            "size_kb": round(size / 1024, 1),
                            "skipped": skip,
                            "skip_reason": reason,
                        })

        emails.append({
            "message_id": msg_id,
            "imap_uid": mid.decode(),
            "from": from_addr,
            "subject": subject,
            "date": msg_date.isoformat() if msg_date else date_str,
            "date_obj": msg_date,
            "attachments": attachments,
        })

        if i % 10 == 0:
            print(f"   Scanned {i}/{len(id_list)} emails...")

    conn.logout()
    print(f"   Done. {len(emails)} emails scanned.\n")
    return emails


# ─── Master.xlsx Scanner ─────────────────────────────────────────────────────

def scan_master(config):
    """Read master.xlsx and group records by source filename."""
    # Try common paths
    master_path = None
    candidates = [
        config.get("output", {}).get("master_path", ""),
        config.get("master_path", ""),
        "output/master.xlsx",
        "master.xlsx",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            master_path = c
            break

    if not master_path:
        print("⚠️  master.xlsx not found! Tried:", candidates)
        return pd.DataFrame(), {}

    print(f"📊 Reading {master_path}...")
    df = pd.read_excel(master_path, dtype=str)
    print(f"   {len(df)} total records in master.")

    # Group by source filename
    source_col = "Источник файла"
    by_source = {}
    if source_col in df.columns:
        for name, group in df.groupby(source_col):
            by_source[name] = len(group)
        print(f"   {len(by_source)} unique source files.\n")
    else:
        print(f"   ⚠️  Column '{source_col}' not found. Columns: {list(df.columns)}\n")

    return df, by_source


# ─── Processed IDs Scanner ───────────────────────────────────────────────────

def load_processed_ids(path="processed_ids.json"):
    if not os.path.exists(path):
        print(f"⚠️  {path} not found — assuming no messages processed.\n")
        return set()
    with open(path, "r") as f:
        data = json.load(f)
    # Could be a list or dict
    if isinstance(data, list):
        ids = set(str(x) for x in data)
    elif isinstance(data, dict):
        ids = set(str(x) for x in data.keys())
    else:
        ids = set()
    print(f"📋 Loaded {len(ids)} processed message IDs from {path}.\n")
    return ids


# ─── Cross-Reference & Report ────────────────────────────────────────────────

def build_report(emails, master_df, by_source, processed_ids):
    """Cross-reference inbox vs master and build diagnostic report."""

    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {},
        "by_sender": defaultdict(lambda: {"emails": 0, "attachments": 0, "processable": 0, "skipped": 0}),
        "inbox_attachments": [],   # All non-skipped attachments from inbox
        "missing": [],             # In inbox but NOT in master
        "matched": [],             # In inbox AND in master
        "orphaned_sources": [],    # In master but not found in inbox scan
        "unprocessed_emails": [],  # Message IDs not in processed_ids.json
        "errors": [],
    }

    total_emails = len(emails)
    total_attachments = 0
    total_skipped = 0
    total_processable = 0

    all_inbox_filenames = set()

    # Build reverse lookup: strip UID prefix from master sources
    # Master stores "1438_p41238439.xlsx", inbox has "p41238439.xlsx"
    # Also handles Zetta extracted files like "11140-2_ММВП-..." (no UID prefix)
    source_by_raw_name = {}
    for source_name, count in by_source.items():
        source_by_raw_name[source_name] = count
        # Try stripping numeric UID prefix: "1438_filename.xlsx" -> "filename.xlsx"
        if '_' in source_name:
            parts = source_name.split('_', 1)
            if parts[0].isdigit():
                raw_name = parts[1]
                # Sum if multiple UIDs map to same raw name
                source_by_raw_name[raw_name] = source_by_raw_name.get(raw_name, 0) + count

    for em in emails:
        sender = em["from"]
        sender_short = re.search(r"[\w.-]+@[\w.-]+", sender)
        sender_short = sender_short.group(0) if sender_short else sender

        report["by_sender"][sender_short]["emails"] += 1

        # Check if this email was processed
        is_processed = em["message_id"] in processed_ids or em["imap_uid"] in processed_ids
        if not is_processed:
            report["unprocessed_emails"].append({
                "message_id": em["message_id"],
                "imap_uid": em["imap_uid"],
                "from": sender_short,
                "subject": em["subject"][:80],
                "date": em["date"],
            })

        for att in em["attachments"]:
            total_attachments += 1
            report["by_sender"][sender_short]["attachments"] += 1

            if att["skipped"]:
                total_skipped += 1
                report["by_sender"][sender_short]["skipped"] += 1
                continue

            total_processable += 1
            report["by_sender"][sender_short]["processable"] += 1
            all_inbox_filenames.add(att["filename"])

            # Look up in master (try exact match first, then stripped UID match)
            records_in_master = source_by_raw_name.get(att["filename"], 0)

            entry = {
                "filename": att["filename"],
                "size_kb": att["size_kb"],
                "from": sender_short,
                "email_date": em["date"],
                "email_subject": em["subject"][:80],
                "message_id": em["message_id"],
                "email_processed": is_processed,
                "records_in_master": records_in_master,
            }
            report["inbox_attachments"].append(entry)

            if records_in_master > 0:
                report["matched"].append(entry)
            else:
                report["missing"].append(entry)

    # Find orphaned sources (in master but not in current inbox scan)
    for source_name, count in by_source.items():
        # Check both exact match and UID-stripped match
        raw_name = source_name
        if '_' in source_name:
            parts = source_name.split('_', 1)
            if parts[0].isdigit():
                raw_name = parts[1]

        if source_name not in all_inbox_filenames and raw_name not in all_inbox_filenames:
            report["orphaned_sources"].append({
                "filename": source_name,
                "records_in_master": count,
                "note": "In master.xlsx but not found in inbox (may be from older period or Zetta sub-file)",
            })

    report["summary"] = {
        "total_emails_in_inbox": total_emails,
        "total_attachments": total_attachments,
        "skipped_by_rules": total_skipped,
        "processable_attachments": total_processable,
        "matched_in_master": len(report["matched"]),
        "missing_from_master": len(report["missing"]),
        "orphaned_in_master": len(report["orphaned_sources"]),
        "unprocessed_email_count": len(report["unprocessed_emails"]),
        "master_total_records": len(master_df),
        "master_unique_sources": len(by_source),
    }

    # Convert defaultdict for JSON
    report["by_sender"] = dict(report["by_sender"])

    return report


# ─── Terminal Output ──────────────────────────────────────────────────────────

def print_report(report):
    """Print a human-readable diagnostic report to terminal."""

    s = report["summary"]
    print("=" * 78)
    print("  📋 EMAIL PROCESSOR DIAGNOSTIC REPORT")
    print(f"  Generated: {report['generated_at']}")
    print("=" * 78)

    # ── Summary
    print("\n── SUMMARY ─────────────────────────────────────────────────────")
    print(f"  Emails in inbox:          {s['total_emails_in_inbox']}")
    print(f"  Total attachments:        {s['total_attachments']}")
    print(f"  Skipped (rules):          {s['skipped_by_rules']}")
    print(f"  Processable attachments:  {s['processable_attachments']}")
    print(f"  ✅ Matched in master:      {s['matched_in_master']}")
    print(f"  ❌ MISSING from master:    {s['missing_from_master']}")
    print(f"  📦 Orphaned in master:     {s['orphaned_in_master']}")
    print(f"  ⏭️  Unprocessed emails:     {s['unprocessed_email_count']}")
    print(f"  Master total records:     {s['master_total_records']}")
    print(f"  Master unique sources:    {s['master_unique_sources']}")

    # ── By Sender
    print("\n── BY SENDER ───────────────────────────────────────────────────")
    print(f"  {'Sender':<40} {'Emails':>6} {'Attach':>6} {'Process':>7} {'Skip':>5}")
    print("  " + "─" * 64)
    for sender, data in sorted(report["by_sender"].items()):
        print(f"  {sender:<40} {data['emails']:>6} {data['attachments']:>6} {data['processable']:>7} {data['skipped']:>5}")

    # ── Missing (THE MAIN THING)
    if report["missing"]:
        print("\n── ❌ MISSING FROM MASTER (inbox file → 0 records) ──────────────")
        for m in report["missing"]:
            proc_mark = "✅" if m["email_processed"] else "⏭️"
            print(f"  {proc_mark} {m['filename']}")
            print(f"     From: {m['from']}  |  Date: {m['email_date']}")
            print(f"     Size: {m['size_kb']} KB  |  Subject: {m['email_subject']}")
            print()
    else:
        print("\n── ✅ NO MISSING FILES — all inbox attachments matched master ──")

    # ── Matched
    if report["matched"]:
        print("\n── ✅ MATCHED (inbox file → records in master) ─────────────────")
        for m in report["matched"]:
            print(f"  ✅ {m['filename']}  →  {m['records_in_master']} records")

    # ── Unprocessed emails
    if report["unprocessed_emails"]:
        print("\n── ⏭️ UNPROCESSED EMAILS (not in processed_ids.json) ───────────")
        for u in report["unprocessed_emails"]:
            print(f"  📧 UID {u['imap_uid']}  |  {u['from']}  |  {u['date']}")
            print(f"     Subject: {u['subject']}")
            print()

    # ── Orphaned
    if report["orphaned_sources"]:
        print("\n── 📦 ORPHANED SOURCES (in master but not in inbox scan) ───────")
        for o in report["orphaned_sources"]:
            print(f"  📦 {o['filename']}  →  {o['records_in_master']} records")

    print("\n" + "=" * 78)
    print("  END OF DIAGNOSTIC REPORT")
    print("=" * 78)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Email Processor Diagnostic Tool")
    parser.add_argument("--days", type=int, default=None, help="Override days_back")
    parser.add_argument("--json", action="store_true", help="Also save diagnostic.json")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    # Load config
    if not os.path.exists(args.config):
        print(f"❌ Config file not found: {args.config}")
        sys.exit(1)
    config = load_config(args.config)

    # Determine days_back
    days_back = args.days
    if days_back is None:
        days_back = config.get("days_back", config.get("imap", {}).get("days_back", 2))
    print(f"⚙️  Using days_back = {days_back}")

    # Phase 1: Scan inbox
    emails = scan_inbox(config, days_back)

    # Phase 2: Scan master.xlsx
    master_df, by_source = scan_master(config)

    # Phase 3: Load processed IDs
    processed_ids = load_processed_ids()

    # Phase 4: Cross-reference
    report = build_report(emails, master_df, by_source, processed_ids)

    # Phase 5: Output
    print_report(report)

    # Always save JSON (for Claude to analyze)
    json_path = "diagnostic_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 JSON report saved to: {json_path}")
    print("   → Paste this JSON back to Claude for analysis.\n")


if __name__ == "__main__":
    main()
