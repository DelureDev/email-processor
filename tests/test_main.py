"""Tests for main.py utility functions."""
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
