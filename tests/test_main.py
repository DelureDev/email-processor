"""Tests for main.py utility functions."""
import pytest
from unittest.mock import patch, MagicMock


def test_convert_xls_to_xlsx_returns_none_on_nonzero_exit(tmp_path):
    """convert_xls_to_xlsx must return None if LibreOffice exits non-zero."""
    fake_xls = tmp_path / 'test.xls'
    fake_xls.write_bytes(b'fake')
    fake_xlsx = tmp_path / 'test.xlsx'
    fake_xlsx.write_bytes(b'partial output')  # file exists but exit was non-zero

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = b'LibreOffice error'

    with patch('subprocess.run', return_value=mock_result):
        from main import convert_xls_to_xlsx
        result = convert_xls_to_xlsx(str(fake_xls))
    assert result is None


def test_convert_xls_to_xlsx_returns_none_on_zero_byte_output(tmp_path):
    """convert_xls_to_xlsx must return None if output file is zero bytes."""
    fake_xls = tmp_path / 'test.xls'
    fake_xls.write_bytes(b'fake')
    fake_xlsx = tmp_path / 'test.xlsx'
    fake_xlsx.write_bytes(b'')  # zero byte file

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = b''

    with patch('subprocess.run', return_value=mock_result):
        from main import convert_xls_to_xlsx
        result = convert_xls_to_xlsx(str(fake_xls))
    assert result is None


class TestEnvVarResolution:
    """Config loader must fail loudly when credential env vars are missing."""

    def test_missing_imap_password_raises(self, tmp_path, monkeypatch):
        from main import load_config
        cfg_file = tmp_path / 'config.yaml'
        cfg_file.write_text(
            'imap:\n'
            '  server: test\n'
            '  port: 993\n'
            '  username: u\n'
            '  password: "${FAKE_MISSING_ENV_VAR_XYZ}"\n'
            '  folder: INBOX\n'
            'processing:\n'
            '  temp_folder: ./temp\n'
            '  processed_ids_file: ./ids.db\n',
            encoding='utf-8',
        )
        monkeypatch.delenv('FAKE_MISSING_ENV_VAR_XYZ', raising=False)
        with pytest.raises(ValueError, match='FAKE_MISSING_ENV_VAR_XYZ'):
            load_config(str(cfg_file))

    def test_resolved_password_passes(self, tmp_path, monkeypatch):
        from main import load_config
        cfg_file = tmp_path / 'config.yaml'
        cfg_file.write_text(
            'imap:\n'
            '  server: test\n'
            '  port: 993\n'
            '  username: u\n'
            '  password: "${MY_TEST_ENV_VAR}"\n'
            '  folder: INBOX\n'
            'processing:\n'
            '  temp_folder: ./temp\n'
            '  processed_ids_file: ./ids.db\n',
            encoding='utf-8',
        )
        monkeypatch.setenv('MY_TEST_ENV_VAR', 'secret123')
        config = load_config(str(cfg_file))
        assert config['imap']['password'] == 'secret123'
