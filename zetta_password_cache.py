"""Persistent cache for the Zetta monthly password.

Zetta sends ONE password valid for the entire month. Caching it locally means
the pipeline doesn't have to re-read it from IMAP every run, which makes
Zetta ZIP extraction immune to transient Yandex SEARCH failures.

Format: {"password": str, "valid_from": "DD.MM.YYYY", "valid_to": "DD.MM.YYYY"}
File is gitignored and written with mode 0600.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ('password', 'valid_from', 'valid_to')


def load(path: str, today: datetime | None = None) -> dict | None:
    """Load cached password. Returns None if missing, malformed, or expired.

    Fail-safe: on any parse error, returns None so the caller falls back to
    whatever upstream discovery mechanism it has (IMAP SEARCH).
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Zetta password cache at {path} is unreadable: {e}")
        return None
    if not all(k in data for k in _REQUIRED_KEYS):
        logger.warning(f"Zetta password cache at {path} missing required keys")
        return None
    if today is None:
        today = datetime.now()
    try:
        valid_dt = datetime.strptime(data['valid_to'], '%d.%m.%Y')
    except (ValueError, TypeError):
        logger.warning(f"Zetta password cache at {path} has invalid valid_to")
        return None
    if valid_dt.date() < today.date():
        logger.info(f"Zetta password cache at {path} expired ({data['valid_to']}), ignoring")
        return None
    return data


def save(path: str, password: str, valid_from: str, valid_to: str) -> None:
    """Write the cache with mode 0600 so only the owner can read it."""
    data = {'password': password, 'valid_from': valid_from, 'valid_to': valid_to}
    # Write to a tmp file then rename, so a crash mid-write doesn't corrupt cache
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows and some filesystems ignore chmod — not critical for correctness
        pass
    logger.info(f"Zetta password cache updated (valid {valid_from} - {valid_to})")
