"""Regression test: VSK Страхователь column must come from Холдинг, not Место работы."""
import pandas as pd
from openpyxl import Workbook
from parsers.vsk import parse


def _write_vsk_xlsx(path, rows):
    """Build a minimal VSK xlsx with both 'Место работы' and 'Холдинг' columns."""
    wb = Workbook()
    ws = wb.active
    headers = [
        '№ п/п', 'ФИО', 'Дата рождения', 'Пол', 'Серия и номер полиса',
        'Адрес', 'Телефон', 'Дата прикрепления', 'Дата открепления',
        'Место работы', 'Холдинг', 'Объём', 'Программа',
    ]
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_vsk_strahovatel_uses_holding(tmp_path):
    path = tmp_path / "vsk.xlsx"
    _write_vsk_xlsx(path, [
        [1, 'ИВАНОВ ИВАН ИВАНОВИЧ', '01.01.1990', 'М', 'POL123',
         'Москва', '+7-000', '01.01.2026', '31.12.2026',
         'Офис на Ленина 1', 'ООО ХолдингАкме', 'Полный', 'Стандарт'],
    ])

    records = parse(str(path))

    assert len(records) == 1
    assert records[0]['Страхователь'] == 'ООО ХолдингАкме', \
        f"Expected Страхователь to come from Холдинг, got {records[0]['Страхователь']!r}"


def test_vsk_strahovatel_falls_back_to_workplace_if_holding_missing(tmp_path):
    """Backwards compat: if a VSK variant lacks Холдинг column, fall back to Место работы."""
    path = tmp_path / "vsk_no_holding.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(['№ п/п', 'ФИО', 'Дата рождения', 'Полис №',
               'Дата открепления', 'Место работы'])
    ws.append([1, 'ПЕТРОВ ПЕТР ПЕТРОВИЧ', '02.02.1985', 'POL456',
               '15.06.2026', 'Завод №5'])
    wb.save(path)

    records = parse(str(path))

    assert len(records) == 1
    assert records[0]['Страхователь'] == 'Завод №5'
