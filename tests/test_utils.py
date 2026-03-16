"""Tests for parsers/utils.py shared functions."""
import pandas as pd
import pytest
from datetime import datetime
from parsers.utils import format_date, find_header_row, build_header_map, find_col, get_cell_str, assemble_fio


class TestFormatDate:
    def test_datetime_object(self):
        dt = datetime(2026, 3, 15)
        assert format_date(dt) == '15.03.2026'

    def test_iso_string(self):
        assert format_date('2026-03-15') == '15.03.2026'

    def test_iso_with_time(self):
        assert format_date('2026-03-15 10:30:00') == '15.03.2026'

    def test_dot_format_passthrough(self):
        assert format_date('15.03.2026') == '15.03.2026'

    def test_slash_format(self):
        assert format_date('15/03/2026') == '15.03.2026'

    def test_nan(self):
        assert format_date(float('nan')) is None

    def test_none_like(self):
        assert format_date(pd.NaT) is None

    def test_empty_string(self):
        assert format_date('') is None

    def test_unparseable_returns_raw(self):
        assert format_date('some text') == 'some text'


class TestFindHeaderRow:
    def test_finds_header(self):
        df = pd.DataFrame([
            ['info', 'info'],
            ['info', 'info'],
            ['ФИО', '№ полиса'],
            ['Иванов', '123'],
        ])
        assert find_header_row(df, ('фио', 'полис')) == 2

    def test_returns_none_if_not_found(self):
        df = pd.DataFrame([['a', 'b'], ['c', 'd']])
        assert find_header_row(df, ('фио', 'полис')) is None

    def test_respects_max_rows(self):
        rows = [['x', 'y']] * 10 + [['ФИО', 'полис']]
        df = pd.DataFrame(rows)
        assert find_header_row(df, ('фио', 'полис'), max_rows=5) is None
        assert find_header_row(df, ('фио', 'полис'), max_rows=15) == 10


class TestBuildHeaderMapAndFindCol:
    def test_builds_map(self):
        df = pd.DataFrame([['№ п/п', 'ФИО', 'Дата рождения', '№ полиса']])
        headers = build_header_map(df, 0)
        assert find_col(headers, 'фио') == 1
        assert find_col(headers, 'полис') == 3
        assert find_col(headers, 'дата', 'рожд') == 2

    def test_find_col_returns_none(self):
        headers = {'фио': 0, 'полис': 1}
        assert find_col(headers, 'nonsense') is None


class TestGetCellStr:
    def test_normal_value(self):
        df = pd.DataFrame([['hello', 123]])
        assert get_cell_str(df, 0, 0) == 'hello'
        assert get_cell_str(df, 0, 1) == '123'

    def test_nan_returns_none(self):
        df = pd.DataFrame([[float('nan')]])
        assert get_cell_str(df, 0, 0) is None

    def test_none_col_returns_none(self):
        df = pd.DataFrame([['hello']])
        assert get_cell_str(df, 0, None) is None

    def test_empty_string_returns_none(self):
        df = pd.DataFrame([['  ']])
        assert get_cell_str(df, 0, 0) is None


class TestAssembleFio:
    def test_full_fio(self):
        df = pd.DataFrame([['Иванов', 'Иван', 'Иванович']])
        assert assemble_fio(df, 0, 0, 1, 2) == 'Иванов Иван Иванович'

    def test_no_otchestvo(self):
        df = pd.DataFrame([['Иванов', 'Иван', float('nan')]])
        assert assemble_fio(df, 0, 0, 1, 2) == 'Иванов Иван'

    def test_familia_only(self):
        df = pd.DataFrame([['Иванов', float('nan'), float('nan')]])
        assert assemble_fio(df, 0, 0) == 'Иванов'
