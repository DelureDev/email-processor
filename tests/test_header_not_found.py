"""Verify parsers raise HeaderNotFoundError instead of returning empty list on header miss."""
import pytest
from openpyxl import Workbook


def _make_xlsx_missing_fio(path):
    wb = Workbook()
    ws = wb.active
    ws.append(['Policy', 'Start', 'End'])
    ws.append(['123', '01.01.2026', '31.12.2026'])
    wb.save(path)


def test_ingos_raises_when_fio_column_missing(tmp_path):
    from parsers.ingos import parse
    from parsers.errors import HeaderNotFoundError
    p = tmp_path / 'no_fio.xlsx'
    _make_xlsx_missing_fio(str(p))
    with pytest.raises(HeaderNotFoundError):
        parse(str(p))


def test_luchi_raises_when_fio_column_missing(tmp_path):
    from parsers.luchi import parse
    from parsers.errors import HeaderNotFoundError
    p = tmp_path / 'no_fio.xlsx'
    _make_xlsx_missing_fio(str(p))
    with pytest.raises(HeaderNotFoundError):
        parse(str(p))


def test_errors_module_exposes_header_not_found():
    """Sanity: the exception class exists and is importable."""
    from parsers.errors import HeaderNotFoundError
    assert issubclass(HeaderNotFoundError, Exception)
