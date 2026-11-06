# -*- coding: utf-8 -*-
"""Helpers for detecting duplicate Bot identities across channels."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional


_CHANNEL_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "discord": ("bot_token",),
    "telegram": ("bot_token",),
    "slack": ("bot_token",),
    "mattermost": ("url", "bot_token"),
    "wechat": ("bot_token",),
    "dingtalk": ("client_id",),
    "feishu": ("app_id",),
    "qq": ("app_id",),
    "wecom": ("bot_id",),
    "matrix": ("homeserver", "user_id"),
    "voice": ("phone_number_sid",),
    "xiaoyi": ("agent_id",),
    "yuanbao": ("app_id",),
}


def _config_value(config: Any, field: str) -> Any:
    """Read a field from either a mapping or a config model."""
    if isinstance(config, Mapping):
        return config.get(field)
    return getattr(config, field, None)


def _normalize_identity_value(field: str, value: Any) -> str:
    """Normalize an identity value without exposing it outside this module."""
    normalized = str(value or "").strip()
    if field in {"homeserver", "url"}:
        normalized = normalized.rstrip("/")
    return normalized


def get_channel_bot_identity(
    channel_name: str,
    config: Any,
) -> Optional[tuple[tuple[str, str], ...]]:
    """Return a comparable Bot identity, or None when it is unavailable."""
    if config is None:
        return None

    fields = _CHANNEL_IDENTITY_FIELDS.get(channel_name)
    if fields is None:
        return None

    identity = tuple(
        (
            field,
            _normalize_identity_value(
                field,
                _config_value(config, field),
            ),
        )
        for field in fields
    )
    if any(not value for _, value in identity):
        return None
    return identity


def find_identity_holders(
    channel_name: str,
    identity: Optional[tuple[tuple[str, str], ...]],
    configs: Mapping[str, Any],
) -> list[tuple[str, bool, bool]]:
    """Return ``(agent_id, enabled, configured)`` for configs sharing *identity*.

    ``configs`` maps an agent id to that agent's channel config mapping.
    Callers gather it from persisted agent configs, so a stopped agent still
    shows up as a holder — that is exactly the case that produces
    ``ACCOUNT_IN_USE`` only after both agents start.
    """
    if not identity:
        return []
    holders: list[tuple[str, bool, bool]] = []
    for agent_id, config in configs.items():
        if not isinstance(config, Mapping):
            continue
        if get_channel_bot_identity(channel_name, config) != identity:
            continue
        holders.append(
            (
                str(agent_id),
                bool(config.get("enabled")),
                bool(
                    any(
                        _normalize_identity_value(field, config.get(field))
                        for field in _CHANNEL_IDENTITY_FIELDS[channel_name]
                    ),
                ),
            ),
        )
    return sorted(holders)


def clear_channel_identity(
    channel_name: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a copy of *config* with the Bot identity cleared and disabled.

    Releasing an identity must also disable the channel: leaving it enabled
    with an empty token only moves the failure to the next start.
    """
    fields = _CHANNEL_IDENTITY_FIELDS.get(channel_name)
    if not fields:
        return dict(config)
    cleared = dict(config)
    for field in fields:
        cleared[field] = ""
    cleared["enabled"] = False
    return cleared


def get_channel_config(channels: Any, channel_name: str) -> Any:
    """Read a built-in channel config by name."""
    if channels is None:
        return None
    if isinstance(channels, Mapping):
        return channels.get(channel_name)
    return getattr(channels, channel_name, None)
