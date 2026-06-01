"""Tests for utility functions."""
import pytest
from app.utils import (
    format_time, safe_float, safe_int, truncate_str,
    generate_csrf_token
)


class TestFormatTime:
    def test_none(self):
        assert format_time(None) == '-'

    def test_zero(self):
        assert format_time(0) == '0:00.000'

    def test_seconds_only(self):
        assert format_time(1.5) == '0:01.500'

    def test_minutes_and_seconds(self):
        assert format_time(125.3) == '2:05.300'

    def test_large_value(self):
        assert format_time(3720.0) == '62:00.000'


class TestSafeFloat:
    def test_valid_float(self):
        assert safe_float('3.14') == 3.14

    def test_valid_int_string(self):
        assert safe_float('5') == 5.0

    def test_none_value(self):
        assert safe_float(None) == 0.0

    def test_empty_string(self):
        assert safe_float('') == 0.0

    def test_invalid_string(self):
        assert safe_float('abc') == 0.0

    def test_custom_default(self):
        assert safe_float('abc', 10.0) == 10.0

    def test_already_float(self):
        assert safe_float(2.5) == 2.5


class TestSafeInt:
    def test_valid_int(self):
        assert safe_int('42') == 42

    def test_none_value(self):
        assert safe_int(None) == 0

    def test_empty_string(self):
        assert safe_int('') == 0

    def test_custom_default(self):
        assert safe_int('abc', 10) == 10


class TestTruncateStr:
    def test_short_string(self):
        assert truncate_str('hello', 100) == 'hello'

    def test_truncation(self):
        result = truncate_str('a' * 50, 10)
        assert len(result) == 10
        assert result == 'a' * 10

    def test_none_input(self):
        assert truncate_str(None) == ''

    def test_empty_input(self):
        assert truncate_str('') == ''

    def test_exact_length(self):
        assert truncate_str('12345', 5) == '12345'


class TestGenerateCSRFToken:
    def test_generates_token(self, client):
        # login page renders {{ csrf_token() }} in the form
        client.get('/login')
        with client.session_transaction() as sess:
            token = sess.get('_csrf_token')
            assert isinstance(token, str)
            assert len(token) == 32

    def test_returns_same_token_in_session(self, client):
        client.get('/login')
        with client.session_transaction() as sess:
            token = sess['_csrf_token']
        # second request, same session cookie
        client.get('/login')
        with client.session_transaction() as sess:
            assert sess['_csrf_token'] == token
