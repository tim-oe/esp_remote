"""Browser session lifetime for the web terminal (monotonic clock)."""

import os
import time

AUTH_COOKIE = "esp_auth=1"
_AUTH_COOKIE = AUTH_COOKIE
_expires_at = 0.0


def _password_configured() -> bool:
    return bool(
        os.getenv("WEB_PASSWORD", "") or os.getenv("CIRCUITPY_WEB_API_PASSWORD", "")
    )


def session_ttl_seconds() -> int:
    """Idle timeout in seconds; 0 disables expiry (cookie lasts for browser session)."""
    raw = os.getenv("WEB_SESSION_TTL_S", "0")
    if raw is None or raw == "":
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def start_session() -> None:
    """Call after successful login."""
    global _expires_at
    ttl = session_ttl_seconds()
    if ttl <= 0:
        _expires_at = 0.0
    else:
        _expires_at = time.monotonic() + ttl


def touch_session() -> None:
    """Extend idle timeout on each authorized request."""
    global _expires_at
    ttl = session_ttl_seconds()
    if ttl > 0:
        _expires_at = time.monotonic() + ttl


def session_expired() -> bool:
    ttl = session_ttl_seconds()
    if ttl <= 0:
        return False
    return time.monotonic() > _expires_at


def cookie_present(request) -> bool:
    cookie = request.headers.get("cookie", "")
    return _AUTH_COOKIE in cookie


def authorized(request) -> bool:
    if not _password_configured():
        return True
    if not cookie_present(request):
        return False
    if session_expired():
        return False
    touch_session()
    return True


def login_set_cookie_header() -> dict[str, str]:
    ttl = session_ttl_seconds()
    value = _AUTH_COOKIE + "; Path=/; HttpOnly"
    if ttl > 0:
        value += f"; Max-Age={ttl}"
    return {"Set-Cookie": value}


def end_session() -> None:
    """Invalidate the current browser session on the ESP32."""
    global _expires_at
    _expires_at = 0.0


def logout_clear_cookie_header() -> dict[str, str]:
    return {"Set-Cookie": _AUTH_COOKIE + "=; Path=/; HttpOnly; Max-Age=0"}
