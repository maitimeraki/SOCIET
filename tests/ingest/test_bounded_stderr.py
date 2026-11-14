"""run_extraction logs a bounded, printable tail of child stderr, never the whole stream."""
import logging
import re
import subprocess

import pytest

from src.ingest import bounded


def _child(tmp_path, stderr_expr: str) -> str:
    path = tmp_path / "child.py"
    path.write_text(
        "import sys\n"
        "sys.stdout.write('{\"ok\": false, \"detail\": \"x\"}')\n"
        f"sys.stderr.write({stderr_expr})\n",
        encoding="utf-8",
    )
    return str(path)


def _run(monkeypatch, script: str):
    monkeypatch.setattr(bounded, "_CHILD", script)
    with pytest.raises(bounded.BoundedExtractionError):
        bounded.run_extraction(
            {"kind": "url", "url": "http://x"}, timeout=30, max_output_bytes=10_000
        )


def test_child_stderr_is_captured_to_a_file_not_a_pipe(tmp_path, monkeypatch):
    seen = {}
    real_run = subprocess.run

    def spy(*args, **kwargs):
        seen["stderr"] = kwargs.get("stderr")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(bounded.subprocess, "run", spy)
    _run(monkeypatch, _child(tmp_path, "'quiet'"))

    assert seen["stderr"] not in (subprocess.PIPE, subprocess.DEVNULL, None)


def test_a_very_large_child_stderr_logs_only_its_last_4000_bytes(tmp_path, monkeypatch, caplog):
    script = _child(tmp_path, "'START' + 'x' * (3 * 1024 * 1024) + 'END-TAIL'")
    with caplog.at_level(logging.WARNING, logger=bounded.logger.name):
        _run(monkeypatch, script)

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "END-TAIL" in text
    assert "START" not in text
    assert max(len(run) for run in re.findall("x+", text)) <= 4000


def test_logged_child_stderr_carries_no_control_characters(tmp_path, monkeypatch, caplog):
    script = _child(tmp_path, "'bad\\x1b[31mRED\\x00\\x07 line one\\nline two'")
    with caplog.at_level(logging.WARNING, logger=bounded.logger.name):
        _run(monkeypatch, script)

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "line two" in text
    assert not any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in text)
