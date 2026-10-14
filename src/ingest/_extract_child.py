"""Isolated extraction child: JSON on stdin, JSON on stdout — never raises.

Run as ``python -I src/ingest/_extract_child.py`` by ``bounded.run_extraction``.
The parent bounds wall-clock time and output size; this process additionally
lowers its own POSIX memory/CPU rlimits when ``resource`` is available (a Linux
worker), so a decompression bomb cannot exhaust the box before the timeout.

``-I`` isolates the interpreter (no PYTHON* env, no user site), so the repo root
is put back on ``sys.path`` explicitly — it is a trusted, hard-coded location.
"""

import base64
import json
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _apply_rlimits(memory_bytes: int, cpu_seconds: int) -> None:
    try:
        import resource
    except ImportError:
        return  # Windows: the parent's timeout + output caps still apply.
    for limit, value in (
        (resource.RLIMIT_AS, memory_bytes),
        (resource.RLIMIT_CPU, cpu_seconds),
    ):
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass


def _extract(request: dict) -> dict:
    from src.ingest.extract import ExtractionError, extract_document, extract_url

    try:
        if request["kind"] == "url":
            document, meta = extract_url(request["url"])
            return {"ok": True, "document": document, "meta": meta}
        document = extract_document(
            request["filename"], base64.b64decode(request["data"])
        )
        return {"ok": True, "document": document}
    except ExtractionError as exc:
        return {"ok": False, "detail": exc.detail}
    except Exception as exc:  # noqa: BLE001 — the parent only ever sees JSON
        return {"ok": False, "detail": f"extraction failed: {exc}"}


def main() -> None:
    request = json.load(sys.stdin)
    _apply_rlimits(request["rlimit_memory_bytes"], request["rlimit_cpu_seconds"])
    response = _extract(request)
    out = json.dumps(response).encode("utf-8")
    if len(out) > request["max_output_bytes"]:
        out = json.dumps(
            {"ok": False, "detail": "extraction output exceeded the size limit"}
        ).encode("utf-8")
    sys.stdout.buffer.write(out)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
