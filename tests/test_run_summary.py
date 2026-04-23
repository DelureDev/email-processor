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


class TestRunImapModeSummary:
    """Integration: run_imap_mode emits RUN_SUMMARY in finally block."""

    def test_emits_run_summary_on_success(self, tmp_path, monkeypatch, caplog):
        import main
        import logging
        import fetcher as fetcher_module

        class FakeFetcher:
            def __init__(self, config, dry_run=False):
                self.failed_zips = []
            def connect(self): pass
            def fetch_attachments(self, days_back=7): return []
            def close(self): pass
            def disconnect(self): pass
            def move_to_folder(self, *a, **kw): pass
            def _save_processed_ids(self): pass

        monkeypatch.setattr(fetcher_module, 'IMAPFetcher', FakeFetcher)
        monkeypatch.setattr(main, 'load_existing_keys', lambda p: set())
        monkeypatch.setattr(main, '_ping_healthcheck', lambda c, s: None)

        config = {
            'output': {'master_file': str(tmp_path / 'master.xlsx')},
            'imap': {'days_back': 1},
            'processing': {'deduplicate': False},
            'smtp': {'enabled': False},
        }
        caplog.set_level(logging.INFO)
        main.run_imap_mode(config, dry_run=True)

        summary_lines = [r.message for r in caplog.records if '[RUN_SUMMARY]' in r.message]
        assert len(summary_lines) == 1
        assert 'status=OK' in summary_lines[0]
        assert 'mode=imap' in summary_lines[0]
        # NEW assertions — ensure spec-required fields are present:
        assert 'smtp=' in summary_lines[0]
        assert 'network=' in summary_lines[0]
        assert 'duration=' in summary_lines[0]

    def test_emits_crash_on_exception(self, tmp_path, monkeypatch, caplog):
        import main
        import logging
        import fetcher as fetcher_module

        class BoomFetcher:
            def __init__(self, config, dry_run=False):
                raise RuntimeError("deliberate test failure")
            def connect(self): pass

        monkeypatch.setattr(fetcher_module, 'IMAPFetcher', BoomFetcher)
        monkeypatch.setattr(main, 'load_existing_keys', lambda p: set())
        monkeypatch.setattr(main, '_ping_healthcheck', lambda c, s: None)

        config = {
            'output': {'master_file': str(tmp_path / 'master.xlsx')},
            'imap': {'days_back': 1},
            'processing': {'deduplicate': False},
            'smtp': {'enabled': False},
        }
        caplog.set_level(logging.INFO)
        with pytest.raises(RuntimeError, match='deliberate'):
            main.run_imap_mode(config, dry_run=True)

        summary_lines = [r.message for r in caplog.records if '[RUN_SUMMARY]' in r.message]
        assert len(summary_lines) == 1
        assert 'status=CRASH' in summary_lines[0]
        assert 'exception=RuntimeError' in summary_lines[0]


class TestRunLocalModeSummary:
    def test_emits_run_summary_on_success(self, tmp_path, monkeypatch, caplog):
        import main
        import logging
        monkeypatch.setattr(main, 'load_existing_keys', lambda p: set())

        empty_folder = tmp_path / 'input'
        empty_folder.mkdir()

        config = {
            'output': {'master_file': str(tmp_path / 'master.xlsx')},
            'processing': {'deduplicate': False},
            'smtp': {'enabled': False},
        }
        caplog.set_level(logging.INFO)
        main.run_local_mode(str(empty_folder), config, dry_run=True)

        summary_lines = [r.message for r in caplog.records if '[RUN_SUMMARY]' in r.message]
        assert len(summary_lines) == 1
        assert 'mode=local' in summary_lines[0]
        assert 'status=OK' in summary_lines[0]
        assert 'duration=' in summary_lines[0]

    def test_emits_crash_on_exception(self, tmp_path, monkeypatch, caplog):
        import main
        import logging

        def boom(*_args, **_kwargs):
            raise RuntimeError("deliberate local-mode test failure")

        monkeypatch.setattr(main, 'load_existing_keys', boom)

        empty_folder = tmp_path / 'input'
        empty_folder.mkdir()
        config = {
            'output': {'master_file': str(tmp_path / 'master.xlsx')},
            'processing': {'deduplicate': True},  # forces load_existing_keys to be called
            'smtp': {'enabled': False},
        }
        caplog.set_level(logging.INFO)
        with pytest.raises(RuntimeError, match='deliberate'):
            main.run_local_mode(str(empty_folder), config, dry_run=True)

        summary_lines = [r.message for r in caplog.records if '[RUN_SUMMARY]' in r.message]
        assert len(summary_lines) == 1
        assert 'status=CRASH' in summary_lines[0]
        assert 'exception=RuntimeError' in summary_lines[0]
        assert 'mode=local' in summary_lines[0]


class TestRunTestModeSummary:
    def test_emits_run_summary(self, tmp_path, caplog):
        import main
        import logging
        empty_folder = tmp_path / 'input'
        empty_folder.mkdir()

        config = {'processing': {'deduplicate': False}}
        caplog.set_level(logging.INFO)
        main.run_test_mode(str(empty_folder), config)

        summary_lines = [r.message for r in caplog.records if '[RUN_SUMMARY]' in r.message]
        assert len(summary_lines) == 1
        assert 'mode=test' in summary_lines[0]
        assert 'duration=' in summary_lines[0]

    def test_emits_crash_on_exception(self, tmp_path, monkeypatch, caplog):
        import main
        import logging

        def boom(*_args, **_kwargs):
            raise RuntimeError("deliberate test-mode failure")

        monkeypatch.setattr(main, '_dedup_xls_xlsx', boom)

        empty_folder = tmp_path / 'input'
        empty_folder.mkdir()
        config = {}
        caplog.set_level(logging.INFO)
        with pytest.raises(RuntimeError, match='deliberate'):
            main.run_test_mode(str(empty_folder), config)

        summary_lines = [r.message for r in caplog.records if '[RUN_SUMMARY]' in r.message]
        assert len(summary_lines) == 1
        assert 'status=CRASH' in summary_lines[0]
        assert 'exception=RuntimeError' in summary_lines[0]
        assert 'mode=test' in summary_lines[0]
