"""Verify IMAP SEARCH retry behavior."""
from unittest.mock import MagicMock
import pytest
from fetcher import IMAPFetcher


def _make_fetcher_with_fake_imap(search_responses):
    config = {
        'imap': {'server': 's', 'port': 993, 'username': 'u', 'password': 'p',
                 'folder': 'INBOX', 'processed_folder': ''},
        'processing': {'temp_folder': './temp', 'processed_ids_file': './tmp.db'},
    }
    fetcher = IMAPFetcher(config, dry_run=True)
    fetcher.mail = MagicMock()
    fetcher.mail.uid = MagicMock(side_effect=search_responses)
    return fetcher


def test_main_search_retries_on_not_ok():
    """Main SEARCH must retry up to 3 times before giving up."""
    responses = [
        ('NO', [b'[UNAVAILABLE] Backend error']),
        ('NO', [b'[UNAVAILABLE] Backend error']),
        ('OK', [b'']),
    ]
    fetcher = _make_fetcher_with_fake_imap(responses)
    fetcher._load_processed_ids = lambda: set()
    fetcher.processed_ids = set()
    fetcher._initial_ids = set()
    fetcher.mail.select = MagicMock(return_value=('OK', [b'0']))
    from fetcher import _search_with_retry
    typ, data = _search_with_retry(fetcher.mail, None, '(SINCE 01-Jan-2026)', attempts=3, delay=0)
    assert typ == 'OK'
    assert fetcher.mail.uid.call_count == 3


def test_password_fetch_handles_expunged_uid():
    """FETCH returning [None] (expunged UID) must not crash the password loop."""
    from unittest.mock import MagicMock
    from fetcher import _safe_fetch_rfc822
    mail = MagicMock()
    mail.uid = MagicMock(return_value=('OK', [None]))
    result = _safe_fetch_rfc822(mail, '42', attempts=1, delay=0)
    assert result is None


def test_safe_fetch_returns_message_bytes_on_success():
    """Happy path: helper returns raw message bytes from a well-formed FETCH response."""
    from unittest.mock import MagicMock
    from fetcher import _safe_fetch_rfc822
    mail = MagicMock()
    mail.uid = MagicMock(return_value=('OK', [(b'header', b'raw-rfc822-bytes')]))
    result = _safe_fetch_rfc822(mail, '42', attempts=1, delay=0)
    assert result == b'raw-rfc822-bytes'


def test_safe_fetch_retries_on_non_ok_status():
    """FETCH must retry up to `attempts` times on non-OK status."""
    from unittest.mock import MagicMock
    from fetcher import _safe_fetch_rfc822
    mail = MagicMock()
    mail.uid = MagicMock(side_effect=[
        ('NO', [b'transient']),
        ('OK', [(b'h', b'ok-body')]),
    ])
    result = _safe_fetch_rfc822(mail, '42', attempts=3, delay=0)
    assert result == b'ok-body'
    assert mail.uid.call_count == 2
