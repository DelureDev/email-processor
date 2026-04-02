"""Tests for notifier.py"""


def test_send_report_filters_empty_recipients(tmp_path):
    """Empty string recipients must be filtered out before SMTP send."""
    from unittest.mock import patch
    config = {
        'smtp': {
            'enabled': True,
            'host': 'localhost',
            'port': 587,
            'username': 'test@test.com',
            'password': 'pass',
            'from_address': 'test@test.com',
            'recipients': ['real@test.com', '', '   '],
            'only_if_new_records': False,
        }
    }
    stats = {
        'total_records': 1, 'files_processed': 1, 'files_skipped': 0,
        'by_company': {}, 'errors': [], 'unknown_files': [],
        'unmatched_clinics': [], 'missing_comments': [], 'skipped_files': [],
        'new_records': [], 'master_path': str(tmp_path / 'master.xlsx'),
    }
    with patch('notifier._send') as mock_send:
        from notifier import send_report
        send_report(config, stats)
        call_args = mock_send.call_args
        recipients_used = call_args[0][1]
        assert '' not in recipients_used
        assert '   ' not in recipients_used
        assert 'real@test.com' in recipients_used
