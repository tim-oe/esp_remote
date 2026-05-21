"""Low-level form body parsing (login depends on this)."""

from esp_remote.firmware.form_parse import (
    bytes_to_text,
    parse_form_urlencoded,
    unquote_plus,
)


def test_unquote_plus_decodes_at_and_space() -> None:
    assert unquote_plus("test%40pwd") == "test@pwd"
    assert unquote_plus("hello+world") == "hello world"


def test_parse_form_password_with_special_chars() -> None:
    body = "password=test%40pwd"
    assert parse_form_urlencoded(body)["password"] == "test@pwd"


def test_parse_form_multiple_fields() -> None:
    body = "user=a%26b&password=x%2By"
    parsed = parse_form_urlencoded(body)
    assert parsed["user"] == "a&b"
    assert parsed["password"] == "x+y"


def test_empty_body_returns_no_fields() -> None:
    assert parse_form_urlencoded("") == {}


def test_bytes_to_text_handles_ascii_and_invalid_utf8() -> None:
    assert bytes_to_text(b"") == ""
    assert bytes_to_text(b"login:") == "login:"
    assert "\ufffd" in bytes_to_text(b"\xff\xfe")


def test_unquote_plus_invalid_percent_escape() -> None:
    # Invalid hex after % keeps the percent and skips the bad pair.
    assert unquote_plus("%ZZ") == "%"


def test_parse_form_skips_pairs_without_equals() -> None:
    assert parse_form_urlencoded("foo&password=x") == {"password": "x"}


def test_bytes_to_text_latin_fallback_when_decode_fails(monkeypatch) -> None:
    import codecs as codecs_mod

    monkeypatch.setattr(
        codecs_mod,
        "decode",
        lambda *args, **kwargs: (_ for _ in ()).throw(TypeError()),
    )
    assert bytes_to_text(b"\xff") == chr(0xFF)
