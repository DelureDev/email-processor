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
        mock_fetcher._save_processed_ids.assert_not_called()
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


class TestProcessedIdsNotSavedOnWriteFailure:
    """If master.xlsx write fails, processed_ids SQLite must NOT be updated."""

    def test_processed_ids_save_skipped_when_write_fails(self, tmp_path, monkeypatch):
        import main
        from unittest.mock import MagicMock

        fake_fetcher = MagicMock()
        fake_fetcher.connect.return_value = None
        fake_fetcher.fetch_attachments.return_value = [{
            'filepath': str(tmp_path / 'dummy.xlsx'),
            'sender': 'x@y.z', 'subject': '', 'date': '',
            'message_id': '<m1>', 'imap_id': '1',
        }]
        (tmp_path / 'dummy.xlsx').write_bytes(b'')
        fake_fetcher.failed_zips = []
        fake_fetcher._save_processed_ids = MagicMock()
        fake_fetcher.move_to_folder = MagicMock()
        fake_fetcher.disconnect = MagicMock()

        monkeypatch.setattr('fetcher.IMAPFetcher', lambda *a, **k: fake_fetcher)

        def fake_process(path, master, cfg, stats, **kw):
            kw['pending'].append({'ФИО': 'Test', '№ полиса': '1',
                                  'Начало обслуживания': '01.01.2026',
                                  'Конец обслуживания': '31.12.2026',
                                  'Страховая компания': 'T', 'Страхователь': 'T',
                                  'Клиника': 'X', 'Комментарий в полис': '',
                                  'Источник файла': 'dummy.xlsx',
                                  'Дата обработки': '23.04.2026'})
        monkeypatch.setattr(main, 'process_file', fake_process)

        def fake_write(*args, **kwargs):
            raise IOError("disk full")
        monkeypatch.setattr(main, 'write_batch_to_master', fake_write)
        monkeypatch.setattr(main, 'load_existing_keys', lambda p: set())

        cfg = {'output': {'master_file': str(tmp_path / 'm.xlsx')},
               'processing': {'deduplicate': True},
               'imap': {'processed_folder': 'Processed'}}

        main.run_imap_mode(cfg, dry_run=False)

        fake_fetcher._save_processed_ids.assert_not_called()
        fake_fetcher.move_to_folder.assert_not_called()


class TestMonthlyAttachmentHappyPath:
    """Lock observable behavior: last-day populates monthly_records; non-last-day leaves it empty."""

    def test_last_day_populates_monthly_records(self, tmp_path, monkeypatch):
        """On the last day of the month, master.xlsx is filtered by 'Дата обработки' month."""
        import main
        import pandas as pd
        from datetime import datetime as real_dt

        master = tmp_path / 'master.xlsx'
        df = pd.DataFrame([
            {'ФИО': 'Иванов И.И.', '№ полиса': '1', 'Начало обслуживания': '01.04.2026',
             'Конец обслуживания': '30.04.2026', 'Страховая компания': 'X',
             'Страхователь': 'Y', 'Клиника': 'Z', 'Комментарий в полис': '',
             'Источник файла': 'a.xlsx', 'Дата обработки': '15.04.2026'},
            {'ФИО': 'Петров П.П.', '№ полиса': '2', 'Начало обслуживания': '01.03.2026',
             'Конец обслуживания': '31.03.2026', 'Страховая компания': 'X',
             'Страхователь': 'Y', 'Клиника': 'Z', 'Комментарий в полис': '',
             'Источник файла': 'b.xlsx', 'Дата обработки': '10.03.2026'},
            {'ФИО': 'Сидоров С.С.', '№ полиса': '3', 'Начало обслуживания': '01.04.2026',
             'Конец обслуживания': '30.04.2026', 'Страховая компания': 'X',
             'Страхователь': 'Y', 'Клиника': 'Z', 'Комментарий в полис': '',
             'Источник файла': 'c.xlsx', 'Дата обработки': '1.4.2026'},
        ])
        df.to_excel(master, index=False)

        config = {'output': {'master_file': str(master)}}
        stats = main.make_stats()

        # Freeze "today" to April 30, 2026 — last day of April
        class Frozen(real_dt):
            @classmethod
            def now(cls, tz=None):
                return real_dt(2026, 4, 30)
        monkeypatch.setattr('main.datetime', Frozen)

        main._attach_monthly_if_last_day(config, stats)

        # Observable behavior: monthly_records populated with only April rows
        assert isinstance(stats['monthly_records'], list)
        assert len(stats['monthly_records']) == 2, (
            f"Expected 2 April records, got {len(stats['monthly_records'])}: {stats['monthly_records']}"
        )
        fios = {r['ФИО'] for r in stats['monthly_records']}
        assert 'Иванов И.И.' in fios
        assert 'Сидоров С.С.' in fios  # "1.4.2026" should be zero-padded and match
        assert 'Петров П.П.' not in fios  # March row excluded
        # No error should have been logged
        assert not any('monthly' in e.lower() for e in stats['errors'])

    def test_non_last_day_skips(self, tmp_path, monkeypatch):
        """On a non-last-day, monthly_records stays empty even if master.xlsx exists."""
        import main
        import pandas as pd
        from datetime import datetime as real_dt

        # Even with a real master file, function should skip on non-last-day
        master = tmp_path / 'master.xlsx'
        df = pd.DataFrame([
            {'ФИО': 'A', '№ полиса': '1', 'Начало обслуживания': '01.04.2026',
             'Конец обслуживания': '30.04.2026', 'Страховая компания': 'X',
             'Страхователь': 'Y', 'Клиника': 'Z', 'Комментарий в полис': '',
             'Источник файла': 'a.xlsx', 'Дата обработки': '15.04.2026'},
        ])
        df.to_excel(master, index=False)

        class Frozen(real_dt):
            @classmethod
            def now(cls, tz=None):
                return real_dt(2026, 4, 15)  # mid-month, not last day
        monkeypatch.setattr('main.datetime', Frozen)

        config = {'output': {'master_file': str(master)}}
        stats = main.make_stats()

        main._attach_monthly_if_last_day(config, stats)

        # Observable behavior: monthly_records unchanged (empty list from make_stats)
        assert stats['monthly_records'] == []
        assert not any('monthly' in e.lower() for e in stats['errors'])
