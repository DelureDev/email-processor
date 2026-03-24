"""Tests for pipeline resilience — write failures must not kill the pipeline."""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from main import make_stats


class TestWriteBatchFailure:
    """Pipeline must survive write_batch_to_master failure."""

    @patch('notifier.send_report')
    @patch('main.write_batch_to_master', side_effect=RuntimeError("Disk full"))
    @patch('main.load_existing_keys', return_value=set())
    @patch('fetcher.IMAPFetcher')
    def test_imap_mode_survives_write_failure(self, mock_fetcher_cls, mock_keys, mock_write, mock_report):
        """run_imap_mode should catch write failure, add to errors, not move emails."""
        from main import run_imap_mode

        mock_fetcher = MagicMock()
        mock_fetcher.fetch_attachments.return_value = [{
            'filepath': '/tmp/fake.xlsx',
            'filename': 'fake.xlsx',
            'sender': 'test@test.com',
            'subject': 'Test',
            'date': '2026-03-24',
            'message_id': '<test@test>',
            'imap_id': '123',
            '_extract_dir': None,
        }]
        mock_fetcher.failed_zips = []
        mock_fetcher_cls.return_value = mock_fetcher

        config = {
            'imap': {'server': 'x', 'username': 'x', 'password': 'x'},
            'output': {'master_file': '/tmp/test_master.xlsx'},
            'processing': {'deduplicate': True},
        }

        with patch('main.process_file') as mock_pf:
            def fake_process(fp, mp, cfg, stats, **kw):
                if kw.get('pending') is not None:
                    kw['pending'].append(([{'test': 'record'}], 'fake.xlsx'))
                stats['total_records'] += 1
                stats['new_records'].append({'test': 'record'})
            mock_pf.side_effect = fake_process

            stats = run_imap_mode(config, dry_run=False)

        # Should have error in stats, not crash
        assert any('Disk full' in e for e in stats['errors'])
        # Should NOT have moved emails
        mock_fetcher.move_to_folder.assert_not_called()
        # new_records should be cleared since write failed
        assert stats['new_records'] == []
        assert stats['total_records'] == 0

    @patch('notifier.send_report')
    @patch('main.write_batch_to_master', side_effect=RuntimeError("Corrupted xlsx"))
    @patch('main.load_existing_keys', return_value=set())
    def test_local_mode_survives_write_failure(self, mock_keys, mock_write, mock_report):
        """run_local_mode should catch write failure, add to errors, continue."""
        from main import run_local_mode

        with tempfile.TemporaryDirectory() as td:
            config = {
                'output': {'master_file': os.path.join(td, 'master.xlsx')},
                'processing': {'deduplicate': False},
            }

            with patch('main.process_file') as mock_pf:
                def fake_process(fp, mp, cfg, stats, **kw):
                    if kw.get('pending') is not None:
                        kw['pending'].append(([{'test': 'record'}], 'test.xlsx'))
                    stats['total_records'] += 1
                    stats['new_records'].append({'test': 'record'})
                mock_pf.side_effect = fake_process

                # Create a dummy file so glob finds something
                import openpyxl
                wb = openpyxl.Workbook()
                wb.save(os.path.join(td, 'test.xlsx'))

                stats = run_local_mode(td, config, dry_run=False)

            assert any('Corrupted xlsx' in e for e in stats['errors'])
            assert stats['new_records'] == []
            assert stats['total_records'] == 0


class TestMonthlyAttachmentFailure:
    def test_monthly_error_in_stats(self):
        """_attach_monthly_if_last_day should add error to stats, not just log."""
        import calendar
        from datetime import datetime
        from unittest.mock import patch
        from main import _attach_monthly_if_last_day, make_stats

        stats = make_stats()

        # Create a corrupt "xlsx" file that will cause pd.read_excel to fail
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            f.write(b'not a real xlsx')
            corrupt_path = f.name

        try:
            config = {'output': {'master_file': corrupt_path}}
            today = datetime.now()
            last_day = calendar.monthrange(today.year, today.month)[1]

            # Force last day of month so the function actually runs
            with patch('main.datetime') as mock_dt:
                mock_dt.now.return_value = today.replace(day=last_day)
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                _attach_monthly_if_last_day(config, stats)

            assert any('monthly' in e.lower() or 'Failed' in e for e in stats['errors'])
        finally:
            os.unlink(corrupt_path)
