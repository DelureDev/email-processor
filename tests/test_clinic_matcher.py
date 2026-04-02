"""Tests for clinic_matcher.py — clinic detection and comment extraction."""
import os
import pytest
import pandas as pd
from openpyxl import Workbook
from clinic_matcher import detect_clinic, extract_policy_comment, reload_clinics, _load_clinics


@pytest.fixture(autouse=True)
def reset_clinic_cache():
    """Reset the clinic cache before each test."""
    reload_clinics()
    yield
    reload_clinics()


def _make_xlsx(path, rows, sheet_name='Sheet1'):
    """Create an xlsx file with given rows (list of lists)."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()


def _make_clinics_yaml(path, clinics):
    """Create a clinics.yaml file."""
    import yaml
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump({'clinics': clinics}, f, allow_unicode=True)


class TestDetectClinic:
    def test_matches_keyword(self, tmp_path):
        clinics_path = str(tmp_path / 'clinics.yaml')
        _make_clinics_yaml(clinics_path, [
            {'name': 'Тест Клиника', 'keywords': ['тест клиника']},
        ])
        xlsx_path = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_path, [
            ['Прикрепление к Тест Клиника'],
            ['ФИО', 'Полис'],
            ['Иванов', '001'],
        ])
        clinic, extract_comment, clinic_id = detect_clinic(xlsx_path, config_path=clinics_path)
        assert clinic == 'Тест Клиника'
        assert extract_comment is False
        assert clinic_id == ''

    def test_no_match(self, tmp_path):
        clinics_path = str(tmp_path / 'clinics.yaml')
        _make_clinics_yaml(clinics_path, [
            {'name': 'Другая', 'keywords': ['другая клиника']},
        ])
        xlsx_path = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_path, [['ФИО', 'Полис'], ['Иванов', '001']])
        clinic, _, clinic_id = detect_clinic(xlsx_path, config_path=clinics_path)
        assert clinic == '⚠️ Не определено'
        assert clinic_id == ''

    def test_longest_keyword_wins(self, tmp_path):
        clinics_path = str(tmp_path / 'clinics.yaml')
        _make_clinics_yaml(clinics_path, [
            {'name': 'Клиника А', 'keywords': ['клиника']},
            {'name': 'Клиника АБ', 'keywords': ['клиника абвгд']},
        ])
        xlsx_path = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_path, [['Прикрепление к Клиника АБВГД']])
        clinic, _, _ = detect_clinic(xlsx_path, config_path=clinics_path)
        assert clinic == 'Клиника АБ'

    def test_extract_comment_flag(self, tmp_path):
        clinics_path = str(tmp_path / 'clinics.yaml')
        _make_clinics_yaml(clinics_path, [
            {'name': 'Спец', 'keywords': ['спец клиника'], 'extract_comment': True},
        ])
        xlsx_path = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_path, [['Направление в Спец Клиника']])
        clinic, extract_comment, _ = detect_clinic(xlsx_path, config_path=clinics_path)
        assert clinic == 'Спец'
        assert extract_comment is True

    def test_missing_clinics_yaml(self, tmp_path):
        clinic, _, clinic_id = detect_clinic(
            str(tmp_path / 'test.xlsx'),
            config_path=str(tmp_path / 'nonexistent.yaml'),
        )
        assert clinic == '⚠️ Не определено'
        assert clinic_id == ''

    def test_clinic_id_returned(self, tmp_path):
        clinics_path = str(tmp_path / 'clinics.yaml')
        _make_clinics_yaml(clinics_path, [
            {'name': 'Тест', 'id': '000000042', 'keywords': ['тест']},
        ])
        xlsx_path = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_path, [['Данные для Тест']])
        clinic, _, clinic_id = detect_clinic(xlsx_path, config_path=clinics_path)
        assert clinic == 'Тест'
        assert clinic_id == '000000042'


class TestExtractPolicyComment:
    def test_finds_column_header(self, tmp_path):
        xlsx_path = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_path, [
            ['№', 'ФИО', 'Программа ДМС'],
            ['1', 'Иванов', 'Поликлиническое обслуживание Премиум'],
        ])
        comment = extract_policy_comment(xlsx_path)
        assert 'Поликлиническое обслуживание Премиум' in comment

    def test_finds_free_text_keyword(self, tmp_path):
        xlsx_path = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_path, [
            ['Информация о прикреплении'],
            ['Амбулаторно-поликлиническое обслуживание по программе VIP'],
            ['ФИО', 'Полис'],
            ['Иванов', '001'],
        ])
        comment = extract_policy_comment(xlsx_path)
        assert 'Амбулаторно-поликлиническое' in comment

    def test_returns_empty_on_no_match(self, tmp_path):
        xlsx_path = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_path, [
            ['ФИО', 'Полис'],
            ['Иванов', '001'],
        ])
        comment = extract_policy_comment(xlsx_path)
        assert comment == ''

    def test_handles_missing_file(self, tmp_path):
        comment = extract_policy_comment(str(tmp_path / 'nonexistent.xlsx'))
        assert comment == ''

import os as _os

_TEST_FILES = _os.path.join(_os.path.dirname(__file__), '..', 'test_files')

@pytest.mark.skipif(
    not _os.path.exists(_os.path.join(_TEST_FILES, 'ПСБ_Список_на_откр_от_31_03_2026_(0000244141).xlsx')),
    reason="PSB откр fixture not in test_files/"
)
def test_psb_otkr_returns_empty_clinic():
    """PSB открепление file → empty clinic, no warning."""
    from clinic_matcher import detect_clinic, reload_clinics
    reload_clinics()
    clinic, extract, cid = detect_clinic(
        _os.path.join(_TEST_FILES, 'ПСБ_Список_на_откр_от_31_03_2026_(0000244141).xlsx')
    )
    assert clinic == ''
    assert extract is False


@pytest.mark.skipif(
    not _os.path.exists(_os.path.join(_TEST_FILES, 'ПСБ_Список_на_прикр_от_27_03_2026_(0000235400).xlsx')),
    reason="PSB прикр fixture not in test_files/"
)
def test_psb_prikr_returns_garibaldi_15():
    """PSB прикрепление file → Гарибальди 15."""
    from clinic_matcher import detect_clinic, reload_clinics
    reload_clinics()
    clinic, extract, cid = detect_clinic(
        _os.path.join(_TEST_FILES, 'ПСБ_Список_на_прикр_от_27_03_2026_(0000235400).xlsx')
    )
    assert clinic == 'Гарибальди 15'
    assert cid == '000000001'


@pytest.mark.skipif(
    not _os.path.exists(_os.path.join(_TEST_FILES, '1826_00345267_24-03-2026-20-19-38_1826фдг_snyat.xlsx')),
    reason="Alfa snyat fixture not in test_files/"
)
def test_alfa_snyat_returns_empty_clinic():
    """Alfa snyat file → empty clinic."""
    from clinic_matcher import detect_clinic, reload_clinics
    reload_clinics()
    clinic, extract, cid = detect_clinic(
        _os.path.join(_TEST_FILES, '1826_00345267_24-03-2026-20-19-38_1826фдг_snyat.xlsx')
    )
    assert clinic == ''
    assert extract is False
