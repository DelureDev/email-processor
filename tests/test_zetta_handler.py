"""Tests for zetta_handler.py — password extraction and sender detection."""
import os
import zipfile
import pytest
from zetta_handler import (
    extract_monthly_password,
    extract_password_from_body,
    extract_password_from_html,
    is_zetta_email,
    is_sber_email,
    is_password_zip_email,
    is_zetta_monthly_password_email,
    unzip_with_password,
    try_passwords,
)


class TestSenderDetection:
    def test_zetta_email(self):
        assert is_zetta_email('pulse.letter@zettains.ru')
        assert is_zetta_email('ZETTA_LIFE_SPISKI@ZETTAINS.RU')
        assert not is_zetta_email('someone@gmail.com')

    def test_sber_email(self):
        assert is_sber_email('digital.assistant@sberins.ru')
        assert not is_sber_email('someone@gmail.com')

    def test_password_zip_email(self):
        assert is_password_zip_email('pulse.letter@zettains.ru')
        assert is_password_zip_email('digital.assistant@sberins.ru')
        assert not is_password_zip_email('someone@gmail.com')

    def test_zetta_monthly_password_email(self):
        assert is_zetta_monthly_password_email('parollpu@zettains.ru')
        assert not is_zetta_monthly_password_email('pulse.letter@zettains.ru')


class TestExtractMonthlyPassword:
    def test_standard_format(self):
        body = """
        Уважаемые коллеги!
        Высылаем пароль для открытия файлов
        в период с 01.03.2026 по 31.03.2026 .

        MyP@ssw0rd123

        Коммерческая тайна.
        """
        result = extract_monthly_password(body)
        assert result is not None
        assert result['password'] == 'MyP@ssw0rd123'
        assert result['valid_from'] == '01.03.2026'
        assert result['valid_to'] == '31.03.2026'

    def test_html_body(self):
        body = """<html><body>
        <p>Высылаем пароль для файлов</p>
        <p>в период с 01.03.2026 по 31.03.2026 .</p>
        <br>
        <p>TestPassword1</p>
        <p>Настоящее письмо конфиденциально.</p>
        </body></html>"""
        result = extract_monthly_password(body)
        assert result is not None
        assert result['password'] == 'TestPassword1'

    def test_no_period(self):
        body = "Some random email body with no password info"
        assert extract_monthly_password(body) is None

    def test_empty_body(self):
        assert extract_monthly_password('') is None
        assert extract_monthly_password(None) is None


class TestExtractPasswordFromBody:
    def test_zip_pattern(self):
        body = "Пароль для открытия ГП12345.zip:\nAbc123xyz"
        pwd = extract_password_from_body(body)
        assert pwd == 'Abc123xyz'

    def test_direct_pattern(self):
        body = "Пароль: MySecret99"
        pwd = extract_password_from_body(body)
        assert pwd == 'MySecret99'

    def test_lowercase_parol(self):
        body = "пароль: secret123"
        pwd = extract_password_from_body(body)
        assert pwd == 'secret123'

    def test_short_password_rejected(self):
        body = "Пароль: ab"
        pwd = extract_password_from_body(body)
        assert pwd is None

    def test_empty_body(self):
        assert extract_password_from_body('') is None
        assert extract_password_from_body(None) is None


class TestExtractPasswordFromHtml:
    def test_strips_html(self):
        html = "<html><body><p>Пароль: Secret123</p></body></html>"
        pwd = extract_password_from_html(html)
        assert pwd == 'Secret123'

    def test_empty(self):
        assert extract_password_from_html('') is None
        assert extract_password_from_html(None) is None


class TestUnzipWithPassword:
    def test_extracts_xlsx(self, tmp_path):
        # Create a password-protected zip with an xlsx file
        xlsx_content = b'PK\x03\x04fake xlsx content'
        xlsx_name = 'test_data.xlsx'
        zip_path = str(tmp_path / 'test.zip')
        extract_to = str(tmp_path / 'extracted')

        # Create a real zip with password using pyzipper if available,
        # otherwise test with non-password zip
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr(xlsx_name, xlsx_content)

        # unzip_with_password tries password encodings — will succeed on non-encrypted
        result = unzip_with_password(zip_path, 'anypassword', extract_to)
        # Non-encrypted zip extracts without password
        assert len(result) == 1
        assert result[0].endswith('.xlsx')

    def test_zip_slip_blocked(self, tmp_path):
        zip_path = str(tmp_path / 'evil.zip')
        extract_to = str(tmp_path / 'extracted')

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('../../../evil.xlsx', b'evil content')

        result = unzip_with_password(zip_path, 'pass', extract_to)
        assert len(result) == 0

    def test_empty_zip(self, tmp_path):
        zip_path = str(tmp_path / 'empty.zip')
        extract_to = str(tmp_path / 'extracted')

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('readme.txt', b'no xlsx here')

        result = unzip_with_password(zip_path, 'pass', extract_to)
        assert len(result) == 0


class TestTryPasswords:
    def test_no_xlsx_in_zip(self, tmp_path):
        zip_path = str(tmp_path / 'noxlsx.zip')
        extract_to = str(tmp_path / 'extracted')

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('readme.txt', b'no xlsx here')

        result = try_passwords(zip_path, ['pass1', 'pass2'], extract_to)
        assert result == []

    def test_invalid_zip(self, tmp_path):
        zip_path = str(tmp_path / 'bad.zip')
        extract_to = str(tmp_path / 'extracted')

        with open(zip_path, 'wb') as f:
            f.write(b'not a zip file')

        result = try_passwords(zip_path, ['pass1'], extract_to)
        assert result == []
