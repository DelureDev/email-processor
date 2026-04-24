# Recovery Runbook

Step-by-step playbooks for the most likely production incidents. All commands assume you are SSH'd into the VM as `adminos` in `/home/adminos/email-processor`.

## 1. Yandex IMAP account locked or rejecting login

**Symptom:** Logs show `imaplib.error: AUTHENTICATIONFAILED` or `LOGIN failed` repeatedly; cron runs produce zero records.

**Investigate:**
```bash
tail -30 logs/processor.log
```

Look for whether the literal string `${IMAP_PASSWORD}` appears in the error (env var not set at cron time) or an actual password was tried and rejected.

**If env var not set (look for `Unresolved environment variable(s)` in log):**
```bash
echo $IMAP_PASSWORD   # verify in the shell where you run main.py
# If empty, source .env:
set -a; source .env; set +a
python3 main.py --dry-run
```

For cron, make sure the crontab line sources `.env` before running python:
```
*/30 * * * * cd /home/adminos/email-processor && set -a; source .env; set +a; python3 main.py 2>&1 | logger -t email-processor
```

**If password actually wrong (Yandex locked the account):**
1. Go to Yandex security settings → app passwords.
2. Revoke old app password, generate new one.
3. Update `/home/adminos/email-processor/.env`:
   ```
   export IMAP_PASSWORD="new-app-password"
   ```
4. `set -a; source .env; set +a` in a fresh shell.
5. Test: `python3 main.py --dry-run`.

Wait 5–10 minutes after repeated failed logins before retrying — Yandex has a cooldown.

## 2. Network share (CSV export) failing

**Symptom:** Email report shows `network_status=FAIL` or `SMB ... CSV failed: ...` or `Network share not reachable`; daily CSV not appearing on the share.

First check which mode is in use:
```bash
grep csv_export_folder config.yaml
```
- Starts with `\\` or `//` → **Option A below** (userspace SMB)
- Plain local path like `/mnt/storage` → **Option B below** (kernel CIFS mount)

### Option A: Userspace SMB (UNC mode, v1.11.0+)

**Investigate:**
```bash
tail -80 logs/processor.log | grep -iE 'smb|error|failed|network'
```

**Common causes:**

- **Wrong / rotated password.** Log shows `STATUS_LOGON_FAILURE`, `STATUS_MORE_PROCESSING_REQUIRED` loops, or `AuthenticationFailed`:
  ```bash
  echo $SMB_PASSWORD      # verify env var is set in your shell
  # For cron: check the SMB_PASSWORD= line at top of `crontab -l`
  ```
  Update `.env` or crontab with the new password, re-run.

- **Server unreachable** (error like `[Errno 113] No route to host` or `ConnectionRefusedError`):
  ```bash
  ping 10.10.10.21
  timeout 3 bash -c "</dev/tcp/10.10.10.21/445" && echo "port 445 OK" || echo "port 445 closed"
  ```

- **Server wedged** (`smbprotocol.exceptions.SMBResponseException`, `STATUS_IO_TIMEOUT`, or our 30s timeout fires):
  ```bash
  # Confirm userspace SMB can negotiate (bypasses any kernel mount state):
  sudo bash diag_smb.sh > ~/smb-diag-$(date +%Y%m%d-%H%M).log
  cat ~/smb-diag-*.log
  ```
  Steps 3 and 4 test `smbprotocol`-equivalent paths. If those work but our exports don't, our config is wrong (credentials, UNC path); if those also fail, the server itself has an issue — forward the log to whoever owns it.

**Manual backfill with the correct file:**
```bash
python3 build_local_daily_csv.py   # writes records_YYYY-MM-DD.csv locally from master.xlsx
# When share is reachable:
timeout 30 cp records_YYYY-MM-DD.csv /mnt/storage/   # if mount still available
# Or delete/resend via the pipeline on the next cron run — `_export_via_smb` auto-heals corrupt files.
```

### Option B: Legacy kernel CIFS mount

**Investigate:**
```bash
ls /mnt/storage
# If hangs or errors, check mount:
mount | grep storage
sudo dmesg | grep -i cifs | tail -10
```

**Common causes:**

- **SMB version mismatch (policy update).** Look for `STATUS_LOGON_FAILURE` in dmesg → try:
  ```bash
  sudo sed -i 's/vers=2.0/vers=2.1/' /etc/fstab
  sudo umount -l /mnt/storage
  sudo mount /mnt/storage
  ls /mnt/storage
  ```
  We hit this on 2026-04-23 — Windows policy forced minimum SMB 2.1. If 2.1 still fails, try 3.0.

- **D-state zombie processes pinning the mount** (we hit this multiple times 2026-04-24):
  ```bash
  ps -eo pid,etime,stat,cmd | grep -E 'python|mount\.cifs' | grep -v grep
  ```
  Anything with `D` in STAT is unkillable — `umount -l` + `mount` usually clears. If not, reboot.

- **Server reboot or credentials changed:**
  ```bash
  sudo mount -a -v
  ```
  Verbose output shows the exact authentication error.

- **DNS / network:**
  ```bash
  ping 10.10.10.21
  ```

**Consider migrating to Option A** if this incident keeps recurring — userspace SMB makes the entire class of mount-layer failures impossible. See `SETUP.md` section 5 for the 5-line config change.

**Pipeline impact (both options):** only CSV export is affected. Records are still written to local `master.xlsx`. Once the share is back, the next run auto-resumes the CSV export; Option A additionally auto-heals corrupt files (headerless / BOM-less) left by prior failed runs.

## 3. `master.xlsx` corrupted or lost

**Symptom:** Pipeline crashes with `BadZipFile: File is not a zip file` or similar at `load_existing_keys`.

**Recover from inline backup (`.bak`):**
```bash
ls -la output/master.xlsx*
# If master.xlsx.bak exists and is recent:
cp output/master.xlsx.bak output/master.xlsx
# Verify:
python3 -c "import pandas as pd; df = pd.read_excel('output/master.xlsx'); print(len(df), 'records')"
```

The `.bak` file is written at the start of every successful `write_batch_to_master` run. If the current run corrupted the main file, the `.bak` holds the previous-run state.

**If no `.bak` or `.bak` also corrupt — restore from tar.gz backup:**
```bash
ls /home/adminos/backups/email-processor/
# Pick the most recent known-good backup:
tar -xzf /home/adminos/backups/email-processor/backup_YYYY-MM-DD_HH-MM-SS.tar.gz -C /tmp/restore
cp /tmp/restore/email-processor/output/master.xlsx output/master.xlsx
rm -rf /tmp/restore
# Verify:
python3 -c "import pandas as pd; df = pd.read_excel('output/master.xlsx'); print(len(df), 'records')"
```

After restore, the next run will re-fetch recent emails and dedup against the restored state. Expect some records that were between the last backup and the corruption to be re-processed.

## 4. `processed_ids.db` corrupted

**Symptom:** Startup logs `sqlite3.DatabaseError: database is malformed`.

**Recover:** The database is a cache, not a primary data store — safe to delete.

```bash
rm processed_ids.db
python3 main.py --dry-run
```

The next run will:
- Re-fetch emails from the last `days_back` window (default 3 days).
- Dedup against `master.xlsx` prevents any duplicate records being written.
- Re-build `processed_ids.db` with the fresh message IDs.

## 5. Cron didn't run / missed a day

**Symptom:** Expected daily email report didn't arrive; healthcheck.io shows no recent ping.

**Investigate:**
```bash
grep CRON /var/log/syslog | grep email-processor | tail -10
# or if using journald:
journalctl -t email-processor -n 50
```

**If the job didn't fire at all:**
```bash
crontab -l                  # verify job is present
systemctl status cron       # verify daemon is running
```

**If the job ran but failed silently:**
```bash
tail -200 logs/processor.log
```

**Recover missed data:** The pipeline's `days_back: 3` auto-catches the last 3 days of email on the next run. For gaps longer than 3 days, temporarily raise `days_back` in `config.yaml` and run manually:

```bash
# Edit config.yaml: imap.days_back: 14 (or however many days to backfill)
python3 main.py
# Restore days_back: 3 after the catch-up run
```

## 6. Zetta ZIPs failing to extract (stale or rotated password)

**Symptom:** Email report shows `Zetta zip not extracted: <filename>` for every recent Zetta zip.

**Check the cache:**
```bash
cat zetta_password.json   # if present
```

**If cache shows validity window ending in a past month:**
The cache is stale. Delete it and rerun:
```bash
rm zetta_password.json
python3 main.py --dry-run
```

The next run will re-fetch the monthly password from IMAP. If the monthly password email hasn't arrived yet for this month (Zetta sometimes sends it late on the 1st), Zetta extraction will fail until it arrives — this is normal at the start of the month.

**If cache is current but zips still fail:**
Zetta may have rotated the password mid-month (rare). Delete the cache; the next monthly password email (or per-email password for new zips) will populate it with the new password.

**If you can't find the monthly password email:** it may have been filtered out. Run the diagnostic script:
```bash
python3 dump_zetta_password_email.py
```
This scans INBOX + the processed folder for `parollpu@zettains.ru` emails and shows what's available.

---

## Rolling back a bad release

```bash
git log --oneline -5
# Identify the last known-good tag:
git checkout v1.10.8   # or whichever
python3 main.py --dry-run     # verify
# Pipeline will now run under the old version
```

Note: rolling back code does NOT revert data in `master.xlsx`. Records already written stay. If a bad release wrote corrupted records, also restore `master.xlsx` per section 3.

To permanently return to a specific tag:
```bash
git reset --hard v1.10.8
# WARNING: destructive — only do this if you're sure. Consider a new branch first:
#   git checkout -b rollback-to-v1.10.8 v1.10.8
```

## Getting help

If none of the above solves the issue, collect diagnostics:
```bash
tar -czf diagnostics.tar.gz \
    logs/processor.log logs/audit.log \
    config.yaml clinics.yaml \
    diagnostic_report.json 2>/dev/null
```

and open a GitHub issue (strip credentials from `config.yaml` first — search for `password:` lines).
