"""Smoke tests for _export_to_network."""
from unittest.mock import patch
import time


class TestExportToNetwork:
    def test_empty_folder_is_noop(self, tmp_path):
        """Empty csv_export_folder means no export — no error, no file writes."""
        from main import _export_to_network, make_stats
        stats = make_stats()
        stats['new_records'] = [{'ФИО': 'Test'}]
        config = {'output': {'csv_export_folder': ''}}
        # Should not raise, should not create any files, should not append errors
        _export_to_network(config, stats)
        err_text = ' '.join(stats['errors'])
        assert 'reachable' not in err_text.lower()
        assert 'timed out' not in err_text.lower()
        # tmp_path was not passed in, so nothing should be in it either
        assert list(tmp_path.iterdir()) == []

    def test_writes_csv_to_reachable_folder(self, tmp_path):
        """Happy path: records written to daily CSV in the configured folder."""
        from main import _export_to_network, make_stats
        stats = make_stats()
        stats['new_records'] = [{
            'ФИО': 'Иванов Иван Иванович',
            'Дата рождения': '01.01.1990',
            '№ полиса': '123456',
            'Начало обслуживания': '01.04.2026',
            'Конец обслуживания': '30.04.2026',
            'Страховая компания': 'TestIns',
            'Страхователь': 'TestPolicyHolder',
            'Клиника': 'TestClinic',
            'ID Клиники': '12345',
            'Комментарий в полис': '',
            'Источник файла': 'a.xlsx',
            'Дата обработки': '15.04.2026',
        }]
        config = {'output': {'csv_export_folder': str(tmp_path),
                             'network_timeout': 10}}
        _export_to_network(config, stats)
        csvs = list(tmp_path.glob('*.csv'))
        assert len(csvs) >= 1, (
            f"Expected at least one CSV in {tmp_path}, "
            f"found {list(tmp_path.iterdir())}"
        )
        # At minimum, the daily delta file should exist
        daily_files = list(tmp_path.glob('records_*.csv'))
        assert len(daily_files) == 1
        # And no 'reachable' error should have been logged
        err_text = ' '.join(stats['errors'])
        assert 'reachable' not in err_text.lower()

    def test_unreachable_folder_times_out(self, tmp_path):
        """Unreachable folder surfaces 'timed out' error in stats."""
        from main import _export_to_network, make_stats
        stats = make_stats()
        # Must have records, else function returns early before the reachability check
        stats['new_records'] = [{'ФИО': 'X', '№ полиса': '1'}]
        config = {'output': {'csv_export_folder': '/path/that/never/exists/hangs',
                             'network_timeout': 1}}
        # Mock os.path.isdir used inside main._export_to_network to simulate
        # a hung network share that sleeps longer than network_timeout.
        def hung_isdir(_path):
            time.sleep(5)
            return True
        with patch('main.os.path.isdir', side_effect=hung_isdir):
            _export_to_network(config, stats)
        err_text = ' '.join(stats['errors'])
        assert 'timed out' in err_text.lower() or 'reachable' in err_text.lower()
