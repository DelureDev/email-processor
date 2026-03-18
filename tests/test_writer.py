"""Tests for writer.py — master file creation and appending."""
import os
import pytest
import pandas as pd
from writer import write_to_master, load_existing_keys


def _make_record(**overrides):
    """Create a minimal valid record."""
    base = {
        'ФИО': 'ТЕСТОВ ТЕСТ ТЕСТОВИЧ',
        'Дата рождения': '01.01.1990',
        '№ полиса': 'POL-001',
        'Начало обслуживания': '01.01.2026',
        'Конец обслуживания': '31.12.2026',
        'Страховая компания': 'Тест СК',
        'Страхователь': 'ООО Тест',
    }
    base.update(overrides)
    return base


class TestWriteToMaster:
    def test_creates_new_file(self, tmp_path):
        path = str(tmp_path / "master.xlsx")
        records = [_make_record()]
        write_to_master(records, path, source_filename="test.xlsx")
        assert os.path.exists(path)

        df = pd.read_excel(path)
        assert len(df) == 1
        assert df.iloc[0]['ФИО'] == 'ТЕСТОВ ТЕСТ ТЕСТОВИЧ'

    def test_appends_to_existing(self, tmp_path):
        path = str(tmp_path / "master.xlsx")
        write_to_master([_make_record(ФИО='ПЕРВЫЙ')], path, source_filename="a.xlsx")
        write_to_master([_make_record(ФИО='ВТОРОЙ')], path, source_filename="b.xlsx")

        df = pd.read_excel(path)
        assert len(df) == 2
        assert df.iloc[0]['ФИО'] == 'ПЕРВЫЙ'
        assert df.iloc[1]['ФИО'] == 'ВТОРОЙ'

    def test_backup_cleaned_after_success(self, tmp_path):
        path = str(tmp_path / "master.xlsx")
        write_to_master([_make_record()], path, source_filename="a.xlsx")
        write_to_master([_make_record(ФИО='SECOND')], path, source_filename="b.xlsx")
        # .bak is created during write but removed after successful completion
        assert not os.path.exists(path + '.bak')
        assert os.path.exists(path)

    def test_does_not_mutate_input(self, tmp_path):
        path = str(tmp_path / "master.xlsx")
        record = _make_record()
        original_keys = set(record.keys())
        write_to_master([record], path, source_filename="test.xlsx")
        assert set(record.keys()) == original_keys, "write_to_master should not mutate input dicts"


class TestLoadExistingKeys:
    def test_empty_on_missing_file(self, tmp_path):
        keys = load_existing_keys(str(tmp_path / "nonexistent.xlsx"))
        assert keys == set()

    def test_loads_keys(self, tmp_path):
        path = str(tmp_path / "master.xlsx")
        write_to_master([_make_record()], path, source_filename="test.xlsx")
        keys = load_existing_keys(path)
        assert len(keys) == 1
        assert ('ТЕСТОВ ТЕСТ ТЕСТОВИЧ', 'POL-001', '01.01.2026', '31.12.2026', '') in keys

    def test_dedup_works(self, tmp_path):
        path = str(tmp_path / "master.xlsx")
        r1 = _make_record()
        r2 = _make_record()  # same key
        r3 = _make_record(ФИО='ДРУГОЙ ЧЕЛОВЕК')
        write_to_master([r1], path, source_filename="a.xlsx")
        keys = load_existing_keys(path)
        # r2 should match existing key, r3 should not
        key2 = ('ТЕСТОВ ТЕСТ ТЕСТОВИЧ', 'POL-001', '01.01.2026', '31.12.2026', '')
        key3 = ('ДРУГОЙ ЧЕЛОВЕК', 'POL-001', '01.01.2026', '31.12.2026', '')
        assert key2 in keys
        assert key3 not in keys
