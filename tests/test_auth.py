"""Tests for authentication routes."""
import pytest


class TestLogin:
    def test_login_page(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200

    def test_login_success(self, client):
        resp = client.post('/login', data={
            'email': 'tenant@example.com',
            'password': 'admin'
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '管理员' in resp.data.decode('utf-8') or '活动' in resp.data.decode('utf-8')

    def test_login_wrong_password(self, client):
        resp = client.post('/login', data={
            'email': 'tenant@example.com',
            'password': 'wrong'
        }, follow_redirects=True)
        assert resp.status_code == 200
        body = resp.data.decode('utf-8')
        assert '密码' in body or '错误' in body or 'login' in body.lower()

    def test_login_wrong_username(self, client):
        resp = client.post('/login', data={
            'email': 'nobody@example.com',
            'password': 'admin'
        }, follow_redirects=True)
        assert resp.status_code == 200
        body = resp.data.decode('utf-8')
        assert '密码' in body or '错误' in body or 'login' in body.lower()


class TestLogout:
    def test_logout(self, client):
        # Login first
        client.post('/login', data={
            'email': 'tenant@example.com',
            'password': 'admin'
        })
        resp = client.get('/logout', follow_redirects=True)
        assert resp.status_code == 200
        # Should redirect to login
        body = resp.data.decode('utf-8')
        assert '登录' in body or 'login' in body.lower()

    def test_logout_redirects_to_login(self, client):
        resp = client.get('/logout', follow_redirects=True)
        assert resp.status_code == 200


class TestAccessControl:
    def test_admin_page_requires_login(self, client):
        resp = client.get('/admin', follow_redirects=True)
        assert resp.status_code == 200
        # Should be on login page
        assert '登录' in resp.data.decode('utf-8') or 'login' in resp.data.decode('utf-8').lower()

    def test_admin_page_accessible_when_logged_in(self, auth_client):
        resp = auth_client.get('/admin')
        assert resp.status_code == 200
