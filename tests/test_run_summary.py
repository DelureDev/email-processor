"""Tests for run_summary.build_run_summary pure function."""
from datetime import datetime
import pytest

from run_summary import build_run_summary, compute_status


def _stats(**overrides):
    """Minimal stats dict matching make_stats() shape."""
    base = {
        'total_records': 0, 'files_processed': 0, 'files_skipped': 0,
        'duplicates_removed': 0, 'by_company': {}, 'errors': [],
        'unknown_files': [], 'skipped_files': [], 'empty_files': [],
        'new_records': [], 'monthly_records': [], 'master_path': '',
        'unmatched_clinics': [], 'missing_comments': [],
        'run_start': datetime(2026, 4, 23, 15, 30, 0),
        'smtp_status': 'SKIP', 'network_status': 'SKIP',
    }
    base.update(overrides)
    return base


class TestBuildRunSummary:
    def test_ok_all_zeros(self):
        line = build_run_summary(_stats(), status='OK', duration_s=5, mode='imap')
        assert line.startswith('[RUN_SUMMARY] ')
        assert 'status=OK' in line
        assert 'mode=imap' in line
        assert 'files=0' in line
        assert 'records=0' in line
        assert 'errors=0' in line
        assert 'unknown=0' in line
        assert 'skip_rule=0' in line
        assert 'clinic_miss=0' in line
        assert 'smtp=SKIP' in line
        assert 'network=SKIP' in line
        assert 'duration=5s' in line
        assert 'exception' not in line

    def test_field_order_is_stable(self):
        """Grep-based tooling depends on consistent field order."""
        line = build_run_summary(_stats(), status='OK', duration_s=5, mode='imap')
        tokens = line.split()
        # Expected order: [RUN_SUMMARY] status mode files records errors unknown skip_rule clinic_miss smtp network duration
        keys_in_order = [t.split('=')[0] for t in tokens[1:]]
        assert keys_in_order == [
            'status', 'mode', 'files', 'records', 'errors',
            'unknown', 'skip_rule', 'clinic_miss', 'smtp', 'network', 'duration',
        ]

    def test_fail_with_errors(self):
        line = build_run_summary(
            _stats(total_records=120, files_processed=5, errors=['a', 'b'], smtp_status='OK', network_status='FAIL'),
            status='FAIL', duration_s=23, mode='imap'
        )
        assert 'status=FAIL' in line
        assert 'files=5' in line
        assert 'records=120' in line
        assert 'errors=2' in line
        assert 'smtp=OK' in line
        assert 'network=FAIL' in line

    def test_crash_with_exception(self):
        line = build_run_summary(
            _stats(), status='CRASH', duration_s=12, mode='imap',
            exception_class='RuntimeError'
        )
        assert 'status=CRASH' in line
        assert 'exception=RuntimeError' in line
        assert 'duration=12s' in line

    def test_local_mode(self):
        line = build_run_summary(_stats(), status='OK', duration_s=3, mode='local')
        assert 'mode=local' in line

    def test_never_raises_on_missing_fields(self):
        """Robustness: missing stats keys must not crash the summary."""
        sparse = {'errors': []}
        line = build_run_summary(sparse, status='OK', duration_s=1, mode='test')
        assert line.startswith('[RUN_SUMMARY] ')
        # The .get(..., 0) fallbacks must actually produce 0 for numeric fields
        assert 'files=0' in line
        assert 'records=0' in line
        assert 'unknown=0' in line
        assert 'smtp=SKIP' in line
        assert 'network=SKIP' in line


class TestComputeStatus:
    def test_ok_when_all_clean(self):
        assert compute_status(_stats()) == 'OK'

    def test_fail_on_errors(self):
        assert compute_status(_stats(errors=['x'])) == 'FAIL'

    def test_fail_on_unknown_files(self):
        assert compute_status(_stats(unknown_files=['mystery.xlsx'])) == 'FAIL'

    def test_fail_on_unmatched_clinics(self):
        assert compute_status(_stats(unmatched_clinics=['x.xlsx'])) == 'FAIL'

    def test_fail_on_missing_comments(self):
        assert compute_status(_stats(missing_comments=['x.xlsx'])) == 'FAIL'
