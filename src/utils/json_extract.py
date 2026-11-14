"""Extract the first JSON object from a model reply."""


def extract_json_object(raw: str) -> str | None:
    """Return the first balanced `{...}` object in `raw`, or None.

    Tolerates markdown fences and prose before/after the object (both are
    common from a small model) by locating the first `{` and matching braces.
    String-aware, so a brace inside a JSON string never ends the match early.
    """
    text = raw or ""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
