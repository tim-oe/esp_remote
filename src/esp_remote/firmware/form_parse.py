"""Parse application/x-www-form-urlencoded bodies (CircuitPython-safe)."""


def bytes_to_text(chunk: bytes) -> str:
    """Decode UART bytes to UTF-8 text (CircuitPython has no decode(..., errors=))."""
    if not chunk:
        return ""
    try:
        import codecs  # noqa: PLC0415

        return codecs.decode(chunk, "utf-8", "replace")
    except (ImportError, TypeError):
        pass
    try:
        return chunk.decode("utf-8")
    except UnicodeError:
        return "".join(chr(b) for b in chunk)


def unquote_plus(value: str) -> str:
    """Decode a single form field (``+`` → space, ``%XX`` → byte)."""
    out: list[str] = []
    i = 0
    length = len(value)
    while i < length:
        ch = value[i]
        if ch == "+":
            out.append(" ")
            i += 1
        elif ch == "%" and i + 2 < length:
            hex_part = value[i + 1 : i + 3]
            try:
                out.append(chr(int(hex_part, 16)))
            except ValueError:
                out.append(ch)
            i += 3
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_form_urlencoded(body: str) -> dict[str, str]:
    """Return the first value for each field in a URL-encoded form body."""
    fields: dict[str, str] = {}
    if not body:
        return fields
    for pair in body.split("&"):
        if "=" not in pair:
            continue
        key, raw_val = pair.split("=", 1)
        fields[unquote_plus(key)] = unquote_plus(raw_val)
    return fields
