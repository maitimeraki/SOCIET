"""Bounded extraction: run the extractor in an isolated child process (plan §7).

The extractor parses untrusted bytes with third-party libraries (PyMuPDF,
python-docx, BeautifulSoup) and, for URLs, drives the network. A malformed
input must not hang or crash the worker, so every extraction runs in a
``python -I`` child with a hard wall-clock timeout and an output-size cap; on
POSIX the child also lowers its own memory/CPU rlimits. On Windows ``resource``
is unavailable — the timeout and size caps still hold, and the missing rlimits
are logged once.

Failures surface as :class:`BoundedExtractionError` (an ``ExtractionError``), so
the job body maps them onto a readable job failure like any other.
"""

import json
import logging
import os
import subprocess
import sys
from importlib.util import find_spec

from src.ingest.extract import ExtractionError

logger = logging.getLogger(__name__)

_CHILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_extract_child.py")

#: Ceiling the child imposes on its own address space (POSIX only).
_RLIMIT_MEMORY_BYTES = 1024 * 1024 * 1024

_rlimit_logged = False


class BoundedExtractionError(ExtractionError):
    """The isolated extractor failed: timeout, crash, oversize output, or a
    child-reported extraction error."""


def _log_missing_rlimits_once() -> None:
    global _rlimit_logged
    if _rlimit_logged or find_spec("resource") is not None:
        return
    _rlimit_logged = True
    logger.warning(
        "resource module unavailable (non-POSIX): extraction runs with the "
        "timeout and output caps only — no memory/CPU rlimits."
    )


def run_extraction(request: dict, *, timeout: int, max_output_bytes: int) -> dict:
    """Run one extraction in the isolated child; return its parsed result dict.

    ``request`` is ``{"kind": "file", "filename": …, "data": <b64>}`` or
    ``{"kind": "url", "url": …}``. Raises :class:`BoundedExtractionError` on
    timeout, crash, oversize output, or a child-reported extraction failure.
    """
    _log_missing_rlimits_once()
    payload = {
        **request,
        "rlimit_memory_bytes": _RLIMIT_MEMORY_BYTES,
        "rlimit_cpu_seconds": timeout,
        "max_output_bytes": max_output_bytes,
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-I", _CHILD],
            input=json.dumps(payload).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BoundedExtractionError(
            f"extraction exceeded its {timeout}s limit"
        ) from exc
    if len(proc.stdout) > max_output_bytes:
        raise BoundedExtractionError(
            f"extraction output exceeded the {max_output_bytes} byte limit"
        )
    try:
        result = json.loads(proc.stdout)
    except (ValueError, UnicodeDecodeError) as exc:
        raise BoundedExtractionError(
            f"extraction failed (exit {proc.returncode})"
        ) from exc
    if not result.get("ok"):
        raise BoundedExtractionError(result.get("detail") or "extraction failed")
    return result
