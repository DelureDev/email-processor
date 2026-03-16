"""Tests for individual parsers against real fixture files."""
import pytest
from tests.conftest import fixture_path

# Required fields every record must have
REQUIRED_FIELDS = {'ФИО', 'Дата рождения', '№ полиса', 'Начало обслуживания',
                   'Конец обслуживания', 'Страховая компания', 'Страхователь'}


def _validate_records(records, expected_company, min_count=1):
    """Common validation for parsed records."""
    assert len(records) >= min_count, f"Expected at least {min_count} records, got {len(records)}"
    for r in records:
        assert REQUIRED_FIELDS.issubset(r.keys()), f"Missing fields: {REQUIRED_FIELDS - r.keys()}"
        assert r['ФИО'], "ФИО should not be empty"
        assert r['Страховая компания'] == expected_company


# --- Alfa ---

class TestAlfa:
    def test_parse(self):
        from parsers.alfa import parse
        records = parse(fixture_path('alfa.xlsx'))
        _validate_records(records, 'АльфаСтрахование', min_count=2)

    def test_fields(self):
        from parsers.alfa import parse
        records = parse(fixture_path('alfa.xlsx'))
        r = records[0]
        assert r['Дата рождения'] is not None
        assert r['№ полиса'] is not None
        assert r['Начало обслуживания'] is not None
        assert r['Конец обслуживания'] is not None


# --- Ingos ---

class TestIngos:
    def test_parse(self):
        from parsers.ingos import parse
        records = parse(fixture_path('ingos.XLS'))
        _validate_records(records, 'Ингосстрах', min_count=1)

    def test_fio_uppercase(self):
        from parsers.ingos import parse
        records = parse(fixture_path('ingos.XLS'))
        for r in records:
            assert r['ФИО'] == r['ФИО'].upper(), "Ingos FIO should be uppercased"

    def test_strahovatel(self):
        from parsers.ingos import parse
        records = parse(fixture_path('ingos.XLS'))
        assert records[0]['Страхователь'] is not None


# --- Soglasie ---

class TestSoglasie:
    def test_parse(self):
        from parsers.soglasie import parse
        records = parse(fixture_path('soglasie.xlsx'))
        _validate_records(records, 'СК Согласие', min_count=1)

    def test_dates_extracted(self):
        from parsers.soglasie import parse
        records = parse(fixture_path('soglasie.xlsx'))
        r = records[0]
        # Soglasie gets dates from metadata rows, not per-row columns
        assert r['Начало обслуживания'] is not None or r['Конец обслуживания'] is not None

    def test_strahovatel(self):
        from parsers.soglasie import parse
        records = parse(fixture_path('soglasie.xlsx'))
        assert records[0]['Страхователь'] is not None


# --- Zetta ---

class TestZetta:
    def test_parse(self):
        from parsers.zetta import parse
        records = parse(fixture_path('zetta.xlsx'))
        _validate_records(records, 'Зетта Страхование жизни', min_count=1)

    def test_fio_uppercase(self):
        from parsers.zetta import parse
        records = parse(fixture_path('zetta.xlsx'))
        for r in records:
            assert r['ФИО'] == r['ФИО'].upper(), "Zetta FIO should be uppercased"

    def test_policy_number(self):
        from parsers.zetta import parse
        records = parse(fixture_path('zetta.xlsx'))
        assert records[0]['№ полиса'] is not None
