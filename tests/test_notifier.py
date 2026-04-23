"""Tests for notifier.py"""
from notifier import send_report


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
        send_report(config, stats)
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        recipients_used = call_args[0][1]
        assert '' not in recipients_used
        assert '   ' not in recipients_used
        assert 'real@test.com' in recipients_used


def test_smtp_failure_recorded_in_stats_errors(tmp_path):
    """Regression: SMTP exception must populate stats['errors'] so healthcheck flips red."""
    from unittest.mock import patch
    import smtplib
    config = {
        'smtp': {
            'enabled': True,
            'host': 'localhost',
            'port': 587,
            'username': 'test@test.com',
            'password': 'pass',
            'from_address': 'test@test.com',
            'recipients': ['real@test.com'],
            'only_if_new_records': False,
        }
    }
    stats = {
        'total_records': 1, 'files_processed': 1, 'files_skipped': 0,
        'by_company': {}, 'errors': [], 'unknown_files': [],
        'unmatched_clinics': [], 'missing_comments': [], 'skipped_files': [],
        'new_records': [], 'master_path': str(tmp_path / 'master.xlsx'),
    }
    with patch('notifier._send', side_effect=smtplib.SMTPAuthenticationError(535, b'bad creds')):
        send_report(config, stats)

    assert len(stats['errors']) == 1
    assert 'smtp' in stats['errors'][0].lower()


def test_smtp_status_ok_on_success(tmp_path):
    """stats['smtp_status'] must be 'OK' when send succeeds."""
    from unittest.mock import patch
    config = {
        'smtp': {
            'enabled': True, 'host': 'localhost', 'port': 587,
            'username': 'test@test.com', 'password': 'pass',
            'from_address': 'test@test.com',
            'recipients': ['real@test.com'],
            'only_if_new_records': False,
        }
    }
    stats = {
        'total_records': 1, 'files_processed': 1, 'files_skipped': 0,
        'by_company': {}, 'errors': [], 'unknown_files': [],
        'unmatched_clinics': [], 'missing_comments': [], 'skipped_files': [],
        'new_records': [], 'master_path': str(tmp_path / 'master.xlsx'),
        'smtp_status': 'SKIP',
    }
    with patch('notifier._send'):
        send_report(config, stats)

    assert stats['smtp_status'] == 'OK'


def test_smtp_status_fail_on_exception(tmp_path):
    """stats['smtp_status'] must be 'FAIL' when send raises."""
    from unittest.mock import patch
    import smtplib
    config = {
        'smtp': {
            'enabled': True, 'host': 'localhost', 'port': 587,
            'username': 'test@test.com', 'password': 'pass',
            'from_address': 'test@test.com',
            'recipients': ['real@test.com'],
            'only_if_new_records': False,
        }
    }
    stats = {
        'total_records': 1, 'files_processed': 1, 'files_skipped': 0,
        'by_company': {}, 'errors': [], 'unknown_files': [],
        'unmatched_clinics': [], 'missing_comments': [], 'skipped_files': [],
        'new_records': [], 'master_path': str(tmp_path / 'master.xlsx'),
        'smtp_status': 'SKIP',
    }
    with patch('notifier._send', side_effect=smtplib.SMTPAuthenticationError(535, b'bad')):
        send_report(config, stats)

    assert stats['smtp_status'] == 'FAIL'


def test_smtp_status_skip_when_disabled(tmp_path):
    """stats['smtp_status'] must remain 'SKIP' when smtp.enabled is False."""
    config = {'smtp': {'enabled': False}}
    stats = {
        'total_records': 1, 'errors': [], 'unknown_files': [],
        'smtp_status': 'SKIP',
    }
    send_report(config, stats)

    assert stats['smtp_status'] == 'SKIP'
