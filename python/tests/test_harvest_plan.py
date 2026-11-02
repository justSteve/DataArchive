"""Tests for harvest_plan.py dedupe against the master archive. [co-2xplv]

Run:  cd /root/projects/DataArchive && PYTHONPATH=python python3 -m unittest python/tests/test_harvest_plan.py -v

What these guard: a file is skipped as a duplicate only when its twin is really on Z:
(checked on disk under --verify-root), fingerprints match regardless of case, and drives
harvested without a progress file (DVRC, Tera1A, NASR) still count as archived.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import harvest_plan as hp

SCHEMA = """
CREATE TABLE drives (drive_id INTEGER PRIMARY KEY, drive_code TEXT, label TEXT);
CREATE TABLE scans (scan_id INTEGER PRIMARY KEY, drive_id INTEGER);
CREATE TABLE files (file_id INTEGER PRIMARY KEY, scan_id INTEGER, path TEXT, size_bytes INTEGER, extension TEXT);
CREATE TABLE file_hashes (hash_id INTEGER PRIMARY KEY, scan_id INTEGER, file_id INTEGER, hash_type TEXT, hash_value TEXT);
"""
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64


class World:
    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.z = root / "z"
        self.harvester = root / "Harvester"
        (self.harvester / "progress").mkdir(parents=True)
        (self.harvester / "manifests").mkdir()
        self.db_path = root / "archive.db"
        self.db = sqlite3.connect(self.db_path)
        self.db.executescript(SCHEMA)
        self.fid = 0

    def drive(self, code: str, scan_id: int) -> None:
        self.db.execute("INSERT INTO drives VALUES (?, ?, ?)", (scan_id, code, code))
        self.db.execute("INSERT INTO scans VALUES (?, ?)", (scan_id, scan_id))

    def file(self, scan_id: int, path: str, size: int, h: str | None) -> None:
        self.fid += 1
        self.db.execute("INSERT INTO files VALUES (?, ?, ?, ?, ?)",
                        (self.fid, scan_id, path, size, Path(path).suffix))
        if h:
            self.db.execute("INSERT INTO file_hashes (scan_id, file_id, hash_type, hash_value) VALUES (?, ?, 'sha256', ?)",
                            (scan_id, self.fid, h))
        self.db.commit()

    def on_z(self, rel: str, size: int) -> None:
        p = self.z / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)

    def run(self, config: dict, *extra: str) -> list[dict]:
        cfg = Path(self.tmp.name) / "cfg.json"
        cfg.write_text(json.dumps(config))
        argv = ["harvest_plan.py", "--config", str(cfg), "--db", str(self.db_path),
                "--staging", "Z:\\Harvest", "--verify-root", str(self.z), *extra]
        with mock.patch.object(hp, "HARVESTER_ROOT_WSL", self.harvester), \
                mock.patch.object(sys, "argv", argv), mock.patch("builtins.print"):
            hp.main()
        out = self.harvester / "manifests" / f"harvest-{config['label']}.jsonl"
        return [json.loads(l) for l in out.read_text().splitlines()]


def by_path(recs: list[dict]) -> dict[str, dict]:
    return {r["src"].split("\\")[-1]: r for r in recs}


class NormHash(unittest.TestCase):
    def test_case_and_prefix(self) -> None:
        self.assertEqual(hp.norm_hash("sha256:" + A.upper()), A)
        self.assertEqual(hp.norm_hash(A.upper()), A)
        self.assertIsNone(hp.norm_hash(None))


class ArchivePath(unittest.TestCase):
    def test_staging_and_z_paths_map_under_harvest(self) -> None:
        z = "/mnt/z"
        self.assertEqual(hp.archive_path("W:\\DTJX\\a\\b.txt", z), "/mnt/z/Harvest/DTJX/a/b.txt")
        self.assertEqual(hp.archive_path("F:\\WWYY\\x.xls", z), "/mnt/z/Harvest/WWYY/x.xls")
        self.assertEqual(hp.archive_path("Z:\\Harvest\\SVNK\\u\\f.url", z), "/mnt/z/Harvest/SVNK/u/f.url")


class Plan(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World()
        self.addCleanup(self.w.tmp.cleanup)
        self.w.drive("WWYY", 1)
        self.w.drive("Tera1A", 2)
        self.w.drive("NASR", 3)
        self.w.drive("DVRC", 4)
        self.w.drive("X1BK", 9)
        # WWYY copied with an upper-case progress record; twin present on Z.
        (self.w.harvester / "progress" / "harvest-WWYY.progress.jsonl").write_text(
            json.dumps({"dst": "F:\\WWYY\\w.xls", "status": "done", "bytes": 10, "hash": A.upper()}) + "\n")
        self.w.on_z("Harvest/WWYY/w.xls", 10)
        # Tera1A: catalogued upper-case, no progress file; one file on Z, one never copied.
        self.w.file(2, "My Pictures/t.jpg", 20, B.upper())
        self.w.on_z("Harvest/Tera1A/My Pictures/t.jpg", 20)
        self.w.file(2, "PicasaRoot/p.jpg", 30, C.upper())
        # NASR: catalogued under OldNAS's root, on Z under Harvest/NASR/OldNAS.
        self.w.file(3, "Steve/n.doc", 40, D)
        self.w.on_z("Harvest/NASR/OldNAS/Steve/n.doc", 40)
        # DVRC: catalogued, but the file never reached Z.
        self.w.file(4, "Users/steve/.gemini/r.jpg", 50, E)
        # X1BK, the new scan: each matches one of the above (lower-case), plus an internal duplicate.
        for name, size, h in [("w.xls", 10, A), ("t.jpg", 20, B), ("p.jpg", 30, C),
                              ("n.doc", 40, D), ("r.jpg", 50, E)]:
            self.w.file(9, f"Users/steve/{name}", size, h)
        self.w.file(9, "Users/steve/copy-of-p.jpg", 30, C)
        self.cfg = {"label": "X1BK", "drive_letter": "W", "source_root": "W:\\X1-backup",
                    "exclude_paths": []}

    def test_dupes_only_when_twin_is_on_z(self) -> None:
        recs = by_path(self.w.run(self.cfg))
        self.assertEqual(recs["w.xls"]["action"], "skip:dupe")      # upper-case progress hash
        self.assertEqual(recs["t.jpg"]["action"], "skip:dupe")      # Tera1A, no progress file
        self.assertEqual(recs["n.doc"]["action"], "skip:dupe")      # NASR, OldNAS prefix
        self.assertEqual(recs["p.jpg"]["action"], "copy")           # Tera1A claim, twin not on Z
        self.assertEqual(recs["r.jpg"]["action"], "copy")           # DVRC claim, twin not on Z
        self.assertIn("dupe_unverified", recs["r.jpg"])
        self.assertEqual(recs["copy-of-p.jpg"]["action"], "skip:dupe")  # same file earlier in this run

    def test_source_root_and_destination(self) -> None:
        recs = by_path(self.w.run(self.cfg))
        self.assertEqual(recs["p.jpg"]["src"], "W:\\X1-backup\\Users\\steve\\p.jpg")
        self.assertEqual(recs["p.jpg"]["dst"], "Z:\\Harvest\\X1BK\\Users\\steve\\p.jpg")


if __name__ == "__main__":
    unittest.main()
