"""Tests for format detection."""
from tests.conftest import fixture_path
from detector import detect_format


def test_detect_alfa():
    assert detect_format(fixture_path('alfa.xlsx')) == 'alfa'


def test_detect_ingos():
    assert detect_format(fixture_path('ingos.XLS')) == 'ingos'


def test_detect_soglasie():
    assert detect_format(fixture_path('soglasie.xlsx')) == 'soglasie'


def test_detect_zetta():
    assert detect_format(fixture_path('zetta.xlsx')) == 'zetta'


def test_detect_alfa_by_sender():
    assert detect_format(fixture_path('alfa.xlsx'), sender='alfastrah@alfastrah.ru') == 'alfa'


def test_detect_unknown_returns_none_or_generic(tmp_path):
    """An empty xlsx should return None or a generic format."""
    import pandas as pd
    empty = tmp_path / "empty.xlsx"
    pd.DataFrame().to_excel(empty, index=False)
    result = detect_format(str(empty))
    assert result is None or result.startswith('generic')
