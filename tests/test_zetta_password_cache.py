"""Unit tests for zetta_password_cache."""
import json
from datetime import datetime
import pytest


class TestLoad:
    def test_missing_file_returns_none(self, tmp_path):
        from zetta_password_cache import load
        assert load(str(tmp_path / 'nope.json')) is None

    def test_malformed_json_returns_none(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text('{ not valid json', encoding='utf-8')
        assert load(str(p)) is None

    def test_missing_required_keys_returns_none(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text(json.dumps({'password': 'x'}), encoding='utf-8')  # no valid_to
        assert load(str(p)) is None

    def test_expired_cache_returns_none(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text(json.dumps({
            'password': 'abc', 'valid_from': '01.03.2026', 'valid_to': '31.03.2026',
        }), encoding='utf-8')
        today = datetime(2026, 4, 23)
        assert load(str(p), today=today) is None

    def test_current_cache_returns_dict(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text(json.dumps({
            'password': 'abc', 'valid_from': '01.04.2026', 'valid_to': '30.04.2026',
        }), encoding='utf-8')
        today = datetime(2026, 4, 23)
        result = load(str(p), today=today)
        assert result == {'password': 'abc', 'valid_from': '01.04.2026', 'valid_to': '30.04.2026'}

    def test_boundary_valid_to_equals_today_is_still_valid(self, tmp_path):
        from zetta_password_cache import load
        p = tmp_path / 'cache.json'
        p.write_text(json.dumps({
            'password': 'abc', 'valid_from': '01.04.2026', 'valid_to': '30.04.2026',
        }), encoding='utf-8')
        today = datetime(2026, 4, 30)  # last day
        assert load(str(p), today=today) is not None


class TestSave:
    def test_save_creates_file(self, tmp_path):
        from zetta_password_cache import save
        p = str(tmp_path / 'cache.json')
        save(p, 'secret', '01.04.2026', '30.04.2026')
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        assert data == {'password': 'secret', 'valid_from': '01.04.2026', 'valid_to': '30.04.2026'}

    def test_save_overwrites_existing(self, tmp_path):
        from zetta_password_cache import save
        p = str(tmp_path / 'cache.json')
        save(p, 'old', '01.03.2026', '31.03.2026')
        save(p, 'new', '01.04.2026', '30.04.2026')
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        assert data['password'] == 'new'
        assert data['valid_to'] == '30.04.2026'

    def test_roundtrip_through_load(self, tmp_path):
        from zetta_password_cache import save, load
        p = str(tmp_path / 'cache.json')
        save(p, 'mypwd', '01.04.2026', '30.04.2026')
        today = datetime(2026, 4, 15)
        result = load(p, today=today)
        assert result['password'] == 'mypwd'
