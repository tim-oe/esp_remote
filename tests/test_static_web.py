"""Tests for static HTML asset paths and httpserver URL conventions."""

from scripts.static_web_check import (
    STATIC_DIR,
    collect_local_paths,
    run_all_checks,
    validate_static_files,
)


def test_local_asset_paths_exist() -> None:
    assert validate_static_files() == []


def test_no_double_static_prefix_in_html() -> None:
    for html in STATIC_DIR.glob("*.html"):
        for path in collect_local_paths(html.read_text(encoding="utf-8")):
            assert not path.startswith("/static/"), (
                f"{html.name} must not reference {path}; "
                "httpserver root_path already maps /static on device"
            )


def test_run_all_checks_passes() -> None:
    assert run_all_checks() == []


def test_login_form_posts_urlencoded_password_to_login_route() -> None:
    html = (STATIC_DIR / "login.html").read_text(encoding="utf-8")
    assert 'method="post"' in html
    assert 'action="/login"' in html
    assert 'name="password"' in html
    assert 'type="password"' in html


def test_terminal_js_serializes_poll_and_input() -> None:
    js = (STATIC_DIR / "terminal.js").read_text(encoding="utf-8")
    assert 'fetch("/api/output?since="' in js
    assert 'credentials: "same-origin"' in js
    assert "postInput" in js
    assert "inputPending" in js
    assert "pollInFlight" in js
    assert "scheduleBacklogPoll" in js
    assert "since = st.rx_total" in js
    assert "json.pending" in js
    assert "res.status === 401" in js
