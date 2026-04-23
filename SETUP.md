# Setup Guide

Deploy the email-processor pipeline on a clean Linux VM.

## Prerequisites

- Linux VM (tested on Ubuntu/Debian), Moscow timezone (`timedatectl set-timezone Europe/Moscow`)
- Python 3.10+ (3.12 preferred)
- LibreOffice (for `.xls → .xlsx` conversion)
- Network access to: `imap.yandex.ru:993`, `smtp.yandex.ru:465`, `hc-ping.com`, and your file server (if using CSV export)

## 1. Install system dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip libreoffice-calc cifs-utils
```

## 2. Clone and install

```bash
cd /home/adminos
git clone <your-repo-url> email-processor
cd email-processor
pip3 install -r requirements.txt
```

## 3. Configure credentials

Copy the templates and fill in credentials:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

Edit `.env`:

```bash
export IMAP_PASSWORD="your-yandex-app-password"
export SMTP_PASSWORD="your-yandex-app-password"
```

Edit `config.yaml`:
- Fill in IMAP/SMTP `username`. Leave passwords as `${IMAP_PASSWORD}` / `${SMTP_PASSWORD}` — they're resolved from env at runtime.
- Set `imap.folder` (usually `INBOX`) and `imap.processed_folder` (e.g. `"Обработанные"`).
- Populate `imap.allowed_senders` — use the insurer domains from `SENDER_FORMAT_MAP` in `detector.py` to prevent spoofing / overmatching.
- Set `output.master_file` (e.g. `./output/master.xlsx`).
- Set `output.csv_export_folder` if using a network share (see section 5).
- Set `healthcheck_url` if using healthchecks.io.

**Never commit `config.yaml`** — it's gitignored by default.

## 4. Create runtime directories

```bash
mkdir -p output temp logs quarantine
```

These are also created automatically on first run, but pre-creating them avoids permission surprises.

## 5. Mount network share (optional, for 1C CSV export)

Edit `/etc/fstab`:

```
//10.10.10.21/dms_reports /mnt/storage cifs username=<user>,password=<pass>,domain=<dom>,iocharset=utf8,uid=adminos,_netdev,vers=2.1 0 0
```

Notes:
- Use `vers=2.1` or `vers=3.0` depending on your Windows server's SMB policy. `vers=2.0` may be rejected by modern Windows security policies (we hit this on 2026-04-23).
- `_netdev` ensures mount waits for network.
- `iocharset=utf8` is required for Cyrillic filenames.

```bash
sudo mkdir /mnt/storage
sudo mount -a
ls /mnt/storage  # verify
```

## 6. First-run smoke test

```bash
set -a; source .env; set +a
python3 main.py --dry-run
```

Expected: no errors; records counted but not written to `master.xlsx`.

If Zetta zips fail with "no passwords": expected on first run if the monthly password email isn't in INBOX. See `RECOVERY.md` section 6.

## 7. Schedule via cron

Edit `crontab -e`:

```
*/30 * * * * cd /home/adminos/email-processor && set -a; source .env; set +a; python3 main.py 2>&1 | logger -t email-processor
```

Adjust the interval to taste. Every 30 minutes is typical; daily is also fine since `days_back: 3` catches any missed runs.

The pipeline's pidfile lock (`./logs/main.lock`) prevents concurrent cron + manual runs from duplicating work.

## 8. Schedule daily backups

```
0 6 * * * cd /home/adminos/email-processor && bash backup.sh
```

Creates a timestamped tar.gz in `/home/adminos/backups/email-processor/` every morning at 6am. Keeps the 10 most recent.

## 9. Verification

After the first real run:

```bash
tail -50 logs/processor.log       # should end with "Records: N" summary
ls -la output/master.xlsx         # file exists and grew
cat logs/audit.log                # password operations logged (no passwords in clear)
```

Email report should arrive at the addresses in `smtp.recipients`.

If configured: https://healthchecks.io/ dashboard should show green ping.

## Environment variables reference

| Variable | Purpose | Required |
|----------|---------|----------|
| `IMAP_PASSWORD` | Yandex app password for IMAP login | Yes |
| `SMTP_PASSWORD` | Yandex app password for SMTP send | Yes |

Unresolved `${VAR}` placeholders in `config.yaml` raise `ValueError` at startup — no silent fallback to literal strings (prevents Yandex account lockout from repeated failed login with `"${IMAP_PASSWORD}"` as password).

The healthcheck URL goes directly in `config.yaml` as `healthcheck_url: "https://hc-ping.com/your-uuid"` — it is not read from an env var. Leave empty to disable.

## Next steps

- Read `RECOVERY.md` for failure playbooks.
- Review `CLAUDE.md` for architecture context.
- Set up healthchecks.io monitoring (free tier: https://healthchecks.io/).
