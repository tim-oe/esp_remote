"""Session idle timeout for web terminal auth."""

from unittest.mock import MagicMock

from esp_remote.firmware import session


def test_no_ttl_when_zero(monkeypatch) -> None:
    monkeypatch.setenv("WEB_SESSION_TTL_S", "0")
    monkeypatch.setenv("WEB_PASSWORD", "secret")
    session.start_session()
    req = MagicMock()
    req.headers = {"cookie": "esp_auth=1"}
    assert session.authorized(req) is True
    assert session.session_expired() is False
    hdr = session.login_set_cookie_header()
    assert "Max-Age" not in hdr["Set-Cookie"]


def test_idle_timeout_expires(monkeypatch) -> None:
    monkeypatch.setenv("WEB_SESSION_TTL_S", "60")
    monkeypatch.setenv("WEB_PASSWORD", "secret")
    times = [1000.0, 1000.0, 1000.0, 1061.0]
    monkeypatch.setattr(session.time, "monotonic", lambda: times.pop(0))
    session.start_session()
    req = MagicMock()
    req.headers = {"cookie": "esp_auth=1"}
    assert session.authorized(req) is True
    assert session.authorized(req) is False


def test_touch_extends_idle_window(monkeypatch) -> None:
    monkeypatch.setenv("WEB_SESSION_TTL_S", "60")
    monkeypatch.setenv("WEB_PASSWORD", "secret")
    times = [1000.0, 1000.0, 1000.0, 1050.0, 1050.0, 1111.0]
    monkeypatch.setattr(session.time, "monotonic", lambda: times.pop(0))
    session.start_session()
    req = MagicMock()
    req.headers = {"cookie": "esp_auth=1"}
    assert session.authorized(req) is True
    assert session.authorized(req) is True
    assert session.authorized(req) is False


def test_login_cookie_includes_max_age(monkeypatch) -> None:
    monkeypatch.setenv("WEB_SESSION_TTL_S", "120")
    hdr = session.login_set_cookie_header()
    assert "Max-Age=120" in hdr["Set-Cookie"]


def test_end_session_and_logout_cookie(monkeypatch) -> None:
    monkeypatch.setenv("WEB_SESSION_TTL_S", "60")
    monkeypatch.setenv("WEB_PASSWORD", "secret")
    session.start_session()
    session.end_session()
    assert session.session_expired() is True
    clear = session.logout_clear_cookie_header()["Set-Cookie"]
    assert "Max-Age=0" in clear
    assert "esp_auth=" in clear
