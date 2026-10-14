"""Metrics gating + the telemetry no-op boot (Task 10b, plan §10).

The enabled/disabled cases build a throwaway app so both can be exercised in
one process; the no-op case boots the real app's lifespan with no Sentry/OTel
env to prove the integrations stay inert when unconfigured.
"""

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import observability
from src.api.api_server import app


def _settings(**overrides) -> SimpleNamespace:
    base = {"metrics_enabled": False, "metrics_port": 9100}
    base.update(overrides)
    return SimpleNamespace(**base)


def _has_metrics_route(target: FastAPI) -> bool:
    return any(getattr(route, "path", None) == "/metrics" for route in target.routes)


def test_metrics_disabled_leaves_the_route_absent(monkeypatch):
    monkeypatch.setattr(observability, "get_settings", lambda: _settings())
    target = FastAPI()

    observability.setup_metrics(target)

    assert not _has_metrics_route(target)


def test_metrics_enabled_exposes_the_route(monkeypatch):
    monkeypatch.setattr(
        observability, "get_settings", lambda: _settings(metrics_enabled=True)
    )
    target = FastAPI()

    observability.setup_metrics(target)

    assert _has_metrics_route(target)
    response = TestClient(target).get("/metrics")
    assert response.status_code == 200
    # The app metrics ride on the same registry the instrumentator exposes.
    assert "societas_queue_depth" in response.text


def test_app_ships_with_metrics_off_by_default():
    if os.environ.get("METRICS_ENABLED", "").lower() in ("1", "true"):
        pytest.skip("METRICS_ENABLED is set in this environment")
    assert not _has_metrics_route(app)


def test_boot_without_sentry_or_otel_env_is_a_noop(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    saved = {
        key: getattr(app.state, key, None) for key in ("degraded", "last_llm_probe_at")
    }
    try:
        # Both init paths return cleanly when unconfigured (no import, no call).
        observability.init_tracing(app)
        observability.init_sentry()

        with TestClient(app) as client:  # runs the real lifespan
            assert client.get("/health").status_code == 200
    finally:
        for key, value in saved.items():
            setattr(app.state, key, value)
