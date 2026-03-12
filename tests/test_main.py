#!/usr/bin/env python3
"""
Tests for main.py — smart_organize and undo_smart_organize

Run with:
    python -m pytest tests/test_main.py -v
    # or
    python tests/test_main.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make the parent directory importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import (
    FILE_CATEGORIES,
    LOG_FILENAME,
    _category_for,
    _log_path,
    smart_organize,
    undo_smart_organize,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_file(path: Path, content: bytes = b"test content") -> Path:
    """Create a file with the given bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ─── Unit tests: helpers ───────────────────────────────────────────────────────

class TestCategoryFor(unittest.TestCase):

    def test_known_extensions(self):
        pairs = [
            ("report.pdf",   "Documents"),
            ("photo.jpg",    "Images"),
            ("clip.mp4",     "Videos"),
            ("track.mp3",    "Music"),
            ("backup.zip",   "Archives"),
            ("data.xlsx",    "Spreadsheets"),
            ("slides.pptx",  "Presentations"),
            ("script.py",    "Code"),
            ("logo.psd",     "Design"),
            ("setup.exe",    "Executables"),
            ("font.ttf",     "Fonts"),
        ]
        for filename, expected in pairs:
            with self.subTest(filename=filename):
                self.assertEqual(_category_for(filename), expected)

    def test_unknown_extension_returns_none(self):
        self.assertIsNone(_category_for("mysterious.xyz"))
        self.assertIsNone(_category_for("noextension"))

    def test_case_insensitive(self):
        self.assertEqual(_category_for("IMAGE.JPG"), "Images")
        self.assertEqual(_category_for("DOC.PDF"),   "Documents")

    def test_log_filename_category(self):
        # organize.log should have no category (it's a .log extension)
        self.assertIsNone(_category_for(LOG_FILENAME))


class TestLogPath(unittest.TestCase):

    def test_log_path_inside_target(self):
        target = Path("/some/dir")
        self.assertEqual(_log_path(target), target / LOG_FILENAME)


# ─── Integration tests: smart_organize ────────────────────────────────────────

class TestSmartOrganize(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, target=None):
        smart_organize(target or self.tmp)

    def test_moves_known_files(self):
        _make_file(self.tmp / "report.pdf")
        _make_file(self.tmp / "photo.jpg")
        _make_file(self.tmp / "song.mp3")
        self._run()

        self.assertTrue((self.tmp / "Documents" / "report.pdf").exists())
        self.assertTrue((self.tmp / "Images"    / "photo.jpg").exists())
        self.assertTrue((self.tmp / "Music"     / "song.mp3").exists())

        # Originals should no longer exist at root
        self.assertFalse((self.tmp / "report.pdf").exists())
        self.assertFalse((self.tmp / "photo.jpg").exists())
        self.assertFalse((self.tmp / "song.mp3").exists())

    def test_unknown_extension_stays_in_place(self):
        unknown = _make_file(self.tmp / "mystery.xyz")
        self._run()
        self.assertTrue(unknown.exists())

    def test_hidden_files_are_skipped(self):
        hidden = _make_file(self.tmp / ".hidden_file")
        self._run()
        self.assertTrue(hidden.exists())

    def test_log_file_written(self):
        _make_file(self.tmp / "doc.pdf")
        self._run()
        log_file = _log_path(self.tmp)
        self.assertTrue(log_file.exists())

    def test_log_file_not_moved(self):
        """organize.log itself must not be moved."""
        _make_file(self.tmp / "doc.pdf")
        self._run()
        # Run twice; the log written by the first run must not be moved
        self._run()
        self.assertTrue(_log_path(self.tmp).exists())

    def test_log_structure(self):
        _make_file(self.tmp / "img.png")
        self._run()
        log_data = json.loads(_log_path(self.tmp).read_text())
        self.assertEqual(log_data["version"], 1)
        self.assertIn("organized", log_data)
        self.assertIn("moves", log_data)
        self.assertEqual(len(log_data["moves"]), 1)
        move = log_data["moves"][0]
        self.assertIn("src", move)
        self.assertIn("dest", move)
        self.assertIn("timestamp", move)

    def test_duplicate_filename_handling(self):
        """If the destination already has a file with the same name, add a counter."""
        (self.tmp / "Images").mkdir()
        _make_file(self.tmp / "Images" / "photo.jpg", b"existing")
        _make_file(self.tmp / "photo.jpg", b"new")
        self._run()
        # Both files should exist; the moved one gets a unique name
        dest_dir = self.tmp / "Images"
        files_in_dest = list(dest_dir.iterdir())
        self.assertEqual(len(files_in_dest), 2)

    def test_empty_directory(self):
        """Running on an empty directory should produce an empty log."""
        self._run()
        log_data = json.loads(_log_path(self.tmp).read_text())
        self.assertEqual(log_data["moves"], [])

    def test_string_path_accepted(self):
        _make_file(self.tmp / "file.txt")
        smart_organize(str(self.tmp))
        self.assertTrue((self.tmp / "Documents" / "file.txt").exists())


# ─── Integration tests: undo_smart_organize ───────────────────────────────────

class TestUndoSmartOrganize(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _organize_then_undo(self):
        smart_organize(self.tmp)
        undo_smart_organize(self.tmp)

    def test_restores_files(self):
        _make_file(self.tmp / "report.pdf")
        _make_file(self.tmp / "photo.png")
        self._organize_then_undo()

        self.assertTrue((self.tmp / "report.pdf").exists())
        self.assertTrue((self.tmp / "photo.png").exists())

    def test_log_removed_after_undo(self):
        _make_file(self.tmp / "track.mp3")
        self._organize_then_undo()
        self.assertFalse(_log_path(self.tmp).exists())

    def test_empty_category_dirs_removed(self):
        _make_file(self.tmp / "doc.pdf")
        self._organize_then_undo()
        self.assertFalse((self.tmp / "Documents").exists())

    def test_undo_without_log_exits(self):
        with self.assertRaises(SystemExit):
            undo_smart_organize(self.tmp)

    def test_undo_then_files_at_original_locations(self):
        files = ["a.pdf", "b.jpg", "c.mp3", "d.zip"]
        for f in files:
            _make_file(self.tmp / f)

        smart_organize(self.tmp)
        undo_smart_organize(self.tmp)

        for f in files:
            self.assertTrue((self.tmp / f).exists(), f"{f} not restored")

    def test_undo_with_empty_log(self):
        """An empty moves list should not raise and should clean up the log."""
        log_data = {
            "version": 1,
            "organized": "2024-01-01T00:00:00Z",
            "target": str(self.tmp),
            "moves": [],
        }
        _log_path(self.tmp).write_text(json.dumps(log_data))
        undo_smart_organize(self.tmp)
        self.assertFalse(_log_path(self.tmp).exists())

    def test_undo_string_path_accepted(self):
        _make_file(self.tmp / "file.txt")
        smart_organize(str(self.tmp))
        undo_smart_organize(str(self.tmp))
        self.assertTrue((self.tmp / "file.txt").exists())


# ─── File category completeness ───────────────────────────────────────────────

class TestFileCategoriesStructure(unittest.TestCase):

    def test_no_empty_categories(self):
        for cat, exts in FILE_CATEGORIES.items():
            self.assertTrue(exts, f"Category '{cat}' has no extensions")

    def test_all_extensions_lowercase_with_dot(self):
        for cat, exts in FILE_CATEGORIES.items():
            for ext in exts:
                self.assertTrue(ext.startswith("."),
                                f"Extension '{ext}' in '{cat}' missing leading dot")
                self.assertEqual(ext, ext.lower(),
                                 f"Extension '{ext}' in '{cat}' is not lower-case")

    def test_no_duplicate_extensions_across_categories(self):
        seen: dict[str, str] = {}
        for cat, exts in FILE_CATEGORIES.items():
            for ext in exts:
                if ext in seen:
                    self.fail(
                        f"Extension '{ext}' appears in both '{seen[ext]}' and '{cat}'"
                    )
                seen[ext] = cat


if __name__ == "__main__":
    unittest.main(verbosity=2)
