#!/usr/bin/env python3
"""
Tests for smart_organizer.py — AI-Enhanced File Organiser

Run with:
    python -m pytest tests/test_smart_organizer.py -v
    # or
    python tests/test_smart_organizer.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make the parent directory importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from smart_organizer import (
    CATEGORY_MAP,
    CognitiveMode,
    ContentAnalyzer,
    AdaptiveCategorizer,
    _get_category_ext,
    get_category,
    quick_hash,
    unique_dest,
    should_skip,
    collect_files,
    build_plan,
    save_undo_log,
    perform_undo,
    save_plan_file,
    load_plan_file,
    save_tags,
    execute_plan,
    JUNK_FILES,
    UNDO_DIR_NAME,
    PLAN_FILENAME,
    TAGS_FILENAME,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_file(path: Path, content: bytes = b"test content") -> Path:
    """Create a file with the given bytes at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ─── CognitiveMode ────────────────────────────────────────────────────────────

class TestCognitiveMode(unittest.TestCase):

    def test_values(self) -> None:
        self.assertEqual(CognitiveMode.EXTENSION.value, "extension")
        self.assertEqual(CognitiveMode.CONTENT.value,   "content")
        self.assertEqual(CognitiveMode.ADAPTIVE.value,  "adaptive")

    def test_from_string(self) -> None:
        self.assertEqual(CognitiveMode("extension"), CognitiveMode.EXTENSION)
        self.assertEqual(CognitiveMode("adaptive"),  CognitiveMode.ADAPTIVE)

    def test_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            CognitiveMode("invalid_mode")


# ─── ContentAnalyzer — magic bytes ────────────────────────────────────────────

class TestContentAnalyzerMagicBytes(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.analyzer = ContentAnalyzer(enable_ocr=False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make(self, name: str, header: bytes) -> Path:
        p = self.root / name
        p.write_bytes(header + b"\x00" * 16)
        return p

    def test_png_header(self) -> None:
        p = self._make("test.png", b"\x89PNG\r\n\x1a\n")
        cat, conf, tags = self.analyzer.analyze(p)
        self.assertEqual(cat, "Images")
        # Confidence varies with available optional libraries (python-magic);
        # magic bytes alone give ≥ 0.40 of the combined score.
        self.assertGreaterEqual(conf, 0.40)
        self.assertIn("magic:images", tags)

    def test_jpeg_header(self) -> None:
        p = self._make("test.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF")
        cat, conf, tags = self.analyzer.analyze(p)
        self.assertEqual(cat, "Images")
        self.assertGreater(conf, 0.5)

    def test_pdf_header(self) -> None:
        p = self._make("test.pdf", b"%PDF-1.7\n")
        cat, conf, tags = self.analyzer.analyze(p)
        self.assertEqual(cat, "Documents")
        # Minimum confidence from magic bytes alone (0.99 × 0.45 ≈ 0.44)
        self.assertGreaterEqual(conf, 0.40)

    def test_flac_header(self) -> None:
        p = self._make("test.flac", b"fLaC\x00\x00\x00\x22")
        cat, conf, tags = self.analyzer.analyze(p)
        self.assertEqual(cat, "Audio")

    def test_gzip_header(self) -> None:
        p = self._make("test.gz", b"\x1f\x8b\x08\x00")
        cat, conf, tags = self.analyzer.analyze(p)
        self.assertEqual(cat, "Archives")

    def test_sqlite_header(self) -> None:
        p = self._make("test.db", b"SQLite format 3\x00")
        cat, conf, tags = self.analyzer.analyze(p)
        self.assertEqual(cat, "Databases")

    def test_elf_binary(self) -> None:
        p = self._make("test_bin", b"\x7fELF\x02\x01\x01\x00")
        cat, conf, tags = self.analyzer.analyze(p)
        self.assertEqual(cat, "Executables")

    def test_unknown_binary(self) -> None:
        # Random bytes with no known signature
        p = self._make("test.xyz", b"\xDE\xAD\xBE\xEF\x01\x02\x03\x04")
        cat, conf, tags = self.analyzer.analyze(p)
        # Should return empty (no magic match, not text-readable)
        self.assertEqual(cat, "")
        self.assertEqual(conf, 0.0)

    def test_missing_file(self) -> None:
        p = self.root / "nonexistent.png"
        cat, conf, tags = self.analyzer.analyze(p)
        # Should not raise; returns empty result
        self.assertEqual(cat, "")

    def test_empty_file(self) -> None:
        p = self.root / "empty.png"
        p.write_bytes(b"")
        cat, conf, tags = self.analyzer.analyze(p)
        # Empty file matches no signature
        self.assertEqual(cat, "")


# ─── ContentAnalyzer — text keywords ─────────────────────────────────────────

class TestContentAnalyzerTextKeywords(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.analyzer = ContentAnalyzer()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_txt(self, name: str, text: str) -> Path:
        p = self.root / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_invoice_keywords(self) -> None:
        p = self._make_txt(
            "bill.txt",
            "Invoice\nAmount due: $500\nPayment terms: Net 30\n",
        )
        cat, conf, tags = self.analyzer._text_keywords(p)
        self.assertIsNotNone(cat)
        self.assertIn("Invoices", cat)
        self.assertGreater(conf, 0.0)
        self.assertTrue(any("kw:" in t for t in tags))

    def test_resume_keywords(self) -> None:
        p = self._make_txt(
            "cv.txt",
            "Resume\nWork experience: 5 years\nReferences available upon request.\n",
        )
        cat, conf, tags = self.analyzer._text_keywords(p)
        self.assertIsNotNone(cat)
        self.assertIn("Resumes", cat)

    def test_contract_keywords(self) -> None:
        p = self._make_txt(
            "contract.txt",
            "This Agreement is made between the parties. Terms and conditions hereby apply.",
        )
        cat, conf, tags = self.analyzer._text_keywords(p)
        self.assertIsNotNone(cat)
        self.assertIn("Contracts", cat)

    def test_no_keywords(self) -> None:
        p = self._make_txt("random.txt", "Hello world, this is a random file.")
        cat, conf, tags = self.analyzer._text_keywords(p)
        # No keyword match → returns None
        self.assertIsNone(cat)

    def test_non_text_extension_skipped(self) -> None:
        # .png is not in _TEXT_READABLE_EXTS and is not .pdf
        p = self.root / "image.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n")
        cat, conf, tags = self.analyzer._text_keywords(p)
        self.assertIsNone(cat)

    def test_read_text_safe_utf8(self) -> None:
        p = self._make_txt("utf8.txt", "Hello UTF-8")
        text = ContentAnalyzer._read_text_safe(p)
        self.assertIsNotNone(text)
        self.assertIn("Hello", text)

    def test_read_text_safe_missing(self) -> None:
        p = self.root / "missing.txt"
        text = ContentAnalyzer._read_text_safe(p)
        self.assertIsNone(text)


# ─── AdaptiveCategorizer ─────────────────────────────────────────────────────

class TestAdaptiveCategorizer(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make(self, name: str, content: bytes = b"data") -> Path:
        p = self.root / name
        p.write_bytes(content)
        return p

    def test_extension_mode_png(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.EXTENSION)
        p = self._make("photo.png")
        cat, conf, tags = cat_obj.categorize(p)
        self.assertEqual(cat, "Images")
        self.assertEqual(tags, [])

    def test_extension_mode_mp3(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.EXTENSION)
        p = self._make("song.mp3")
        cat, conf, tags = cat_obj.categorize(p)
        self.assertEqual(cat, "Audio")

    def test_extension_mode_no_ext(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.EXTENSION)
        p = self._make("Makefile")
        cat, conf, tags = cat_obj.categorize(p)
        self.assertEqual(cat, "No_Extension")

    def test_extension_mode_unknown_ext(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.EXTENSION)
        p = self._make("file.xyz123")
        cat, conf, tags = cat_obj.categorize(p)
        self.assertEqual(cat, "XYZ123_Files")

    def test_content_mode_png_header(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.CONTENT)
        # Write a .txt file but with PNG header bytes
        p = self._make("disguised.txt", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        cat, conf, tags = cat_obj.categorize(p)
        # Content mode should detect Images from magic bytes
        self.assertEqual(cat, "Images")
        self.assertGreater(conf, 0.4)

    def test_content_mode_fallback_to_ext(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.CONTENT)
        # All-zero bytes: no magic match, python-magic returns octet-stream
        # → content_cat is empty → must fall back to extension (.mp4 = Videos)
        p = self._make("data.mp4", b"\x00" * 20)
        cat, conf, tags = cat_obj.categorize(p)
        # Extension fallback: Videos
        self.assertEqual(cat, "Videos")

    def test_adaptive_mode_returns_category(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.ADAPTIVE)
        p = self._make("archive.zip", b"PK\x03\x04" + b"\x00" * 20)
        cat, conf, tags = cat_obj.categorize(p)
        # Both extension and magic bytes agree → Archives
        self.assertEqual(cat, "Archives")

    def test_adaptive_mode_weight_shift(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.ADAPTIVE)
        initial_w = cat_obj._weights["content"]
        # Disguised file: .txt extension but PNG header (high-confidence mismatch)
        p = self._make("fake.txt", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        cat_obj.categorize(p)
        # Weight should shift toward content
        self.assertGreaterEqual(cat_obj._weights["content"], initial_w)

    def test_get_sub_category_invoice(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.CONTENT)
        p = self.root / "bill.txt"
        p.write_text(
            "Invoice\nAmount due: $500\nPayment terms: Net 30\n", encoding="utf-8"
        )
        sub = cat_obj.get_sub_category(p, "Documents")
        self.assertIsNotNone(sub)
        self.assertEqual(sub, "Invoices")

    def test_get_sub_category_none_for_non_doc(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.CONTENT)
        p = self._make("photo.png", b"\x89PNG\r\n\x1a\n")
        sub = cat_obj.get_sub_category(p, "Documents")
        self.assertIsNone(sub)

    def test_record_confirmation_does_not_raise(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.ADAPTIVE)
        for _ in range(55):  # trigger recalibrate at 50
            cat_obj.record_confirmation("Documents", "extension")

    def test_recalibrate_adjusts_weights(self) -> None:
        cat_obj = AdaptiveCategorizer(mode=CognitiveMode.ADAPTIVE)
        for _ in range(49):
            cat_obj.record_confirmation("Images", "content")
        # Confirm once more to trigger recalibrate
        cat_obj.record_confirmation("Images", "content")
        # content weight should have increased toward 1.0
        self.assertGreater(cat_obj._weights["content"], 0.5)


# ─── _get_category_ext ────────────────────────────────────────────────────────

class TestGetCategoryExt(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _f(self, name: str) -> Path:
        p = self.root / name
        p.write_bytes(b"x")
        return p

    def test_known_extensions(self) -> None:
        cases = {
            "photo.jpg": "Images",
            "movie.mp4": "Videos",
            "song.mp3":  "Audio",
            "doc.pdf":   "Documents",
            "data.xlsx": "Spreadsheets",
            "slides.pptx": "Presentations",
            "archive.zip": "Archives",
            "script.py":   "Code",
            "font.ttf":    "Fonts",
            "model.stl":   "3D_Models",
            "book.epub":   "Ebooks",
            "app.exe":     "Executables",
            "db.sqlite":   "Databases",
            "image.iso":   "Disk_Images",
        }
        for fname, expected in cases.items():
            with self.subTest(fname=fname):
                p = self._f(fname)
                self.assertEqual(_get_category_ext(p), expected)

    def test_no_extension(self) -> None:
        p = self._f("Makefile")
        self.assertEqual(_get_category_ext(p), "No_Extension")

    def test_unknown_extension(self) -> None:
        p = self._f("file.xyz")
        self.assertEqual(_get_category_ext(p), "XYZ_Files")

    def test_large_gb_override(self) -> None:
        p = self._f("big.mp4")
        # File is tiny so no override
        self.assertEqual(_get_category_ext(p, large_gb=1.0), "Videos")

    def test_case_insensitive_ext(self) -> None:
        p = self._f("PHOTO.JPG")
        self.assertEqual(_get_category_ext(p), "Images")


# ─── Utility functions ────────────────────────────────────────────────────────

class TestUtilities(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_quick_hash_deterministic(self) -> None:
        p = self.root / "file.txt"
        p.write_bytes(b"hello world")
        h1 = quick_hash(p)
        h2 = quick_hash(p)
        self.assertEqual(h1, h2)

    def test_quick_hash_differs_for_different_content(self) -> None:
        p1 = self.root / "a.txt"
        p2 = self.root / "b.txt"
        p1.write_bytes(b"content A")
        p2.write_bytes(b"content B")
        self.assertNotEqual(quick_hash(p1), quick_hash(p2))

    def test_quick_hash_same_content_same_hash(self) -> None:
        p1 = self.root / "a.txt"
        p2 = self.root / "b.txt"
        p1.write_bytes(b"identical")
        p2.write_bytes(b"identical")
        self.assertEqual(quick_hash(p1), quick_hash(p2))

    def test_quick_hash_missing_file(self) -> None:
        p = self.root / "nonexistent.txt"
        h = quick_hash(p)
        self.assertTrue(h.startswith("err_"))

    def test_unique_dest_no_conflict(self) -> None:
        dst = unique_dest(self.root, "file.txt")
        self.assertEqual(dst, self.root / "file.txt")

    def test_unique_dest_conflict(self) -> None:
        (self.root / "file.txt").write_bytes(b"x")
        dst = unique_dest(self.root, "file.txt")
        self.assertEqual(dst, self.root / "file (1).txt")

    def test_unique_dest_multiple_conflicts(self) -> None:
        (self.root / "file.txt").write_bytes(b"x")
        (self.root / "file (1).txt").write_bytes(b"x")
        dst = unique_dest(self.root, "file.txt")
        self.assertEqual(dst, self.root / "file (2).txt")

    def test_should_skip_directory(self) -> None:
        d = self.root / "subdir"
        d.mkdir()
        self.assertTrue(should_skip(d, True, "organizer.py"))

    def test_should_skip_script(self) -> None:
        p = self.root / "organizer.py"
        p.write_bytes(b"x")
        self.assertTrue(should_skip(p, True, "organizer.py"))

    def test_should_skip_junk_file(self) -> None:
        p = self.root / ".DS_Store"
        p.write_bytes(b"x")
        self.assertTrue(should_skip(p, True, "organizer.py"))

    def test_should_skip_hidden_excluded(self) -> None:
        p = self.root / ".hidden"
        p.write_bytes(b"x")
        self.assertTrue(should_skip(p, include_hidden=False, script_name="organizer.py"))

    def test_should_skip_hidden_included(self) -> None:
        p = self.root / ".hidden"
        p.write_bytes(b"x")
        self.assertFalse(should_skip(p, include_hidden=True, script_name="organizer.py"))

    def test_should_skip_organize_json(self) -> None:
        p = self.root / "organize_plan.json"
        p.write_bytes(b"{}")
        self.assertTrue(should_skip(p, True, "organizer.py"))

    def test_should_not_skip_normal_file(self) -> None:
        p = self.root / "document.pdf"
        p.write_bytes(b"x")
        self.assertFalse(should_skip(p, False, "organizer.py"))


# ─── build_plan ───────────────────────────────────────────────────────────────

class TestBuildPlan(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make(self, name: str, content: bytes = b"data") -> Path:
        p = self.root / name
        p.write_bytes(content)
        return p

    def _plan(self, **kwargs):
        defaults = dict(
            root=self.root,
            mode="flat",
            by_date="none",
            large_gb=0.0,
            include_hidden=False,
            dup_action="move_to_duplicates",
            exclude_exts=frozenset(),
            script_name="smart_organizer.py",
        )
        defaults.update(kwargs)
        return build_plan(**defaults)

    def test_basic_plan(self) -> None:
        self._make("photo.jpg", b"unique-image-content")
        self._make("song.mp3", b"unique-audio-content")
        self._make("doc.pdf", b"unique-document-content")
        plan, stats, dup_count, tags = self._plan()
        self.assertEqual(len(plan), 3)
        self.assertEqual(dup_count, 0)
        self.assertIn("Images", stats)
        self.assertIn("Audio", stats)
        self.assertIn("Documents", stats)

    def test_duplicate_detection(self) -> None:
        content = b"identical content"
        self._make("a.jpg", content)
        self._make("b.jpg", content)
        plan, stats, dup_count, tags = self._plan()
        self.assertEqual(dup_count, 1)
        # One goes to Images, one to Duplicates
        cats = {str(dst.parent.name) for _, dst in plan}
        self.assertIn("Duplicates", cats)

    def test_duplicate_skip_action(self) -> None:
        content = b"identical content"
        self._make("a.jpg", content)
        self._make("b.jpg", content)
        plan, stats, dup_count, tags = self._plan(dup_action="skip")
        self.assertEqual(dup_count, 1)
        # Only the first file should be in the plan
        self.assertEqual(len(plan), 1)

    def test_exclude_extension(self) -> None:
        self._make("photo.jpg")
        self._make("temp.tmp")
        plan, stats, dup_count, tags = self._plan(exclude_exts=frozenset({".tmp"}))
        cats = [dst.parent.name for _, dst in plan]
        self.assertNotIn("TMP_Files", cats)
        self.assertEqual(len(plan), 1)

    def test_skips_own_script(self) -> None:
        self._make("smart_organizer.py", b"#!/usr/bin/env python3")
        self._make("photo.jpg")
        plan, stats, dup_count, tags = self._plan(script_name="smart_organizer.py")
        self.assertEqual(len(plan), 1)

    def test_mirror_mode_preserves_structure(self) -> None:
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "photo.jpg").write_bytes(b"img")
        plan, stats, dup_count, tags = self._plan(mode="mirror")
        self.assertEqual(len(plan), 1)
        src, dst = plan[0]
        # Mirror mode: Images/sub/photo.jpg
        self.assertIn("sub", str(dst))

    def test_none_mode_top_level_only(self) -> None:
        (self.root / "top.jpg").write_bytes(b"x")
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "nested.jpg").write_bytes(b"x")
        plan, stats, dup_count, tags = self._plan(mode="none")
        # Only top-level file should be in plan
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][0].name, "top.jpg")

    def test_sub_categorize_invoices(self) -> None:
        p = self.root / "bill.txt"
        p.write_text(
            "Invoice\nAmount due: $500\nPayment terms: Net 30\n", encoding="utf-8"
        )
        categorizer = AdaptiveCategorizer(mode=CognitiveMode.CONTENT)
        plan, stats, dup_count, tags = self._plan(
            categorizer=categorizer, sub_categorize=True
        )
        self.assertEqual(len(plan), 1)
        _, dst = plan[0]
        # Should be under Documents/Invoices/
        self.assertIn("Invoices", str(dst))

    def test_tag_files_populates_tags_map(self) -> None:
        p = self.root / "test.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        categorizer = AdaptiveCategorizer(mode=CognitiveMode.ADAPTIVE)
        plan, stats, dup_count, tags_map = self._plan(
            categorizer=categorizer, tag_files=True
        )
        self.assertGreater(len(tags_map), 0)

    def test_empty_folder(self) -> None:
        plan, stats, dup_count, tags = self._plan()
        self.assertEqual(len(plan), 0)
        self.assertEqual(dup_count, 0)

    def test_extension_mode_no_categorizer(self) -> None:
        self._make("file.py")
        plan, stats, dup_count, tags = self._plan(categorizer=None)
        self.assertEqual(len(plan), 1)
        _, dst = plan[0]
        self.assertIn("Code", str(dst))


# ─── execute_plan ─────────────────────────────────────────────────────────────

class TestExecutePlan(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_dry_run_does_not_move(self) -> None:
        src = self.root / "file.txt"
        src.write_bytes(b"x")
        dst = self.root / "Documents" / "file.txt"
        plan = [(src, dst)]
        moved, failed = execute_plan(plan, self.root, dry_run=True)
        self.assertEqual(moved, 1)
        self.assertEqual(failed, 0)
        self.assertTrue(src.exists())
        self.assertFalse(dst.exists())

    def test_real_move(self) -> None:
        src = self.root / "file.txt"
        src.write_bytes(b"hello")
        dst = self.root / "Documents" / "file.txt"
        plan = [(src, dst)]
        moved, failed = execute_plan(plan, self.root, dry_run=False)
        self.assertEqual(moved, 1)
        self.assertEqual(failed, 0)
        self.assertFalse(src.exists())
        self.assertTrue(dst.exists())
        # Undo log should be created
        undo_dir = self.root / UNDO_DIR_NAME
        self.assertTrue(undo_dir.is_dir())

    def test_failed_move_counted(self) -> None:
        src = self.root / "missing.txt"  # does not exist
        dst = self.root / "Documents" / "missing.txt"
        plan = [(src, dst)]
        moved, failed = execute_plan(plan, self.root, dry_run=False)
        self.assertEqual(moved, 0)
        self.assertEqual(failed, 1)

    def test_tags_saved(self) -> None:
        src = self.root / "photo.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\ndata")
        dst = self.root / "Images" / "photo.png"
        plan = [(src, dst)]
        tags_map = {"photo.png": ["magic:images", "ocr:none"]}
        execute_plan(plan, self.root, dry_run=False, tags_map=tags_map)
        tags_file = self.root / TAGS_FILENAME
        self.assertTrue(tags_file.exists())
        with tags_file.open() as fh:
            loaded = json.load(fh)
        self.assertIn("photo.png", loaded)


# ─── Undo / plan persistence ──────────────────────────────────────────────────

class TestUndoAndPlan(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_save_and_load_plan(self) -> None:
        src = self.root / "file.txt"
        dst = self.root / "Documents" / "file.txt"
        plan = [(src, dst)]
        out = self.root / PLAN_FILENAME
        save_plan_file(plan, self.root, out)
        loaded = load_plan_file(out, self.root)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0][0], src)
        self.assertEqual(loaded[0][1], dst)

    def test_undo_round_trip(self) -> None:
        # Create a file, move it, then undo
        src = self.root / "original.txt"
        src.write_bytes(b"data")
        moved_to = self.root / "Documents" / "original.txt"
        moves = [(src, moved_to)]

        # Simulate a real move
        moved_to.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(src), str(moved_to))

        # Save undo log
        log = save_undo_log(moves, self.root)
        self.assertTrue(log.exists())

        # Perform undo
        restored = perform_undo(self.root, log)
        self.assertEqual(restored, 1)
        self.assertTrue(src.exists())
        self.assertFalse(moved_to.exists())

    def test_undo_no_logs(self) -> None:
        count = perform_undo(self.root)
        self.assertEqual(count, 0)

    def test_save_tags(self) -> None:
        tags_map = {"file.txt": ["kw:invoice", "magic:documents"]}
        out = save_tags(tags_map, self.root)
        self.assertTrue(out.exists())
        self.assertEqual(out.name, TAGS_FILENAME)
        with out.open() as fh:
            loaded = json.load(fh)
        self.assertEqual(loaded, tags_map)


# ─── CLI integration ──────────────────────────────────────────────────────────

class TestCLIIntegration(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run_cli(self, *extra_args):
        from smart_organizer import cli_main
        return cli_main([str(self.root)] + list(extra_args))

    def test_dry_run_no_moves(self) -> None:
        (self.root / "photo.jpg").write_bytes(b"img")
        rc = self._run_cli("--dry-run")
        self.assertEqual(rc, 0)
        # File still in root
        self.assertTrue((self.root / "photo.jpg").exists())

    def test_basic_organise(self) -> None:
        (self.root / "photo.jpg").write_bytes(b"img")
        (self.root / "song.mp3").write_bytes(b"audio")
        rc = self._run_cli()
        self.assertEqual(rc, 0)
        self.assertTrue((self.root / "Images" / "photo.jpg").exists())
        self.assertTrue((self.root / "Audio" / "song.mp3").exists())

    def test_extension_mode_default(self) -> None:
        (self.root / "data.zip").write_bytes(b"x")
        rc = self._run_cli("--cognitive", "extension")
        self.assertEqual(rc, 0)
        self.assertTrue((self.root / "Archives" / "data.zip").exists())

    def test_content_mode(self) -> None:
        p = self.root / "pdf_disguised.txt"
        p.write_bytes(b"%PDF-1.7\nsome content")
        rc = self._run_cli("--cognitive", "content")
        self.assertEqual(rc, 0)
        # Should be categorised as Documents (PDF magic bytes)
        self.assertTrue((self.root / "Documents" / "pdf_disguised.txt").exists())

    def test_adaptive_mode(self) -> None:
        (self.root / "photo.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        )
        rc = self._run_cli("--cognitive", "adaptive")
        self.assertEqual(rc, 0)
        self.assertTrue((self.root / "Images" / "photo.png").exists())

    def test_sub_categorize_invoice(self) -> None:
        p = self.root / "bill.txt"
        p.write_text(
            "Invoice\nAmount due: $500\nPayment terms: Net 30\n", encoding="utf-8"
        )
        rc = self._run_cli("--cognitive", "content", "--sub-categorize")
        self.assertEqual(rc, 0)
        # Should land in Documents/Invoices/
        expected = self.root / "Documents" / "Invoices" / "bill.txt"
        self.assertTrue(expected.exists())

    def test_tag_files_creates_json(self) -> None:
        (self.root / "photo.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        )
        rc = self._run_cli("--cognitive", "adaptive", "--tag-files")
        self.assertEqual(rc, 0)
        tags_file = self.root / TAGS_FILENAME
        self.assertTrue(tags_file.exists())

    def test_undo_after_organise(self) -> None:
        (self.root / "photo.jpg").write_bytes(b"img")
        self._run_cli()
        # Undo
        rc = self._run_cli("--undo")
        self.assertEqual(rc, 0)
        self.assertTrue((self.root / "photo.jpg").exists())

    def test_save_and_load_plan(self) -> None:
        (self.root / "song.mp3").write_bytes(b"audio")
        plan_file = self.root / "my_plan.json"
        self._run_cli("--save-plan", str(plan_file))
        self.assertTrue(plan_file.exists())
        rc = self._run_cli("--load-plan", str(plan_file))
        self.assertEqual(rc, 0)
        self.assertTrue((self.root / "Audio" / "song.mp3").exists())

    def test_invalid_directory(self) -> None:
        from smart_organizer import cli_main
        rc = cli_main(["/nonexistent/path/that/does/not/exist"])
        self.assertEqual(rc, 1)

    def test_empty_folder_exit_zero(self) -> None:
        rc = self._run_cli()
        self.assertEqual(rc, 0)


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_file_with_dot_in_stem(self) -> None:
        p = self.root / "archive.tar.gz"
        p.write_bytes(b"x")
        cat = _get_category_ext(p)
        # .gz is Archives
        self.assertEqual(cat, "Archives")

    def test_category_map_completeness(self) -> None:
        # Sanity-check that every extension in CATEGORY_MAP starts with a dot
        for ext in CATEGORY_MAP:
            self.assertTrue(ext.startswith("."), f"Extension missing dot: {ext!r}")

    def test_junk_files_skipped(self) -> None:
        for jf in JUNK_FILES:
            p = self.root / jf
            p.write_bytes(b"x")
        (self.root / "real.jpg").write_bytes(b"img")
        from smart_organizer import cli_main
        cli_main([str(self.root)])
        for jf in JUNK_FILES:
            if (self.root / jf).exists():
                self.assertTrue((self.root / jf).exists())
        self.assertTrue((self.root / "Images" / "real.jpg").exists())

    def test_no_extension_category(self) -> None:
        p = self.root / "README"
        p.write_bytes(b"readme content")
        cat = _get_category_ext(p)
        self.assertEqual(cat, "No_Extension")

    def test_collect_files_excludes_undo_dir(self) -> None:
        undo = self.root / UNDO_DIR_NAME
        undo.mkdir()
        (undo / "undo_log_20250101_120000.json").write_bytes(b"{}")
        (self.root / "real.jpg").write_bytes(b"img")
        files = collect_files(self.root, "flat", False, "smart_organizer.py")
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "real.jpg")

    def test_content_analyzer_zip_with_wrong_extension(self) -> None:
        # ZIP magic bytes but .doc extension
        p = self.root / "renamed.doc"
        p.write_bytes(b"PK\x03\x04\x00\x00" + b"\x00" * 20)
        analyzer = ContentAnalyzer()
        cat, conf, tags = analyzer.analyze(p)
        # Magic bytes win → Archives (even though extension says Documents)
        self.assertEqual(cat, "Archives")


if __name__ == "__main__":
    unittest.main(verbosity=2)
