"""Tests for the Photo Description Harvest local stages. [co-06tcu]

Run:  cd /root/projects/DataArchive && PYTHONPATH=python python/.venv/bin/python -m unittest python/tests/test_photo_harvest.py -v

The ones that matter most guard what must never leave the machine: the sent
copy carries no metadata, a held photo leaves no sendable copy behind, and a
photo is skipped only when every copy of it would be.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from photo_harvest import cli, inventory, store
from photo_harvest.config import Config
from photo_harvest.prepare import PrepareError, prepare_one, work_path

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "migrations" / "004_add_photo_harvest.sql"

CATALOG = """
CREATE TABLE schema_migrations (migration_id TEXT PRIMARY KEY, applied_at TIMESTAMP NOT NULL, description TEXT);
CREATE TABLE drives (drive_id INTEGER PRIMARY KEY, drive_code TEXT);
CREATE TABLE scans (scan_id INTEGER PRIMARY KEY, drive_id INTEGER);
CREATE TABLE files (file_id INTEGER PRIMARY KEY, scan_id INTEGER, path TEXT, size_bytes INTEGER, extension TEXT);
CREATE TABLE file_hashes (hash_id INTEGER PRIMARY KEY, scan_id INTEGER, file_id INTEGER, hash_type TEXT, hash_value TEXT, computed_at TIMESTAMP);
"""


def make_photo(path: Path, size=(3000, 2000), gps=True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, (90, 140, 200))
    exif = Image.Exif()
    exif[0x010F] = "Samsung"          # Make
    exif[0x0110] = "SM-G900"          # Model
    exif[0x0132] = "2014:07:15 10:16:05"
    exif[0x0112] = 6                  # Orientation: rotate 90
    if gps:
        exif[0x8825] = {1: "N", 2: (30.0, 15.0, 0.0), 3: "W", 4: (97.0, 45.0, 0.0)}
    img.save(path, "JPEG", exif=exif)


class FakeScreener:
    def __init__(self):
        self.held_now = False
        self.seen = []

    def check(self, image_path):
        self.seen.append(Path(image_path))
        return (True, 0.91, ["FEMALE_BREAST_EXPOSED"]) if self.held_now else (False, 0.02, [])


class HarvestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "Harvest"
        self.db = self.tmp / "archive.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(CATALOG)
        conn.executescript(MIGRATION.read_text())
        conn.executemany("INSERT INTO drives VALUES (?, ?)", [(1, "AAAA"), (2, "BBBB")])
        conn.executemany("INSERT INTO scans VALUES (?, ?)", [(1, 1), (2, 2)])
        conn.commit()
        conn.close()
        self.alt = self.tmp / "F"
        self.manifests = self.tmp / "manifests"
        self.manifests.mkdir()
        self.cfg = Config(db_path=self.db, harvest_root=self.root, alt_roots=(self.alt,),
                          manifest_dir=self.manifests, work_dir=self.tmp / "work",
                          min_bytes=20_000, min_side=200, max_side=1568, jpeg_quality=85,
                          screen_threshold=0.25)
        self.next_id = 1

    def add_copy(self, sha, drive_id, rel, size=500_000, ext=".jpg"):
        conn = sqlite3.connect(self.db)
        fid = self.next_id
        self.next_id += 1
        conn.execute("INSERT INTO files VALUES (?, ?, ?, ?, ?)", (fid, drive_id, rel, size, ext))
        conn.execute("INSERT INTO file_hashes VALUES (NULL, ?, ?, 'sha256', ?, datetime('now'))",
                     (drive_id, fid, sha))
        conn.commit()
        conn.close()

    def rows(self):
        conn = store.connect(self.db)
        out = {r["sha256"]: dict(r) for r in conn.execute("SELECT * FROM photo_harvest")}
        conn.close()
        return out

    # --- inventory -------------------------------------------------------

    def test_inventory_picks_the_copy_that_exists(self):
        self.add_copy("a" * 64, 1, "Missing/IMG_1.jpg")
        self.add_copy("a" * 64, 2, "Pictures\\2014\\IMG_1.jpg")   # backslashes, as Windows scans store them
        make_photo(self.root / "BBBB" / "Pictures" / "2014" / "IMG_1.jpg")
        with store.connect(self.db) as conn:
            tally = inventory.run(conn, self.cfg)
        row = self.rows()["a" * 64]
        self.assertEqual(tally, {"pending": 1})
        self.assertEqual(row["copies"], 2)
        self.assertEqual(row["drive_code"], "BBBB")
        self.assertTrue(row["source_path"].endswith("Pictures/2014/IMG_1.jpg"))

    def test_skipped_only_when_every_copy_would_be(self):
        self.add_copy("b" * 64, 1, "Program Files/App/splash.jpg")
        self.add_copy("c" * 64, 1, "AppData/Local/cache/x.jpg")
        self.add_copy("c" * 64, 2, "Pictures/x.jpg")
        self.add_copy("d" * 64, 1, "Pictures/tiny.jpg", size=4_000)
        make_photo(self.root / "BBBB" / "Pictures" / "x.jpg")
        with store.connect(self.db) as conn:
            inventory.run(conn, self.cfg)
        rows = self.rows()
        self.assertEqual(rows["b" * 64]["status"], "skipped_path")
        self.assertEqual(rows["c" * 64]["status"], "pending")
        self.assertEqual(rows["d" * 64]["status"], "skipped_small")

    def test_manifest_and_alternate_root_find_moved_copies(self):
        # NASR-style: scanned at M:\\OldNAS, harvested from M:\\ into an extra OldNAS folder
        self.add_copy("1" * 64, 1, "Public/Shared Pictures/P1.JPG")
        (self.manifests / "harvest-AAAA.jsonl").write_text(json.dumps({
            "src": "M:\\OldNAS\\Public\\Shared Pictures\\P1.JPG", "action": "copy",
            "dst": "Z:\\Harvest\\AAAA\\OldNAS\\Public\\Shared Pictures\\P1.JPG"}) + "\n")
        make_photo(self.root / "AAAA" / "OldNAS" / "Public" / "Shared Pictures" / "P1.JPG")
        # Tera1A-style: harvested to F:\\<code>\\ instead of Z:\\Harvest
        self.add_copy("2" * 64, 2, "PicasaRoot/Scans/s1.JPG")
        make_photo(self.alt / "BBBB" / "PicasaRoot" / "Scans" / "s1.JPG")
        with store.connect(self.db) as conn:
            inventory.run(conn, self.cfg)
        rows = self.rows()
        self.assertEqual(rows["1" * 64]["status"], "pending")
        self.assertIn("OldNAS", rows["1" * 64]["source_path"])
        self.assertEqual(rows["2" * 64]["status"], "pending")
        self.assertTrue(rows["2" * 64]["source_path"].startswith(str(self.alt)))

    def test_recheck_promotes_an_unreadable_photo_once_found(self):
        self.add_copy("3" * 64, 1, "Pictures/late.jpg")
        with store.connect(self.db) as conn:
            inventory.run(conn, self.cfg)
            self.assertEqual(self.rows()["3" * 64]["status"], "unreadable")
            make_photo(self.alt / "AAAA" / "Pictures" / "late.jpg")
            self.assertEqual(inventory.run(conn, self.cfg, recheck=True), {"pending": 1})
        self.assertEqual(self.rows()["3" * 64]["status"], "pending")

    def test_upper_and_lower_case_fingerprints_are_one_photo(self):
        self.add_copy("ab" * 32, 1, "Pictures/one.jpg")
        self.add_copy("AB" * 32, 2, "Backup/one.jpg")
        make_photo(self.root / "AAAA" / "Pictures" / "one.jpg")
        with store.connect(self.db) as conn:
            inventory.run(conn, self.cfg)
            self.assertEqual(inventory.run(conn, self.cfg), {})
        rows = self.rows()
        self.assertEqual(list(rows), ["ab" * 32])
        self.assertEqual(rows["ab" * 32]["copies"], 2)

    def test_no_copy_on_disk_is_unreadable_and_rerun_adds_nothing(self):
        self.add_copy("e" * 64, 1, "Pictures/gone.jpg")
        with store.connect(self.db) as conn:
            inventory.run(conn, self.cfg)
            self.assertEqual(inventory.run(conn, self.cfg), {})
        self.assertEqual(self.rows()["e" * 64]["status"], "unreadable")

    # --- prepare ---------------------------------------------------------

    def test_sent_copy_has_no_metadata_and_details_stay_local(self):
        src = self.tmp / "orig.jpg"
        make_photo(src)
        before = src.read_bytes()
        dest = self.tmp / "out" / "x.jpg"
        info = prepare_one(src, dest, self.cfg)
        self.assertEqual(src.read_bytes(), before, "original must never change")
        with Image.open(dest) as out:
            self.assertEqual(len(out.getexif()), 0)
            self.assertNotIn("icc_profile", out.info)
            self.assertNotIn("exif", out.info)
            self.assertEqual(max(out.size), 1568)
            self.assertGreater(out.size[1], out.size[0], "orientation 6 must come out upright (portrait)")
        self.assertEqual(info["camera"], "Samsung SM-G900")
        self.assertEqual(info["taken_at"], "2014:07:15 10:16:05")
        self.assertAlmostEqual(info["gps_lat"], 30.25)
        self.assertAlmostEqual(info["gps_lon"], -97.75)

    def test_tiny_and_corrupt_images_raise(self):
        small = self.tmp / "s.jpg"
        Image.new("RGB", (120, 90)).save(small, "JPEG")
        with self.assertRaisesRegex(PrepareError, "too small"):
            prepare_one(small, self.tmp / "o1.jpg", self.cfg)
        zeros = self.tmp / "z.jpg"
        zeros.write_bytes(bytes(379_358))
        with self.assertRaisesRegex(PrepareError, "zero-filled"):
            prepare_one(zeros, self.tmp / "o0.jpg", self.cfg)
        bad = self.tmp / "bad.jpg"
        bad.write_bytes(b"not a jpeg at all")
        with self.assertRaises(PrepareError):
            prepare_one(bad, self.tmp / "o2.jpg", self.cfg)

    # --- prepare + screen ------------------------------------------------

    def _pending(self, sha, name):
        self.add_copy(sha, 1, f"Pictures/{name}")
        make_photo(self.root / "AAAA" / "Pictures" / name)

    def test_held_photo_leaves_no_sendable_copy(self):
        self._pending("f" * 64, "f.jpg")
        with store.connect(self.db) as conn:
            inventory.run(conn, self.cfg)
        screener = FakeScreener()
        screener.held_now = True
        cli.cmd_prepare(self.cfg, SimpleNamespace(limit=None), screener=screener)
        row = self.rows()["f" * 64]
        self.assertEqual(row["status"], "held_sensitive")
        self.assertEqual(row["screen_classes"], "FEMALE_BREAST_EXPOSED")
        self.assertFalse(work_path(self.cfg, "f" * 64).exists())

    def test_clean_photo_is_ready_with_its_copy(self):
        self._pending("0" * 64, "g.jpg")
        with store.connect(self.db) as conn:
            inventory.run(conn, self.cfg)
        screener = FakeScreener()
        screener.held_now = False
        cli.cmd_prepare(self.cfg, SimpleNamespace(limit=None), screener=screener)
        row = self.rows()["0" * 64]
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["camera"], "Samsung SM-G900")
        self.assertTrue(work_path(self.cfg, "0" * 64).exists())

    def test_unknown_status_is_refused(self):
        with store.connect(self.db) as conn:
            with self.assertRaises(store.StoreError):
                store.update(conn, "x", status="sent-ish")


class SendTest(HarvestTest):
    """Result handling, with fake batch results shaped like the SDK's."""

    def _row(self, sha):
        self._pending(sha, f"{sha[:4]}.jpg")
        with store.connect(self.db) as conn:
            inventory.run(conn, self.cfg)
            store.update(conn, sha, status="submitted", batch_id="b1")
            conn.commit()
        work_path(self.cfg, sha).parent.mkdir(parents=True, exist_ok=True)
        work_path(self.cfg, sha).write_bytes(b"x")

    @staticmethod
    def _result(sha, text=None, stop="end_turn", kind="succeeded"):
        usage = SimpleNamespace(input_tokens=1700, output_tokens=90)
        msg = SimpleNamespace(stop_reason=stop, usage=usage,
                              content=[SimpleNamespace(type="text", text=text or "")])
        err = SimpleNamespace(error=SimpleNamespace(message="overloaded"))
        return SimpleNamespace(custom_id=sha, result=SimpleNamespace(type=kind, message=msg, error=err))

    def test_described_result_is_stored_and_copy_removed(self):
        from photo_harvest.send import apply_result, spent
        sha = "5" * 64
        self._row(sha)
        body = {"description": "Two boys on a dock.", "tags": ["people", "water or boat"],
                "extra_tags": ["dock", "summer", "lake", "extra"], "people": 2, "setting": "outdoor",
                "text_visible": "", "quality": "fine", "sensitive": False}
        with store.connect(self.db) as conn:
            self.assertEqual(apply_result(conn, self._result(sha, json.dumps(body)), self.cfg), "described")
            conn.commit()
            self.assertAlmostEqual(spent(conn), 1700 / 1e6 * 0.05 + 90 / 1e6 * 0.25)
        row = self.rows()[sha]
        self.assertEqual(row["description"], "Two boys on a dock.")
        self.assertEqual(json.loads(row["tags_json"]), ["people", "water or boat", "dock", "summer", "lake"])
        self.assertIsNone(row["text_visible"])
        self.assertFalse(work_path(self.cfg, sha).exists())

    def test_refusal_and_error_and_garbage(self):
        from photo_harvest.send import apply_result
        for sha, res, want in (
            ("6" * 64, self._result("6" * 64, stop="refusal"), "declined"),
            ("7" * 64, self._result("7" * 64, kind="errored"), "failed"),
            ("8" * 64, self._result("8" * 64, text="not json"), "failed"),
        ):
            self._row(sha)
            with store.connect(self.db) as conn:
                self.assertEqual(apply_result(conn, res, self.cfg), want)
                conn.commit()
            self.assertEqual(self.rows()[sha]["status"], want)

    def test_load_key_reads_only_the_named_line(self):
        from photo_harvest.send import SendError, load_key
        vault = self.tmp / "env"
        vault.write_text("OTHER=1\nexport ANTHROPIC_API_KEY='sk-ant-test'\n")
        self.assertEqual(load_key(vault), "sk-ant-test")
        vault.write_text("OTHER=1\n")
        with self.assertRaises(SendError):
            load_key(vault)


if __name__ == "__main__":
    unittest.main()
