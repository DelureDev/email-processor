"""
Email Notifier — sends processing reports via SMTP.
Attaches the master xlsx and includes a summary of what was processed.
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

logger = logging.getLogger(__name__)


def send_report(config: dict, stats: dict):
    """
    Send processing report via email.

    Args:
        config: full config dict
        stats: {
            'total_records': int,
            'files_processed': int,
            'files_skipped': int,
            'by_company': dict[str, int],
            'errors': list[str],
            'master_path': str,
        }
    """
    smtp_cfg = config.get('smtp', {})
    if not smtp_cfg.get('enabled', False):
        logger.debug("SMTP not enabled, skipping report")
        return

    if smtp_cfg.get('only_if_new_records', True) and stats.get('total_records', 0) == 0:
        # Still send if there are unknown files or errors
        if not stats.get('unknown_files') and not stats.get('errors'):
            logger.info("No new records, skipping email report")
            return

    recipients = smtp_cfg.get('recipients', [])
    if not recipients:
        logger.warning("No recipients configured for email report")
        return

    try:
        msg = _build_message(smtp_cfg, stats)
        _send(smtp_cfg, recipients, msg)
        logger.info(f"Report sent to {', '.join(recipients)}")
    except Exception as e:
        logger.error(f"Failed to send report: {e}", exc_info=True)


def _build_message(smtp_cfg: dict, stats: dict) -> MIMEMultipart:
    """Build email message with report and attachment."""
    msg = MIMEMultipart()
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    total = stats.get('total_records', 0)

    msg['From'] = smtp_cfg['from_address']
    msg['To'] = ', '.join(smtp_cfg['recipients'])
    msg['Subject'] = f"Обработка списков ДМС — {now} — {total} записей"

    # Build HTML body
    body = f"""<html><body style="font-family: Arial, sans-serif;">
<h2>Отчёт обработки списков ДМС</h2>
<p><strong>Дата:</strong> {now}</p>
<p><strong>Новых записей:</strong> {total}</p>
<p><strong>Файлов обработано:</strong> {stats.get('files_processed', 0)}</p>
<p><strong>Файлов пропущено:</strong> {stats.get('files_skipped', 0)}</p>
"""

    # By company breakdown
    by_company = stats.get('by_company', {})
    if by_company:
        body += "<h3>По страховым компаниям:</h3><table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse;'>"
        body += "<tr style='background: #2F5496; color: white;'><th>Компания</th><th>Записей</th></tr>"
        for company, count in sorted(by_company.items(), key=lambda x: -x[1]):
            body += f"<tr><td>{company}</td><td align='center'>{count}</td></tr>"
        body += "</table>"

    # Errors
    errors = stats.get('errors', [])
    if errors:
        body += "<h3 style='color: #dc2626;'>⚠ Ошибки:</h3><ul>"
        for err in errors[:20]:
            body += f"<li>{err}</li>"
        body += "</ul>"

    # Unknown files — IMPORTANT: these need attention
    unknown = stats.get('unknown_files', [])
    if unknown:
        body += "<h3 style='color: #ea580c;'>❓ Нераспознанные файлы:</h3>"
        body += "<p style='color: #666; font-size: 13px;'>Эти файлы не подошли ни под один известный формат. Возможно, новая страховая компания или изменённый формат.</p>"
        body += "<ul>"
        for f in unknown[:20]:
            body += f"<li><code>{f}</code></li>"
        body += "</ul>"

    # Empty files
    empty = stats.get('empty_files', [])
    if empty:
        body += "<h3 style='color: #a3a3a3;'>📭 Файлы без записей:</h3><ul>"
        for f in empty[:20]:
            body += f"<li><code>{f}</code></li>"
        body += "</ul>"

    # Duplicates
    dupes = stats.get('duplicates_removed', 0)
    if dupes > 0:
        body += f"<p style='color: #666; font-size: 13px;'>Дубликатов отфильтровано: {dupes}</p>"

    body += "<p style='color: gray; font-size: 12px;'>Мастер-файл во вложении.</p>"
    body += "</body></html>"

    msg.attach(MIMEText(body, 'html', 'utf-8'))

    # Attach master xlsx
    master_path = stats.get('master_path', '')
    if master_path and os.path.exists(master_path):
        with open(master_path, 'rb') as f:
            part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            basename = os.path.basename(master_path)
            part.add_header('Content-Disposition', f'attachment; filename="{basename}"')
            msg.attach(part)

    return msg


def _send(smtp_cfg: dict, recipients: list[str], msg: MIMEMultipart):
    """Send the email via SMTP."""
    server = smtp_cfg['server']
    port = smtp_cfg.get('port', 465)
    use_ssl = smtp_cfg.get('use_ssl', True)
    username = smtp_cfg['username']
    password = smtp_cfg['password']

    if use_ssl:
        with smtplib.SMTP_SSL(server, port) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg, to_addrs=recipients)
    else:
        with smtplib.SMTP(server, port) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg, to_addrs=recipients)
