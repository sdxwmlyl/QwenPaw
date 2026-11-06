# -*- coding: utf-8 -*-
"""Tests for ``qwenpaw.plugins.dist_info``.

``pip install --target`` keeps the metadata of the version it replaced, so a
long-lived site dir accumulates several ``.dist-info`` directories per
distribution.  These tests pin the helpers that read the newest copy and prune
the rest, plus the loader probe that must not be fooled by a stale copy.
"""

# pylint: disable=protected-access
from __future__ import annotations

from pathlib import Path

import pytest
from packaging.version import Version

from qwenpaw.plugins import dist_info


def _make_dist(site: Path, name: str, version: str) -> Path:
    path = site / f"{name}-{version}.dist-info"
    path.mkdir(parents=True)
    (path / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        encoding="utf-8",
    )
    return path


def test_iter_dist_info_groups_and_sorts(tmp_path: Path) -> None:
    _make_dist(tmp_path, "demo_pkg", "1.10.0")
    _make_dist(tmp_path, "demo_pkg", "1.9.0")
    _make_dist(tmp_path, "other", "3.0.0")

    grouped = dist_info.iter_dist_info(tmp_path)

    assert set(grouped) == {"demo-pkg", "other"}
    assert [v for v, _ in grouped["demo-pkg"]] == [
        Version("1.9.0"),
        Version("1.10.0"),
    ]


def test_iter_dist_info_ignores_unparsable_dirs(tmp_path: Path) -> None:
    (tmp_path / "not-a-dist-info.dist-info").mkdir()
    (tmp_path / "odd-name.dist-info").mkdir()

    assert not dist_info.iter_dist_info(tmp_path)


def test_best_version_prefers_newest_copy(tmp_path: Path) -> None:
    _make_dist(tmp_path, "demo", "1.0.0")
    _make_dist(tmp_path, "demo", "2.0.0")

    assert dist_info.best_version(tmp_path, "demo") == Version("2.0.0")


def test_best_version_honours_specifier(tmp_path: Path) -> None:
    _make_dist(tmp_path, "demo", "1.0.0")
    _make_dist(tmp_path, "demo", "2.0.0")

    assert dist_info.best_version(tmp_path, "demo", ">=2") == Version("2.0.0")
    assert dist_info.best_version(tmp_path, "demo", "<2") == Version("1.0.0")
    assert dist_info.best_version(tmp_path, "demo", ">=3") is None


def test_best_version_missing_distribution(tmp_path: Path) -> None:
    assert dist_info.best_version(tmp_path, "absent") is None
    assert dist_info.best_version(tmp_path / "nope", "absent") is None


def test_prune_stale_keeps_newest_and_is_idempotent(tmp_path: Path) -> None:
    _make_dist(tmp_path, "demo", "1.0.0")
    _make_dist(tmp_path, "demo", "1.1.0")
    _make_dist(tmp_path, "demo", "2.0.0")

    removed = dist_info.prune_stale(tmp_path)

    assert sorted(removed) == ["demo-1.0.0.dist-info", "demo-1.1.0.dist-info"]
    assert [p.name for p in tmp_path.iterdir()] == ["demo-2.0.0.dist-info"]
    assert not dist_info.prune_stale(tmp_path)


def test_prune_stale_dry_run_keeps_everything(tmp_path: Path) -> None:
    _make_dist(tmp_path, "demo", "1.0.0")
    _make_dist(tmp_path, "demo", "2.0.0")

    removed = dist_info.prune_stale(tmp_path, dry_run=True)

    assert removed == ["demo-1.0.0.dist-info"]
    assert len(list(tmp_path.iterdir())) == 2


def test_prune_stale_respects_name_filter(tmp_path: Path) -> None:
    _make_dist(tmp_path, "alpha", "1.0.0")
    _make_dist(tmp_path, "alpha", "2.0.0")
    _make_dist(tmp_path, "beta", "1.0.0")
    _make_dist(tmp_path, "beta", "2.0.0")

    removed = dist_info.prune_stale(tmp_path, names=["alpha"])

    assert removed == ["alpha-1.0.0.dist-info"]
    assert (tmp_path / "beta-1.0.0.dist-info").is_dir()
