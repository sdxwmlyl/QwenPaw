# -*- coding: utf-8 -*-
"""Read and prune ``.dist-info`` directories in a plugin dependency site dir.

``pip install --target DIR`` never removes the metadata of the version it
replaces, so a long-lived target directory accumulates several
``.dist-info`` directories for the same distribution.  ``importlib.metadata``
then reports whichever copy it finds first — possibly an old version — which
makes the "is this requirement satisfied?" probe fail, triggers another
install, and adds yet another copy.  ``plugins/install_lock.py`` documents that
self-amplifying loop; this module supplies the missing half, pruning.

Public helpers:

* :func:`iter_dist_info` — group installed metadata by canonical name.
* :func:`best_version` — highest installed version, optionally filtered by a
  specifier, tolerant of multiple copies.
* :func:`prune_stale` — keep one ``.dist-info`` per distribution and remove the
  rest (metadata only; package files are untouched).
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Iterable, Mapping

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

_DIST_INFO_RE = re.compile(
    r"^(?P<name>.+?)-(?P<version>[^-]+)\.dist-info$",
)


def _parse_dist_info(path: Path) -> tuple[str, Version] | None:
    """Return ``(canonical_name, version)`` for a ``*.dist-info`` directory."""
    match = _DIST_INFO_RE.match(path.name)
    if not match:
        return None
    try:
        version = Version(match.group("version"))
    except InvalidVersion:
        return None
    return canonicalize_name(match.group("name")), version


def iter_dist_info(
    site_dir: Path | str,
) -> dict[str, list[tuple[Version, Path]]]:
    """Group ``.dist-info`` directories in *site_dir* by canonical name.

    The values are sorted by version, oldest first, so ``[-1]`` is the newest
    copy.  Unparsable directories (e.g. leftovers with unusual names) are
    ignored rather than treated as errors.
    """
    grouped: dict[str, list[tuple[Version, Path]]] = {}
    root = Path(site_dir)
    if not root.is_dir():
        return grouped
    for entry in root.iterdir():
        if not entry.is_dir() or not entry.name.endswith(".dist-info"):
            continue
        parsed = _parse_dist_info(entry)
        if parsed is None:
            continue
        name, version = parsed
        grouped.setdefault(name, []).append((version, entry))
    for items in grouped.values():
        items.sort(key=lambda item: item[0])
    return grouped


def best_version(
    site_dir: Path | str,
    name: str,
    specifier: str | SpecifierSet | None = None,
) -> Version | None:
    """Return the highest installed version of *name* in *site_dir*.

    Unlike ``importlib.metadata.version()`` this looks at every copy, so a
    stale leftover cannot mask a satisfying install.  When *specifier* is
    given, only versions satisfying it are considered.
    """
    entries = iter_dist_info(site_dir).get(canonicalize_name(name), [])
    if not entries:
        return None
    wanted: SpecifierSet | None
    if specifier is None:
        wanted = None
    elif isinstance(specifier, SpecifierSet):
        wanted = specifier
    else:
        try:
            wanted = SpecifierSet(str(specifier))
        except InvalidSpecifier:
            wanted = None
    if wanted is not None:
        entries = [item for item in entries if wanted.contains(item[0])]
        if not entries:
            return None
    return entries[-1][0]


def prune_stale(
    site_dir: Path | str,
    *,
    names: Iterable[str] | None = None,
    keep: Mapping[str, str | Path] | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Remove duplicate ``.dist-info`` copies, keeping the newest per name.

    Args:
        site_dir: Directory that holds the installed metadata.
        names: Optional distribution names to restrict pruning to.  ``None``
            prunes every duplicated distribution in *site_dir*.
        keep: Optional mapping of canonical distribution name to the metadata
            directory that must survive.  Use this when the caller knows which
            copy is authoritative (e.g. a just-committed install, or a
            deliberate downgrade) instead of assuming the newest copy wins.
        dry_run: Report what would be removed without deleting anything.

    Returns:
        The ``.dist-info`` directory names that were (or would be) removed.
    """
    root = Path(site_dir)
    wanted_names = (
        {canonicalize_name(name) for name in names}
        if names is not None
        else None
    )
    kept_paths = {
        canonicalize_name(name): str(Path(path))
        for name, path in (keep or {}).items()
    }
    removed: list[str] = []
    for name, entries in iter_dist_info(root).items():
        if len(entries) < 2:
            continue
        if wanted_names is not None and name not in wanted_names:
            continue
        authoritative = kept_paths.get(name)
        stale = [
            (version, path)
            for version, path in entries
            if authoritative is None or str(path) != authoritative
        ]
        if authoritative is None:
            stale = entries[:-1]
        for _version, path in stale:
            if not dry_run:
                try:
                    shutil.rmtree(path)
                except OSError:
                    logger.warning(
                        "Could not remove stale metadata %s",
                        path,
                        exc_info=True,
                    )
                    continue
            removed.append(path.name)
    if removed:
        logger.info(
            "Pruned %d stale .dist-info director%s in %s%s",
            len(removed),
            "y" if len(removed) == 1 else "ies",
            root,
            " (dry run)" if dry_run else "",
        )
    return removed
