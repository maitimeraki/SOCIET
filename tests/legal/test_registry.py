"""The legal-document registry: seeds, hashes, and placeholder rendering."""

import datetime
from types import SimpleNamespace

from src.legal import registry


def test_every_seed_file_exists_and_hashes_are_stable():
    for seed in registry.SEEDS:
        raw = registry.read_raw(seed)
        assert raw.strip(), seed.slug
        assert registry.content_sha256(seed) == registry.content_sha256(seed)
        assert len(registry.content_sha256(seed)) == 64


def test_versions_are_iso_dates_and_required_slugs_are_present():
    slugs = {seed.slug for seed in registry.SEEDS}
    assert set(registry.REQUIRED_CONSENT_SLUGS) <= slugs
    for seed in registry.SEEDS:
        assert datetime.date.fromisoformat(seed.version) == seed.effective_at


def test_render_substitutes_both_placeholders(monkeypatch):
    settings = SimpleNamespace(
        legal_entity_name="Acme Legal Ltd",
        legal_contact_email="legal@acme.test",
    )
    monkeypatch.setattr(registry, "get_settings", lambda: settings)

    rendered = registry.render("{{legal_entity_name}} — {{legal_contact_email}}")

    assert rendered == "Acme Legal Ltd — legal@acme.test"


def test_render_falls_back_when_unset(monkeypatch):
    settings = SimpleNamespace(legal_entity_name="", legal_contact_email="")
    monkeypatch.setattr(registry, "get_settings", lambda: settings)

    rendered = registry.render("{{legal_entity_name}} — {{legal_contact_email}}")

    assert rendered == "Societas — hello@societas.app"
