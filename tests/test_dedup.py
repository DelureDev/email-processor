"""Tests for deduplication logic in main.py."""
from main import _record_key


class TestRecordKey:
    def test_basic_key(self):
        record = {
            'ФИО': 'Иванов Иван Иванович',
            '№ полиса': 'POL-001',
            'Начало обслуживания': '01.01.2026',
            'Конец обслуживания': '31.12.2026',
        }
        key = _record_key(record)
        assert key == ('ИВАНОВ ИВАН ИВАНОВИЧ', 'POL-001', '01.01.2026', '31.12.2026', '')

    def test_fio_uppercased(self):
        r1 = {'ФИО': 'иванов иван', '№ полиса': '1', 'Начало обслуживания': '', 'Конец обслуживания': ''}
        r2 = {'ФИО': 'ИВАНОВ ИВАН', '№ полиса': '1', 'Начало обслуживания': '', 'Конец обслуживания': ''}
        assert _record_key(r1) == _record_key(r2)

    def test_none_values_cleaned(self):
        record = {
            'ФИО': 'Test',
            '№ полиса': None,
            'Начало обслуживания': None,
            'Конец обслуживания': None,
        }
        key = _record_key(record)
        assert key == ('TEST', '', '', '', '')

    def test_nan_cleaned(self):
        record = {
            'ФИО': 'Test',
            '№ полиса': float('nan'),
            'Начало обслуживания': 'nan',
            'Конец обслуживания': 'NaT',
        }
        key = _record_key(record)
        assert key == ('TEST', '', '', '', '')

    def test_different_records_different_keys(self):
        r1 = {'ФИО': 'Иванов', '№ полиса': '001', 'Начало обслуживания': '01.01.2026', 'Конец обслуживания': ''}
        r2 = {'ФИО': 'Петров', '№ полиса': '002', 'Начало обслуживания': '01.01.2026', 'Конец обслуживания': ''}
        assert _record_key(r1) != _record_key(r2)
