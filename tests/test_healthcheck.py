"""Smoke tests for _ping_healthcheck."""
from unittest.mock import MagicMock, patch


class TestPingHealthcheck:
    def test_empty_url_is_noop(self):
        """Empty URL must not call urlopen."""
        from main import _ping_healthcheck, make_stats
        stats = make_stats()
        config = {'healthcheck_url': ''}
        with patch('main.urllib.request.urlopen') as mock_urlopen:
            _ping_healthcheck(config, stats)
            mock_urlopen.assert_not_called()

    def test_missing_key_is_noop(self):
        """Missing healthcheck_url key must not call urlopen."""
        from main import _ping_healthcheck, make_stats
        stats = make_stats()
        config = {}
        with patch('main.urllib.request.urlopen') as mock_urlopen:
            _ping_healthcheck(config, stats)
            mock_urlopen.assert_not_called()

    def test_non_https_url_is_noop(self):
        """Non-https URL must not call urlopen (safety check)."""
        from main import _ping_healthcheck, make_stats
        stats = make_stats()
        config = {'healthcheck_url': 'http://insecure.example.com/uuid'}
        with patch('main.urllib.request.urlopen') as mock_urlopen:
            _ping_healthcheck(config, stats)
            mock_urlopen.assert_not_called()

    def test_success_pings_base_url(self):
        """Success path (no errors) pings the URL without /fail suffix."""
        from main import _ping_healthcheck, make_stats
        stats = make_stats()
        # No errors => success path
        config = {'healthcheck_url': 'https://hc-ping.com/uuid'}
        with patch('main.urllib.request.urlopen') as mock_urlopen:
            _ping_healthcheck(config, stats)
            assert mock_urlopen.called
            # Extract URL from the Request object passed to urlopen
            req_arg = mock_urlopen.call_args.args[0]
            url_str = req_arg.full_url if hasattr(req_arg, 'full_url') else str(req_arg)
            assert '/fail' not in url_str
            assert url_str == 'https://hc-ping.com/uuid'

    def test_failure_adds_fail_suffix(self):
        """When stats['errors'] is non-empty, URL gets /fail appended."""
        from main import _ping_healthcheck, make_stats
        stats = make_stats()
        stats['errors'].append('some prior error')
        config = {'healthcheck_url': 'https://hc-ping.com/uuid'}
        with patch('main.urllib.request.urlopen') as mock_urlopen:
            _ping_healthcheck(config, stats)
            assert mock_urlopen.called
            req_arg = mock_urlopen.call_args.args[0]
            url_str = req_arg.full_url if hasattr(req_arg, 'full_url') else str(req_arg)
            assert url_str.endswith('/fail')

    def test_failure_strips_trailing_slash_before_fail(self):
        """Trailing slash on URL is stripped before /fail suffix."""
        from main import _ping_healthcheck, make_stats
        stats = make_stats()
        stats['errors'].append('boom')
        config = {'healthcheck_url': 'https://hc-ping.com/uuid/'}
        with patch('main.urllib.request.urlopen') as mock_urlopen:
            _ping_healthcheck(config, stats)
            req_arg = mock_urlopen.call_args.args[0]
            url_str = req_arg.full_url if hasattr(req_arg, 'full_url') else str(req_arg)
            assert url_str == 'https://hc-ping.com/uuid/fail'

    def test_network_error_adds_to_stats(self):
        """Network error is caught and surfaced in stats['errors']."""
        from main import _ping_healthcheck, make_stats
        stats = make_stats()
        config = {'healthcheck_url': 'https://hc-ping.com/uuid'}
        with patch('main.urllib.request.urlopen', side_effect=OSError("network down")):
            _ping_healthcheck(config, stats)
        assert any('healthcheck' in e.lower() for e in stats['errors'])

    def test_request_is_post_with_body(self):
        """Request uses POST method with a body containing stats."""
        from main import _ping_healthcheck, make_stats
        stats = make_stats()
        stats['total_records'] = 42
        stats['files_processed'] = 3
        config = {'healthcheck_url': 'https://hc-ping.com/uuid'}
        with patch('main.urllib.request.urlopen') as mock_urlopen:
            _ping_healthcheck(config, stats)
            req_arg = mock_urlopen.call_args.args[0]
            assert req_arg.get_method() == 'POST'
            # Body should contain the stats we set
            body = req_arg.data
            assert b'records=42' in body
            assert b'files=3' in body
