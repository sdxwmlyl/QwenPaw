# -*- coding: utf-8 -*-
"""Tests for channel Bot identity conflict reporting and release.

A duplicated credential usually hides in a *stopped* agent's persisted config:
nothing is running to collide with when the second agent saves, and the failure
only appears as ``ACCOUNT_IN_USE`` once both start.  These tests pin the helpers
that let the UI name the holder and release it.
"""

# pylint: disable=protected-access
from __future__ import annotations

from qwenpaw.app.channels.conflict import (
    clear_channel_identity,
    find_identity_holders,
    get_channel_bot_identity,
)


def _identity(token: str = "token-abc"):
    return get_channel_bot_identity(
        "wechat",
        {"enabled": True, "bot_token": token},
    )


def test_holders_include_enabled_and_disabled_agents() -> None:
    configs = {
        "default": {"enabled": True, "bot_token": "token-abc"},
        "VRPUDS": {"enabled": False, "bot_token": "token-abc"},
        "other": {"enabled": True, "bot_token": "token-xyz"},
    }

    holders = find_identity_holders("wechat", _identity(), configs)

    assert holders == [
        ("VRPUDS", False, True),
        ("default", True, True),
    ]


def test_holders_empty_for_different_identity() -> None:
    configs = {"a": {"enabled": True, "bot_token": "token-other"}}

    assert find_identity_holders("wechat", _identity(), configs) == []


def test_holders_empty_without_identity() -> None:
    configs = {"a": {"enabled": True, "bot_token": "token-abc"}}

    assert find_identity_holders("wechat", None, configs) == []


def test_holders_ignore_non_mapping_entries() -> None:
    configs = {"a": {"enabled": True, "bot_token": "token-abc"}, "b": None}

    assert [
        h[0] for h in find_identity_holders("wechat", _identity(), configs)
    ] == [
        "a",
    ]


def test_clear_identity_disables_and_clears_token() -> None:
    cleared = clear_channel_identity(
        "wechat",
        {"enabled": True, "bot_token": "token-abc", "bot_prefix": "bot"},
    )

    assert cleared["bot_token"] == ""
    assert cleared["enabled"] is False
    # Unrelated settings survive the release.
    assert cleared["bot_prefix"] == "bot"


def test_clear_identity_leaves_other_channels_untouched() -> None:
    original = {"enabled": True, "bot_token": "token-abc"}
    cleared = clear_channel_identity("unknown-channel", original)

    assert cleared == original
