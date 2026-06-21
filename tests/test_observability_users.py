"""Tests for observability user label enrichment."""

from __future__ import annotations

from backend.models.config import AlfredConfig, ObservabilityConfig
from backend.observability.users import UserLabelEnricher, looks_like_slack_user_id


def test_looks_like_slack_user_id():
    assert looks_like_slack_user_id("U0522NX5GG0")
    assert not looks_like_slack_user_id("amit")


def test_display_name_uses_config_alias():
    config = AlfredConfig(
        observability=ObservabilityConfig(user_labels={"U0522NX5GG0": "Amit"}),
    )
    enricher = UserLabelEnricher(config)
    assert enricher.display_name("U0522NX5GG0", "U0522NX5GG0") == "Amit"


def test_display_name_prefers_existing_label():
    config = AlfredConfig()
    enricher = UserLabelEnricher(config)
    assert enricher.display_name("U1", "Om") == "Om"


def test_merge_by_user_combines_ids_to_names():
    config = AlfredConfig(
        observability=ObservabilityConfig(user_labels={"U0522NX5GG0": "Amit"}),
    )
    enricher = UserLabelEnricher(config)
    merged = enricher.merge_by_user(
        {"U0522NX5GG0": 2, "U1": 1},
        [("U0522NX5GG0", "U0522NX5GG0", 2), ("U1", "U1", 1)],
    )
    assert merged["Amit"] == 2
    assert merged["U1"] == 1


def test_enricher_uses_disk_cache(tmp_path):
    from backend.storage.slack_user_cache import SlackUserCache

    SlackUserCache(tmp_path).remember("U051D2Q2QUA", "Om")
    config = AlfredConfig()
    enricher = UserLabelEnricher(config, data_dir=tmp_path)
    assert enricher.display_name("U051D2Q2QUA", "U051D2Q2QUA") == "Om"
