"""Tests for format detection."""
from tests.conftest import fixture_path
from detector import detect_format, detect_by_sender


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


class TestDetectBySender:
    """Tests for sender-based format detection."""

    def test_exact_email_match(self):
        assert detect_by_sender('spiski.dms@reso.ru') == 'reso'

    def test_case_insensitive(self):
        assert detect_by_sender('SPISKI.DMS@RESO.RU') == 'reso'

    def test_domain_match(self):
        """Full email addresses match their sender key."""
        assert detect_by_sender('spiski_lpu@ingos.ru') == 'ingos'

    def test_unknown_sender(self):
        assert detect_by_sender('unknown@example.com') is None

    def test_empty_sender(self):
        assert detect_by_sender('') is None
        assert detect_by_sender(None) is None

    def test_substring_does_not_match_full_emails(self):
        """A sender key like 'spiski.dms@reso.ru' should not match fake domains."""
        assert detect_by_sender('fake@notreso.ru') is None

    def test_partial_key_matches(self):
        """'spiskirobot' is a partial key — should match as substring."""
        assert detect_by_sender('spiskirobot@vsk.ru') == 'vsk'

    def test_all_known_senders(self):
        """Every sender in the map should be detected."""
        from detector import SENDER_FORMAT_MAP
        for sender_key, expected_fmt in SENDER_FORMAT_MAP.items():
            result = detect_by_sender(sender_key)
            assert result == expected_fmt, f"Failed for sender_key={sender_key!r}"
