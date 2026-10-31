"""Inventory: one photo_harvest row per unique SHA-256. [co-06tcu]

Reads the catalog (files, file_hashes, scans, drives), groups every JPEG/HEIC
copy by fingerprint, and records one readable copy under the harvest root
(/mnt/z/Harvest/<drive_code>/<path>, then the alternate roots, then wherever
the harvest manifest says the copy went). Rows already in photo_harvest are left
alone, so a re-run only adds what is new (for example, after a drive is
attached and fingerprinted).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import PHOTO_EXTENSIONS, Config

log = logging.getLogger(__name__)

# Lower-cased path fragments that mark software, system or web assets rather
# than photos someone took. A match is recorded as skipped_path, not dropped,
# so it can be revisited.
SKIP_PATH_PARTS = (
    "/program files/", "/program files (x86)/", "/programdata/", "/appdata/",
    "/windows/", "/$recycle.bin/", "/node_modules/", "/source/repos/",
    "/visual studio", "/obj/", "/bin/", "/packages/", "/code/", "/.git/",
    "/temporary internet files/", "/cache/", "/thumbnails/", "/.thumbnails/",
    "/.gemini/", "/browser_recordings/",
)
SKIP_NAMES = ("folder.jpg", "albumartsmall.jpg", "thumbs.db")


@dataclass
class Candidate:
    sha256: str
    file_id: int
    drive_code: str
    rel_path: str
    size_bytes: int
    extension: str


def normalize(rel_path: str) -> str:
    return rel_path.replace("\\", "/").lstrip("/")


def skip_reason(rel_path: str, size_bytes: int, cfg: Config) -> str | None:
    low = "/" + normalize(rel_path).lower()
    name = PurePosixPath(low).name
    if any(part in low for part in SKIP_PATH_PARTS) or name in SKIP_NAMES \
            or name.startswith("albumart"):
        return "skipped_path"
    if (size_bytes or 0) < cfg.min_bytes:
        return "skipped_small"
    return None


class Manifests:
    """Where the harvester actually put each file.

    Harvester/manifests/harvest-<drive_code>.jsonl records src and dst for
    every copy. The catalog's path and the manifest's src can differ by a
    leading folder (NASR was scanned at M:\\OldNAS, harvested from M:\\), so each
    entry is indexed both whole and with its first folder dropped. The value is
    the dst tail after its <drive_code> folder, tried under every root.
    """

    def __init__(self, manifest_dir: Path):
        self.dir = manifest_dir
        self._by_drive: dict[str, dict[str, str]] = {}

    def _load(self, code: str) -> dict[str, str]:
        index: dict[str, str] = {}
        path = self.dir / f"harvest-{code}.jsonl"
        if not path.is_file():
            return index
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"copy"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                src, dst = d.get("src") or "", d.get("dst") or ""
                if d.get("action") != "copy" or not dst \
                        or not src.lower().endswith(PHOTO_EXTENSIONS):
                    continue
                parts = normalize(dst.split(":", 1)[-1]).split("/")
                if code not in parts:
                    continue
                tail = "/".join(parts[parts.index(code) + 1:])
                rel = normalize(src.split(":", 1)[-1]).lower()
                index.setdefault(rel, tail)
                if "/" in rel:
                    index.setdefault(rel.split("/", 1)[1], tail)
        log.info("manifest %s: %d photo entries", code, len(index))
        return index

    def tail(self, code: str, rel_path: str) -> str | None:
        if code not in self._by_drive:
            self._by_drive[code] = self._load(code)
        return self._by_drive[code].get(normalize(rel_path).lower())


def candidates(conn: sqlite3.Connection, recheck: bool = False) -> dict[str, list[Candidate]]:
    # The catalog stores some fingerprints upper-case (by scanner); one photo,
    # one row, so everything here is lower-case.
    marks = ",".join("?" for _ in PHOTO_EXTENSIONS)
    scope = ("lower(h.hash_value) IN (SELECT sha256 FROM photo_harvest WHERE status = 'unreadable')"
             if recheck else "lower(h.hash_value) NOT IN (SELECT sha256 FROM photo_harvest)")
    rows = conn.execute(
        f"""
        SELECT lower(h.hash_value), f.file_id, d.drive_code, f.path, f.size_bytes,
               lower(f.extension)
        FROM files f
        JOIN file_hashes h ON h.file_id = f.file_id AND h.hash_type = 'sha256'
        JOIN scans s ON s.scan_id = f.scan_id
        JOIN drives d ON d.drive_id = s.drive_id
        WHERE lower(f.extension) IN ({marks})
          AND {scope}
        ORDER BY lower(h.hash_value), f.file_id
        """,
        PHOTO_EXTENSIONS,
    ).fetchall()
    groups: dict[str, list[Candidate]] = {}
    for r in rows:
        groups.setdefault(r[0], []).append(Candidate(*r))
    return groups


def locate(c: Candidate, cfg: Config, manifests: Manifests | None) -> Path | None:
    tails = [normalize(c.rel_path)]
    if manifests is not None:
        t = manifests.tail(c.drive_code, c.rel_path)
        if t and t not in tails:
            tails.append(t)
    for root in (cfg.harvest_root, *cfg.alt_roots):
        for tail in tails:
            path = root / c.drive_code / tail
            if path.is_file():
                return path
    return None


def choose(group: list[Candidate], cfg: Config,
           manifests: Manifests | None = None) -> tuple[Candidate, str, Path | None]:
    """Pick the copy to describe and the row's starting status.

    A group is skipped only when every copy would be skipped: a photo that
    also lives in a Pictures folder is not lost because one copy sat in a
    cache.
    """
    keep = [c for c in group if skip_reason(c.rel_path, c.size_bytes, cfg) is None]
    if not keep:
        first = group[0]
        return first, skip_reason(first.rel_path, first.size_bytes, cfg), None
    for c in keep:
        if not c.drive_code:
            continue
        path = locate(c, cfg, manifests)
        if path is not None:
            return c, "pending", path
    return keep[0], "unreadable", None


def run(conn: sqlite3.Connection, cfg: Config, limit: int | None = None,
        recheck: bool = False) -> dict[str, int]:
    """Add new fingerprints, or with recheck, look again for unreadable ones."""
    groups = candidates(conn, recheck)
    manifests = Manifests(cfg.manifest_dir)
    tally: dict[str, int] = {}
    for i, (sha, group) in enumerate(groups.items()):
        if limit is not None and i >= limit:
            break
        chosen, status, path = choose(group, cfg, manifests)
        source = str(path) if path else str(
            cfg.harvest_root / (chosen.drive_code or "?") / normalize(chosen.rel_path))
        if recheck:
            if status != "unreadable":
                conn.execute(
                    """UPDATE photo_harvest SET source_path = ?, file_id = ?, drive_code = ?,
                       status = ?, error = NULL, updated_at = datetime('now')
                       WHERE sha256 = ? AND status = 'unreadable'""",
                    (source, chosen.file_id, chosen.drive_code, status, sha))
            tally[status] = tally.get(status, 0) + 1
            continue
        conn.execute(
            """INSERT OR IGNORE INTO photo_harvest
               (sha256, file_id, drive_code, source_path, size_bytes, extension,
                copies, status, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sha, chosen.file_id, chosen.drive_code, source, chosen.size_bytes,
             chosen.extension, len(group), status,
             "no copy found under the harvest root" if status == "unreadable" else None),
        )
        tally[status] = tally.get(status, 0) + 1
        if i % 1000 == 999:
            conn.commit()
            log.info("inventory: %d groups processed", i + 1)
    conn.commit()
    return tally
