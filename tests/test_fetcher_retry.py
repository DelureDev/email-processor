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
