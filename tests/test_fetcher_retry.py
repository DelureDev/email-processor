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


def test_expired_monthly_password_not_marked_processed():
    """A monthly password whose valid_to is in the past must not be marked processed."""
    from datetime import datetime
    from fetcher import _should_mark_monthly_processed

    today = datetime(2026, 4, 23)
    # Expired (March 2026)
    assert not _should_mark_monthly_processed({'valid_to': '31.03.2026'}, today=today)
    # Current (April 2026)
    assert _should_mark_monthly_processed({'valid_to': '30.04.2026'}, today=today)
    # Future
    assert _should_mark_monthly_processed({'valid_to': '31.05.2026'}, today=today)
    # Missing valid_to — fail safe: don't mark, retry next run
    assert not _should_mark_monthly_processed({}, today=today)
    # Malformed valid_to — fail safe
    assert not _should_mark_monthly_processed({'valid_to': 'garbage'}, today=today)
    # None value — fail safe
    assert not _should_mark_monthly_processed({'valid_to': None}, today=today)


def test_imap_utf7_encode_handles_cyrillic():
    """Known folder names must round-trip through imap_utf7_encode correctly."""
    from fetcher import imap_utf7_encode
    # ASCII: pass through unchanged
    assert imap_utf7_encode('INBOX') == 'INBOX'
    # Cyrillic: must start with '&' and end with '-' per RFC 3501 modified UTF-7
    encoded = imap_utf7_encode('Обработанные')
    assert encoded.startswith('&')
    assert encoded.endswith('-')
    # Ampersand must be escaped as '&-' per RFC 3501
    assert imap_utf7_encode('A&B') == 'A&-B'
