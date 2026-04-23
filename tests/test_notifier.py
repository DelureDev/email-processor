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


class TestBuildLogTailHtml:
    def test_returns_none_when_file_missing(self, tmp_path):
        from notifier import _build_log_tail_html
        from datetime import datetime
        result = _build_log_tail_html(str(tmp_path / 'nope.log'), datetime.now())
        assert result is None

    def test_returns_none_when_no_matching_lines(self, tmp_path):
        from notifier import _build_log_tail_html
        from datetime import datetime
        log = tmp_path / 'p.log'
        log.write_text(
            "2026-04-23 10:00:00,000 [INFO] main: old line\n"
            "2026-04-23 10:00:01,000 [INFO] main: older line\n",
            encoding='utf-8'
        )
        result = _build_log_tail_html(str(log), datetime(2026, 4, 23, 15, 0, 0))
        assert result is None

    def test_returns_details_block_with_current_run_lines(self, tmp_path):
        from notifier import _build_log_tail_html
        from datetime import datetime
        log = tmp_path / 'p.log'
        log.write_text(
            "2026-04-23 10:00:00,000 [INFO] main: old\n"
            "2026-04-23 15:30:05,000 [INFO] main: this run started\n"
            "2026-04-23 15:30:10,000 [ERROR] writer: problem\n",
            encoding='utf-8'
        )
        result = _build_log_tail_html(str(log), datetime(2026, 4, 23, 15, 30, 0))
        assert result is not None
        assert '<details' in result
        assert 'this run started' in result
        assert 'problem' in result
        assert 'old' not in result

    def test_truncates_at_size_cap(self, tmp_path):
        from notifier import _build_log_tail_html
        from datetime import datetime
        log = tmp_path / 'p.log'
        lines = [f"2026-04-23 15:30:{i % 60:02d},000 [INFO] main: line{i} " + ("x" * 200)
                 for i in range(300)]
        log.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        result = _build_log_tail_html(str(log), datetime(2026, 4, 23, 15, 29, 0), max_bytes=10_000)
        assert result is not None
        assert 'предыдущие строки пропущены' in result
        assert len(result) < 20_000

    def test_html_escapes_angle_brackets(self, tmp_path):
        from notifier import _build_log_tail_html
        from datetime import datetime
        log = tmp_path / 'p.log'
        log.write_text(
            "2026-04-23 15:30:05,000 [ERROR] main: bad <tag> & stuff\n",
            encoding='utf-8'
        )
        result = _build_log_tail_html(str(log), datetime(2026, 4, 23, 15, 30, 0))
        assert '&lt;tag&gt;' in result
        assert '<tag>' not in result
