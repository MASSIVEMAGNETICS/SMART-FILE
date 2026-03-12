#!/usr/bin/env python3
"""
SMART-FILE — AI-Enhanced File Organizer
========================================
Drop into any folder, run it, and watch it organize everything intelligently.

Blends the best of:
  • MASSIVEMAGNETICS/SMART-FILE  — single-file simplicity, core organisation
  • whoisdsmith/SmartFileOrganizer — AI content analysis, OCR, tagging
  • MASSIVEMAGNETICS/victor_llm  — adaptive cognitive modes, confidence scoring

New capabilities over organize_v4:
  • Cognitive modes: extension | content | adaptive
  • Content-based analysis via magic-byte signatures + MIME detection
  • Text keyword extraction for document sub-categorisation
    (Invoices, Contracts, Resumes, Reports, Research, Legal, Financial)
  • Optional OCR for scanned image documents (pytesseract + Pillow)
  • Multi-sector confidence scoring (victor_llm–inspired tensor fusion)
  • File tagging: writes organize_tags.json sidecar (--tag-files)
  • Enhanced Tkinter GUI with a dedicated AI / Cognitive options tab
  • All organize_v4 features preserved: dry-run, undo, plans, mirror, dates…

Usage:
    python smart_organizer.py                              # GUI
    python smart_organizer.py --cli                        # CLI (extension mode)
    python smart_organizer.py --cli --cognitive content    # content-analysis mode
    python smart_organizer.py --cli --cognitive adaptive   # adaptive AI mode
    python smart_organizer.py --cli --ocr                  # enable OCR for images
    python smart_organizer.py --cli --sub-categorize       # Documents sub-folders
    python smart_organizer.py --cli --tag-files            # save tags sidecar
    python smart_organizer.py --cli --dry-run -v           # preview
    python smart_organizer.py --cli --undo                 # restore last run
    python smart_organizer.py --help

Optional dependencies (zero hard deps — everything degrades gracefully):
    pip install tqdm              # progress bar
    pip install rich              # coloured output
    pip install pytesseract       # OCR (also needs Tesseract-OCR binary installed)
    pip install Pillow            # required for OCR image handling
    pip install python-magic      # enhanced MIME detection (needs libmagic)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# ─── Optional dependencies ────────────────────────────────────────────────────
try:
    from tqdm import tqdm  # type: ignore
    _TQDM = True
except ImportError:
    _TQDM = False

try:
    from rich.console import Console as _RichConsole  # type: ignore
    from rich.tree import Tree as _RichTree  # type: ignore
    _RICH = True
except ImportError:
    _RICH = False

try:
    import tkinter as tk  # type: ignore
    from tkinter import filedialog, messagebox, scrolledtext, ttk  # type: ignore
    _TK = True
except ImportError:
    _TK = False

try:
    import magic as _magic_lib  # type: ignore  # python-magic
    _MAGIC = True
except ImportError:
    _MAGIC = False

try:
    from PIL import Image as _PILImage  # type: ignore
    _PIL = True
except ImportError:
    _PIL = False

try:
    import pytesseract as _tesseract  # type: ignore
    _TESSERACT = True
except ImportError:
    _TESSERACT = False


# ─── Cognitive modes (victor_llm–inspired) ────────────────────────────────────

class CognitiveMode(str, Enum):
    """
    Categorisation strategy, inspired by victor_llm's cognitive architecture.

    EXTENSION : Fast, traditional extension-based lookup (default, zero overhead).
    CONTENT   : Deep content analysis via magic bytes + MIME detection.
    ADAPTIVE  : Multi-sector confidence fusion with dynamic weight adjustment.
    """
    EXTENSION = "extension"
    CONTENT   = "content"
    ADAPTIVE  = "adaptive"


# ─── Category map (identical to organize_v4 for backward compatibility) ───────

CATEGORY_MAP: Dict[str, str] = {
    # Images
    ".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images",
    ".bmp": "Images", ".tiff": "Images", ".tif": "Images", ".webp": "Images",
    ".svg": "Images", ".heic": "Images", ".raw": "Images", ".ico": "Images",
    ".psd": "Design", ".ai": "Design", ".xd": "Design", ".sketch": "Design",
    # Videos
    ".mp4": "Videos", ".mkv": "Videos", ".avi": "Videos", ".mov": "Videos",
    ".wmv": "Videos", ".flv": "Videos", ".webm": "Videos", ".m4v": "Videos",
    ".mpg": "Videos", ".mpeg": "Videos", ".3gp": "Videos",
    # Audio
    ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio", ".m4a": "Audio",
    ".aac": "Audio", ".ogg": "Audio", ".wma": "Audio", ".opus": "Audio",
    # Documents
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".txt": "Documents", ".md": "Documents", ".markdown": "Documents",
    ".rtf": "Documents", ".odt": "Documents", ".pages": "Documents",
    # Spreadsheets
    ".xls": "Spreadsheets", ".xlsx": "Spreadsheets", ".csv": "Spreadsheets",
    ".ods": "Spreadsheets", ".numbers": "Spreadsheets",
    # Presentations
    ".ppt": "Presentations", ".pptx": "Presentations", ".odp": "Presentations",
    ".key": "Presentations",
    # Archives
    ".zip": "Archives", ".rar": "Archives", ".7z": "Archives",
    ".tar": "Archives", ".gz": "Archives", ".bz2": "Archives",
    ".xz": "Archives", ".zst": "Archives",
    # Code & Development
    ".py": "Code", ".js": "Code", ".ts": "Code", ".jsx": "Code", ".tsx": "Code",
    ".html": "Code", ".htm": "Code", ".css": "Code", ".scss": "Code",
    ".json": "Code", ".yaml": "Code", ".yml": "Code", ".toml": "Code",
    ".xml": "Code", ".sh": "Code", ".bash": "Code", ".zsh": "Code",
    ".ps1": "Code", ".rb": "Code", ".go": "Code", ".rs": "Code",
    ".c": "Code", ".cpp": "Code", ".h": "Code", ".java": "Code",
    ".kt": "Code", ".swift": "Code", ".php": "Code", ".lua": "Code",
    # Fonts
    ".ttf": "Fonts", ".otf": "Fonts", ".woff": "Fonts", ".woff2": "Fonts",
    # 3D / CAD
    ".obj": "3D_Models", ".fbx": "3D_Models", ".stl": "3D_Models",
    ".blend": "3D_Models", ".dae": "3D_Models",
    # Ebooks
    ".epub": "Ebooks", ".mobi": "Ebooks", ".azw3": "Ebooks",
    # Executables
    ".exe": "Executables", ".msi": "Executables", ".dmg": "Executables",
    ".apk": "Executables", ".deb": "Executables", ".rpm": "Executables",
    ".appimage": "Executables",
    # Databases
    ".db": "Databases", ".sqlite": "Databases", ".sqlite3": "Databases",
    # Disk images
    ".iso": "Disk_Images", ".img": "Disk_Images", ".vmdk": "Disk_Images",
}

JUNK_FILES = frozenset({
    "Thumbs.db", "Desktop.ini", ".DS_Store", "ehthumbs_vista.db",
    ".Spotlight-V100", ".Trashes", "._.DS_Store", "desktop.ini",
})

UNDO_DIR_NAME = "ORGANIZE_UNDO_LOGS"
PLAN_FILENAME = "organize_plan.json"
TAGS_FILENAME = "organize_tags.json"


# ─── Content-analysis constants ───────────────────────────────────────────────

# (byte-prefix, top-level category, confidence) — checked in order
_MAGIC_SIGNATURES: List[Tuple[bytes, str, float]] = [
    (b"\x89PNG\r\n\x1a\n",     "Images",      0.98),
    (b"\xff\xd8\xff",           "Images",      0.97),   # JPEG
    (b"GIF87a",                 "Images",      0.98),
    (b"GIF89a",                 "Images",      0.98),
    (b"BM",                     "Images",      0.85),   # BMP (short sig)
    (b"fLaC",                   "Audio",       0.99),   # FLAC
    (b"OggS",                   "Audio",       0.97),   # OGG
    (b"ID3",                    "Audio",       0.95),   # MP3
    (b"RIFF",                   "Audio",       0.75),   # WAV/AVI (ambiguous)
    (b"%PDF-",                  "Documents",   0.99),
    (b"PK\x03\x04",            "Archives",    0.90),   # ZIP / DOCX / XLSX …
    (b"Rar!\x1a\x07",          "Archives",    0.99),
    (b"7z\xbc\xaf'\x1c",       "Archives",    0.99),
    (b"\x1f\x8b",               "Archives",    0.97),   # gzip
    (b"BZh",                    "Archives",    0.97),   # bzip2
    (b"\xfd7zXZ\x00",          "Archives",    0.99),   # xz
    (b"\x7fELF",                "Executables", 0.99),   # ELF binary
    (b"MZ",                     "Executables", 0.85),   # PE / EXE (short sig)
    (b"\xca\xfe\xba\xbe",      "Executables", 0.99),   # Mach-O fat
    (b"\xce\xfa\xed\xfe",      "Executables", 0.99),   # Mach-O 32-bit
    (b"\xcf\xfa\xed\xfe",      "Executables", 0.99),   # Mach-O 64-bit
    (b"SQLite format 3\x00",    "Databases",   0.99),
]

# Text keyword patterns → document sub-category label
_TEXT_SUBCATEGORIES: Dict[str, List[str]] = {
    "Documents/Invoices":  [
        "invoice", "amount due", "billing", "payment terms", "purchase order",
    ],
    "Documents/Receipts":  [
        "receipt", "transaction id", "order confirmation", "total paid",
    ],
    "Documents/Contracts": [
        "agreement", "contract", "parties", "terms and conditions", "hereby",
    ],
    "Documents/Resumes":   [
        "resume", "curriculum vitae", "work experience", "references available",
    ],
    "Documents/Reports":   [
        "executive summary", "findings", "recommendations", "conclusion",
    ],
    "Documents/Research":  [
        "abstract", "methodology", "hypothesis", "literature review", "doi",
    ],
    "Documents/Legal":     [
        "plaintiff", "defendant", "whereas", "pursuant to", "jurisdiction",
    ],
    "Documents/Financial": [
        "balance sheet", "cash flow", "revenue", "profit and loss", "fiscal",
    ],
}

_PEEK_SIZE  = 512    # bytes to read for magic-byte detection
_TEXT_LIMIT = 8_192  # characters to read for keyword extraction

# Extensions where text keyword scanning is attempted
_TEXT_READABLE_EXTS = frozenset({
    ".txt", ".md", ".markdown", ".rtf", ".csv", ".html", ".htm",
    ".xml", ".json", ".yaml", ".yml", ".toml", ".rst", ".log",
    ".tex", ".org", ".nfo", ".cfg", ".ini", ".conf",
})

# Image extensions eligible for OCR
_IMAGE_EXTS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic",
})


# ─── ContentAnalyzer ──────────────────────────────────────────────────────────

class ContentAnalyzer:
    """
    AI-enhanced file content analyser.

    Combines four analysis "sectors" to determine a file's category and derive
    descriptive tags — independently of its file extension.  Architecture
    inspired by victor_llm's multi-sector cognitive processing: each sector
    contributes a weighted signal that is fused into a final decision.

    Sectors
    -------
    1. Magic bytes — matches the first bytes of the file against known headers.
    2. MIME type   — uses python-magic (libmagic) when available.
    3. Text keywords — scans readable text for document-type indicators.
    4. OCR         — extracts text from images via pytesseract (optional).
    """

    def __init__(self, enable_ocr: bool = False) -> None:
        self.enable_ocr = enable_ocr and _PIL and _TESSERACT

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(self, path: Path) -> Tuple[str, float, List[str]]:
        """
        Analyse *path* and return ``(category, confidence, tags)``.

        The returned category may be a hierarchical string such as
        ``"Documents/Invoices"``; callers decide whether to use the full path
        or just the top-level segment.  *confidence* is in ``[0, 1]``.
        """
        tags: List[str] = []
        scores: Dict[str, float] = defaultdict(float)

        # Sector 1 — magic bytes (weight 0.45)
        magic_cat, magic_conf = self._magic_bytes(path)
        if magic_cat:
            scores[magic_cat] += magic_conf * 0.45
            tags.append(f"magic:{magic_cat.lower()}")

        # Sector 2 — python-magic MIME (weight 0.35, only when available)
        if _MAGIC:
            mime_cat, mime_conf = self._mime_magic(path)
            if mime_cat:
                scores[mime_cat] += mime_conf * 0.35
                tags.append(f"mime:{mime_cat.lower()}")

        # Sector 3 — text keyword extraction (weight 0.20)
        text_cat, text_conf, text_tags = self._text_keywords(path)
        if text_cat:
            scores[text_cat] += text_conf * 0.20
            tags.extend(text_tags)

        # Sector 4 — OCR (images only, weight 0.15, optional)
        if self.enable_ocr and path.suffix.lower() in _IMAGE_EXTS:
            ocr_cat, ocr_tags = self._ocr_sector(path)
            if ocr_cat:
                scores[ocr_cat] += 0.15
                tags.extend(ocr_tags)
                tags.append("ocr:processed")

        if scores:
            best = max(scores, key=scores.__getitem__)
            return best, min(scores[best], 1.0), list(dict.fromkeys(tags))

        return "", 0.0, tags

    def extract_ocr_text(self, path: Path) -> Optional[str]:
        """Return OCR text from *path*, or ``None`` when unavailable."""
        if not _PIL or not _TESSERACT:
            return None
        try:
            img = _PILImage.open(path)
            return _tesseract.image_to_string(img)  # type: ignore[union-attr]
        except Exception as exc:
            logging.debug("OCR failed for %s: %s", path.name, exc)
            return None

    # ── Private sectors ───────────────────────────────────────────────────────

    def _magic_bytes(self, path: Path) -> Tuple[Optional[str], float]:
        """Sector 1: match leading bytes against known signatures."""
        try:
            with path.open("rb") as fh:
                header = fh.read(_PEEK_SIZE)
        except OSError:
            return None, 0.0

        for sig, cat, conf in _MAGIC_SIGNATURES:
            if header.startswith(sig):
                return cat, conf
        return None, 0.0

    def _mime_magic(self, path: Path) -> Tuple[Optional[str], float]:
        """Sector 2: python-magic MIME type detection."""
        try:
            mime: str = _magic_lib.from_file(str(path), mime=True)  # type: ignore[attr-defined]
        except Exception:
            return None, 0.0

        top = mime.split("/")[0]
        simple: Dict[str, Tuple[str, float]] = {
            "image": ("Images",    0.95),
            "video": ("Videos",    0.95),
            "audio": ("Audio",     0.95),
            "text":  ("Documents", 0.60),
        }
        if top in simple:
            return simple[top]

        specific: Dict[str, Tuple[str, float]] = {
            "application/pdf":              ("Documents",     0.99),
            "application/zip":              ("Archives",      0.95),
            "application/x-rar-compressed": ("Archives",      0.99),
            "application/x-7z-compressed":  ("Archives",      0.99),
            "application/gzip":             ("Archives",      0.97),
            "application/x-sqlite3":        ("Databases",     0.99),
            "application/x-executable":     ("Executables",   0.95),
            "application/x-sharedlib":      ("Executables",   0.90),
            "application/msword":           ("Documents",     0.95),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                                            ("Documents",     0.99),
            "application/vnd.ms-excel":     ("Spreadsheets",  0.95),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                                            ("Spreadsheets",  0.99),
            "application/vnd.ms-powerpoint":("Presentations", 0.95),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation":
                                            ("Presentations", 0.99),
            "application/epub+zip":         ("Ebooks",        0.99),
            "application/x-mobipocket-ebook":("Ebooks",       0.99),
            "application/json":             ("Code",          0.90),
            "application/xml":              ("Code",          0.85),
            "application/javascript":       ("Code",          0.95),
            "application/x-python-code":    ("Code",          0.95),
        }
        return specific.get(mime, (None, 0.0))  # type: ignore[return-value]

    def _text_keywords(
        self, path: Path
    ) -> Tuple[Optional[str], float, List[str]]:
        """Sector 3: scan text content for document-type indicator keywords."""
        if path.suffix.lower() not in _TEXT_READABLE_EXTS and path.suffix.lower() != ".pdf":
            return None, 0.0, []

        text = self._read_text_safe(path)
        if not text:
            return None, 0.0, []

        lower = text.lower()
        tags: List[str] = []
        best_cat: Optional[str] = None
        best_score = 0.0

        for subcat, keywords in _TEXT_SUBCATEGORIES.items():
            hits = sum(1 for kw in keywords if kw in lower)
            if hits > 0:
                score = hits / len(keywords)
                matched = [kw for kw in keywords if kw in lower]
                tags.extend(
                    f"kw:{kw.replace(' ', '_')}" for kw in matched[:3]
                )
                if score > best_score:
                    best_score = score
                    best_cat = subcat

        if best_cat and best_score >= 0.2:
            return best_cat, best_score, tags

        return None, 0.0, tags

    def _ocr_sector(self, path: Path) -> Tuple[Optional[str], List[str]]:
        """Sector 4: OCR — extract text from image, then keyword-scan it."""
        text = self.extract_ocr_text(path)
        if not text or not text.strip():
            return None, []

        lower = text.lower()
        tags = ["ocr:has_text"]
        for subcat, keywords in _TEXT_SUBCATEGORIES.items():
            if any(kw in lower for kw in keywords):
                label = subcat.split("/")[-1].lower()
                tags.append(f"ocr_type:{label}")
                return subcat, tags

        return "Documents", tags

    @staticmethod
    def _read_text_safe(path: Path, limit: int = _TEXT_LIMIT) -> Optional[str]:
        """Try common encodings; return first *limit* characters."""
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                with path.open("r", encoding=enc, errors="replace") as fh:
                    return fh.read(limit)
            except OSError:
                return None
        return None


# ─── AdaptiveCategorizer (victor_llm–inspired) ───────────────────────────────

class AdaptiveCategorizer:
    """
    Multi-sector, confidence-weighted categoriser inspired by victor_llm's
    tensor-style cognitive architecture.

    Three cognitive modes control how the two primary sectors are weighted:

    EXTENSION  — Only extension look-up (fast, deterministic, zero AI overhead).
    CONTENT    — Primarily magic-byte / MIME analysis; extension as fallback.
    ADAPTIVE   — Fuses extension + content signals with confidence weighting
                 and dynamically recalibrates sector weights based on agreement
                 history, maximising long-run accuracy.
    """

    # Base sector weights per cognitive mode
    _MODE_WEIGHTS: Dict[str, Dict[str, float]] = {
        CognitiveMode.EXTENSION: {"extension": 1.0,  "content": 0.0},
        CognitiveMode.CONTENT:   {"extension": 0.2,  "content": 0.8},
        CognitiveMode.ADAPTIVE:  {"extension": 0.5,  "content": 0.5},
    }

    def __init__(
        self,
        mode: CognitiveMode = CognitiveMode.EXTENSION,
        enable_ocr: bool = False,
    ) -> None:
        self.mode = mode
        self._analyzer = ContentAnalyzer(enable_ocr=enable_ocr)
        # Mutable sector weights (adjusted at runtime in ADAPTIVE mode)
        self._weights: Dict[str, float] = dict(self._MODE_WEIGHTS[mode])
        # Confirmation counters for adaptive recalibration
        self._confirm_ext:     Counter = Counter()
        self._confirm_content: Counter = Counter()

    # ── Public API ────────────────────────────────────────────────────────────

    def categorize(
        self,
        path: Path,
        by_date: Optional[str] = None,
        large_gb: float = 0.0,
    ) -> Tuple[str, float, List[str]]:
        """
        Return ``(category, confidence, tags)`` for *path*.
        *confidence* is in ``[0, 1]``; higher means more certain.
        """
        ext_cat = _get_category_ext(path, by_date, large_gb)

        if self.mode == CognitiveMode.EXTENSION:
            return ext_cat, 0.75, []

        content_cat, content_conf, tags = self._analyzer.analyze(path)

        if self.mode == CognitiveMode.CONTENT:
            # Any non-empty content signal is used: CONTENT mode exists to
            # override extension-based guessing whenever content analysis
            # returns a result (regardless of the combined weighted score).
            if content_cat:
                return content_cat.split("/")[0], content_conf, tags
            return ext_cat, 0.40, tags

        # ── ADAPTIVE: weighted fusion ─────────────────────────────────────────
        scores: Dict[str, float] = defaultdict(float)
        scores[ext_cat] += self._weights["extension"] * 0.75

        if content_cat:
            top = content_cat.split("/")[0]
            scores[top] += self._weights["content"] * content_conf

        best_cat  = max(scores, key=scores.__getitem__)
        best_conf = min(scores[best_cat], 1.0)

        # Shift weight toward content when it confidently disagrees with extension
        if (
            content_cat
            and ext_cat != content_cat.split("/")[0]
            and content_conf > 0.8
        ):
            self._shift_weight("content", +0.02)

        return best_cat, best_conf, tags

    def get_sub_category(self, path: Path, top_category: str) -> Optional[str]:
        """
        Return a refined sub-category label (e.g. ``"Invoices"``) if text
        keyword analysis yields a confident match for *top_category*.
        """
        _, _, _ = self._analyzer.analyze(path)
        text_cat, text_conf, _ = self._analyzer._text_keywords(path)
        if (
            text_cat
            and text_conf >= 0.2
            and text_cat.startswith(top_category + "/")
        ):
            return text_cat.split("/", 1)[1]
        return None

    def record_confirmation(self, category: str, from_sector: str) -> None:
        """Update adaptive weights based on a confirmed categorisation."""
        if from_sector == "extension":
            self._confirm_ext[category] += 1
        else:
            self._confirm_content[category] += 1
        total = (
            sum(self._confirm_ext.values())
            + sum(self._confirm_content.values())
        )
        if total > 0 and total % 50 == 0:
            self._recalibrate()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _shift_weight(self, sector: str, delta: float) -> None:
        other = "extension" if sector == "content" else "content"
        self._weights[sector] = max(0.10, min(0.90, self._weights[sector] + delta))
        self._weights[other]  = max(0.10, min(0.90, self._weights[other]  - delta))

    def _recalibrate(self) -> None:
        ext_total  = sum(self._confirm_ext.values())
        cont_total = sum(self._confirm_content.values())
        total      = ext_total + cont_total
        if total == 0:
            return
        self._weights["extension"] = max(0.10, ext_total  / total)
        self._weights["content"]   = max(0.10, cont_total / total)


# ─── Core helpers (backward-compatible with organize_v4) ─────────────────────

def _get_category_ext(
    path: Path,
    by_date: Optional[str] = None,
    large_gb: float = 0.0,
) -> str:
    """Extension-only category (identical logic to organize_v4.get_category)."""
    if by_date and by_date != "none":
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if by_date == "year":
                return f"By_Year/{mtime.year}"
            if by_date == "year-month":
                return f"By_Year-Month/{mtime.strftime('%Y-%m')}"
        except OSError:
            pass

    if large_gb > 0:
        try:
            if path.stat().st_size >= large_gb * 1_000_000_000:
                ext = path.suffix.lower()
                base = CATEGORY_MAP.get(ext, "Files")
                return f"Large_{base}"
        except OSError:
            pass

    ext = path.suffix.lower()
    if not ext:
        return "No_Extension"
    return CATEGORY_MAP.get(ext, f"{ext.lstrip('.').upper()}_Files")


def get_category(
    path: Path,
    by_date: Optional[str] = None,
    large_gb: float = 0.0,
    categorizer: Optional[AdaptiveCategorizer] = None,
) -> str:
    """Return destination category for *path*, using *categorizer* when set."""
    if categorizer and categorizer.mode != CognitiveMode.EXTENSION:
        cat, _conf, _tags = categorizer.categorize(path, by_date, large_gb)
        return cat
    return _get_category_ext(path, by_date, large_gb)


def quick_hash(path: Path, chunk: int = 8192) -> str:
    """Fast fingerprint: (file-size + first 8 KiB) → BLAKE2b digest."""
    try:
        st = path.stat()
        with path.open("rb") as fh:
            head = fh.read(chunk)
        raw = f"{st.st_size}:".encode() + head
        return hashlib.blake2b(raw, digest_size=20).hexdigest()
    except OSError:
        return f"err_{id(path)}"


def unique_dest(target_dir: Path, name: str) -> Path:
    """Return a non-conflicting path under *target_dir*."""
    candidate = target_dir / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 1
    while True:
        candidate = target_dir / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def should_skip(path: Path, include_hidden: bool, script_name: str) -> bool:
    """Return True if *path* should never be touched by the organizer."""
    if path.is_dir():
        return True
    if path.name == script_name:
        return True
    if path.name in JUNK_FILES:
        return True
    if not include_hidden and path.name.startswith("."):
        return True
    # Skip our own metadata files
    if path.suffix == ".json" and path.stem.startswith("organize_"):
        return True
    return False


def collect_files(
    root: Path,
    mode: str,
    include_hidden: bool,
    script_name: str,
) -> List[Path]:
    """Return all candidate files under *root* respecting *mode*."""
    iterator: Iterator[Path] = (
        root.iterdir() if mode == "none" else root.rglob("*")
    )
    result = []
    for p in iterator:
        if not p.is_file() or should_skip(p, include_hidden, script_name):
            continue
        try:
            p.relative_to(root / UNDO_DIR_NAME)
            continue  # inside undo-log dir
        except ValueError:
            pass
        result.append(p)
    return result


def atomic_move(src: Path, dst: Path) -> None:
    """Move src → dst via a temp file on the same device."""
    tmp = dst.with_name(f".{dst.name}.org_tmp")
    try:
        shutil.move(str(src), str(tmp))
        tmp.rename(dst)
    except Exception:
        if tmp.exists():
            try:
                tmp.rename(dst)
            except Exception:
                shutil.move(str(tmp), str(dst))
        raise


# ─── Plan builder ─────────────────────────────────────────────────────────────

def build_plan(
    root: Path,
    mode: str,
    by_date: str,
    large_gb: float,
    include_hidden: bool,
    dup_action: str,
    exclude_exts: frozenset,
    script_name: str,
    categorizer: Optional[AdaptiveCategorizer] = None,
    sub_categorize: bool = False,
    tag_files: bool = False,
) -> Tuple[List[Tuple[Path, Path]], Counter, int, Dict[str, List[str]]]:
    """
    Return ``(plan, stats, dup_count, tags_map)``.

    *plan*      — list of ``(src, dst)`` absolute Path pairs.
    *stats*     — Counter mapping category → file count.
    *dup_count* — number of duplicate files detected.
    *tags_map*  — ``{relative_path: [tag, …]}`` (populated when tag_files=True).
    """
    files = collect_files(root, mode, include_hidden, script_name)
    plan: List[Tuple[Path, Path]] = []
    stats: Counter = Counter()
    dup_count = 0
    seen_hashes: Dict[str, Path] = {}
    tags_map: Dict[str, List[str]] = {}

    for src in files:
        if src.suffix.lower() in exclude_exts or src.name.lower() in exclude_exts:
            continue

        # Duplicate detection
        h = quick_hash(src)
        if h in seen_hashes:
            dup_count += 1
            if dup_action == "move_to_duplicates":
                dst = unique_dest(root / "Duplicates", src.name)
                plan.append((src, dst))
                stats["Duplicates"] += 1
            continue
        seen_hashes[h] = src

        # Categorise
        cat = get_category(
            src,
            by_date if by_date != "none" else None,
            large_gb,
            categorizer,
        )

        # Optional document sub-categorisation (e.g. Documents/Invoices)
        if sub_categorize and categorizer and cat == "Documents":
            sub = categorizer.get_sub_category(src, cat)
            if sub:
                cat = f"{cat}/{sub}"

        target_dir = (
            root / cat / src.relative_to(root).parent
            if mode == "mirror"
            else root / cat
        )

        dst = unique_dest(target_dir, src.name)
        plan.append((src, dst))
        stats[cat] += 1

        # Collect AI tags
        if tag_files and categorizer:
            _, _, tags = categorizer.categorize(src)
            if tags:
                key = str(src.relative_to(root)) if src.is_relative_to(root) else src.name
                tags_map[key] = tags

    return plan, stats, dup_count, tags_map


# ─── Undo / plan persistence ──────────────────────────────────────────────────

def save_undo_log(moves: List[Tuple[Path, Path]], root: Path) -> Path:
    """Persist an undo log and return the path to the JSON file."""
    undo_dir = root / UNDO_DIR_NAME
    undo_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = undo_dir / f"undo_log_{ts}.json"
    data = [
        {"from": str(src.relative_to(root)), "to": str(dst.relative_to(root))}
        for src, dst in moves
    ]
    with log_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return log_path


def perform_undo(root: Path, undo_file: Optional[Path] = None) -> int:
    """Reverse moves recorded in the most recent (or specified) undo log."""
    if not undo_file:
        undo_dir = root / UNDO_DIR_NAME
        candidates = sorted(undo_dir.glob("undo_log_*.json"), reverse=True)
        if not candidates:
            logging.error("No undo logs found in %s", undo_dir)
            return 0
        undo_file = candidates[0]
        logging.info("Using most recent undo log: %s", undo_file.name)

    with undo_file.open(encoding="utf-8") as fh:
        moves = json.load(fh)

    restored = 0
    for item in moves:
        current  = root / item["to"]
        original = root / item["from"]
        if current.exists() and not original.exists():
            try:
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current), str(original))
                restored += 1
                logging.info("Restored: %s", item["from"])
            except Exception as exc:
                logging.warning("Failed to restore %s: %s", item["from"], exc)
        else:
            logging.debug("Skip restore %s", item["from"])

    logging.info("Undo complete — %d file(s) restored.", restored)
    return restored


def save_plan_file(plan: List[Tuple[Path, Path]], root: Path, out: Path) -> None:
    data = [
        {"from": str(s.relative_to(root)), "to": str(d.relative_to(root))}
        for s, d in plan
    ]
    with out.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_plan_file(plan_file: Path, root: Path) -> List[Tuple[Path, Path]]:
    with plan_file.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return [(root / item["from"], root / item["to"]) for item in data]


def save_tags(tags_map: Dict[str, List[str]], root: Path) -> Path:
    """Write AI-derived tags to *organize_tags.json* in *root*."""
    out = root / TAGS_FILENAME
    with out.open("w", encoding="utf-8") as fh:
        json.dump(tags_map, fh, indent=2, sort_keys=True)
    return out


def execute_plan(
    plan: List[Tuple[Path, Path]],
    root: Path,
    dry_run: bool = False,
    tags_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[int, int]:
    """Execute *plan*, return ``(moved_count, failed_count)``."""
    moved = 0
    failed = 0
    moves_made: List[Tuple[Path, Path]] = []

    iterator = (
        tqdm(plan, desc="Organizing", unit="file")  # type: ignore[name-defined]
        if _TQDM and not dry_run
        else plan
    )

    for src, dst in iterator:
        if dry_run:
            logging.info(
                "[DRY-RUN]  %s  →  %s",
                src.relative_to(root),
                dst.relative_to(root),
            )
            moved += 1
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            atomic_move(src, dst)
            logging.info(
                "Moved  %s  →  %s",
                src.relative_to(root),
                dst.relative_to(root),
            )
            moves_made.append((src, dst))
            moved += 1
        except Exception as exc:
            logging.error("Failed %s: %s", src.name, exc)
            failed += 1

    if moves_made and not dry_run:
        log_path = save_undo_log(moves_made, root)
        logging.info("Undo log → %s", log_path)

    if tags_map and not dry_run:
        tp = save_tags(tags_map, root)
        logging.info("Tags saved → %s", tp)

    return moved, failed


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _print_summary(
    stats: Counter,
    moved: int,
    failed: int,
    skipped: int,
    mode: CognitiveMode = CognitiveMode.EXTENSION,
) -> None:
    sep = "═" * 52
    print(f"\n{sep}")
    print(f"  Cognitive mode : {mode.value}")
    print(f"  Moved          : {moved:,}")
    print(f"  Failed         : {failed:,}")
    print(f"  Skipped        : {skipped:,}")
    if stats:
        print("\n  By category:")
        for cat, cnt in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"    {cat:<32} {cnt:4,} file(s)")
    print(sep)


def cli_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="smart_organizer.py",
        description="SMART-FILE AI-Enhanced File Organizer — CLI mode",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python smart_organizer.py --cli\n"
            "  python smart_organizer.py --cli path/to/folder --dry-run -v\n"
            "  python smart_organizer.py --cli --cognitive adaptive\n"
            "  python smart_organizer.py --cli --cognitive content --ocr\n"
            "  python smart_organizer.py --cli -m mirror --by-date year-month\n"
            "  python smart_organizer.py --cli --sub-categorize --tag-files\n"
            "  python smart_organizer.py --cli --undo\n"
        ),
    )
    parser.add_argument(
        "path", nargs="?", default=".", help="Folder to organize (default: .)"
    )
    parser.add_argument("--cli", action="store_true", help="Force CLI mode (skip GUI)")
    parser.add_argument(
        "-m", "--mode",
        choices=["flat", "mirror", "none"],
        default="flat",
        help="flat | mirror | none  (default: flat)",
    )
    parser.add_argument(
        "--by-date",
        choices=["none", "year", "year-month"],
        default="none",
        help="Group files by modification date",
    )
    parser.add_argument(
        "--large-gb", type=float, default=0.0,
        help="Files >= X GB → Large_<Category> folder",
    )
    parser.add_argument(
        "--dry-run", "-d", action="store_true",
        help="Preview only — nothing is moved",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--hidden", "-H", action="store_true",
        help="Include hidden (dot) files",
    )
    parser.add_argument(
        "--undo", action="store_true",
        help="Restore files from the most recent undo log",
    )
    parser.add_argument(
        "--undo-file", type=str, default="",
        help="Path to a specific undo JSON log to restore from",
    )
    parser.add_argument(
        "--dup-action",
        choices=["move_to_duplicates", "skip"],
        default="move_to_duplicates",
        help="What to do with duplicate files",
    )
    parser.add_argument(
        "--exclude", type=str, default="",
        help="Comma-separated extensions or filenames to skip (.tmp,.log)",
    )
    parser.add_argument(
        "--save-plan", type=str, default="",
        help="Save plan to JSON file (implies --dry-run preview)",
    )
    parser.add_argument(
        "--load-plan", type=str, default="",
        help="Load and execute a previously saved plan JSON file",
    )
    # ── AI / Cognitive flags ──────────────────────────────────────────────────
    parser.add_argument(
        "--cognitive",
        choices=[m.value for m in CognitiveMode],
        default=CognitiveMode.EXTENSION.value,
        metavar="MODE",
        help=(
            "Categorisation strategy:\n"
            "  extension  — extension-based only (default, zero overhead)\n"
            "  content    — magic-byte + MIME analysis\n"
            "  adaptive   — multi-sector confidence fusion (recommended)\n"
        ),
    )
    parser.add_argument(
        "--ocr", action="store_true",
        help="Enable OCR for image files (requires pytesseract + Pillow)",
    )
    parser.add_argument(
        "--sub-categorize", action="store_true",
        help="Organize documents into sub-folders (Invoices, Contracts, …)",
    )
    parser.add_argument(
        "--tag-files", action="store_true",
        help="Write organize_tags.json with AI-derived tags for each file",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    root = Path(args.path).resolve()
    if not root.is_dir():
        logging.error("'%s' is not a directory.", root)
        return 1

    script_name  = Path(__file__).name
    exclude_exts = frozenset(
        x.strip().lower() for x in args.exclude.split(",") if x.strip()
    )
    cognitive_mode = CognitiveMode(args.cognitive)

    # ── Undo mode ──────────────────────────────────────────────────────────────
    if args.undo:
        undo_file = Path(args.undo_file) if args.undo_file else None
        perform_undo(root, undo_file)
        return 0

    # ── Load-and-execute plan mode ─────────────────────────────────────────────
    if args.load_plan:
        plan_path = Path(args.load_plan)
        if not plan_path.is_file():
            logging.error("Plan file not found: %s", plan_path)
            return 1
        plan = load_plan_file(plan_path, root)
        logging.info("Loaded plan with %d move(s).", len(plan))
        moved, failed = execute_plan(plan, root, dry_run=False)
        _print_summary(Counter(), moved, failed, 0, cognitive_mode)
        return 0

    # ── AI / cognitive mode setup ──────────────────────────────────────────────
    if cognitive_mode != CognitiveMode.EXTENSION:
        logging.info("Cognitive mode: %s", cognitive_mode.value)
        if args.ocr and not (_PIL and _TESSERACT):
            logging.warning(
                "OCR requested but pytesseract/Pillow not installed. "
                "Install with: pip install pytesseract Pillow"
            )
        categorizer: Optional[AdaptiveCategorizer] = AdaptiveCategorizer(
            mode=cognitive_mode, enable_ocr=args.ocr
        )
    else:
        categorizer = None

    # ── Normal / dry-run mode ──────────────────────────────────────────────────
    logging.info("Scanning: %s", root)
    plan, stats, dup_count, tags_map = build_plan(
        root=root,
        mode=args.mode,
        by_date=args.by_date,
        large_gb=args.large_gb,
        include_hidden=args.hidden,
        dup_action=args.dup_action,
        exclude_exts=exclude_exts,
        script_name=script_name,
        categorizer=categorizer,
        sub_categorize=args.sub_categorize,
        tag_files=args.tag_files,
    )

    if not plan:
        logging.info("No files to organize.")
        return 0

    logging.info("Found %d file(s) to move (%d duplicate(s)).", len(plan), dup_count)

    if args.save_plan:
        plan_out = Path(args.save_plan)
        save_plan_file(plan, root, plan_out)
        logging.info("Plan saved to: %s", plan_out)
        execute_plan(plan, root, dry_run=True)
        _print_summary(stats, len(plan), 0, 0, cognitive_mode)
        return 0

    moved, failed = execute_plan(
        plan,
        root,
        dry_run=args.dry_run,
        tags_map=tags_map if args.tag_files else None,
    )
    _print_summary(stats, moved, failed, 0, cognitive_mode)
    return 0 if failed == 0 else 1


# ─── Tkinter GUI ──────────────────────────────────────────────────────────────

class SmartOrganizerApp:
    """AI-enhanced Tkinter GUI for SMART-FILE."""

    def __init__(self, initial_path: Optional[str] = None) -> None:
        self.root_win = tk.Tk()
        self.root_win.title("SMART-FILE — AI-Enhanced File Organizer")
        self.root_win.geometry("900x760")
        self.root_win.resizable(True, True)

        start_dir = initial_path or str(Path.home())
        self.target_path    = tk.StringVar(value=start_dir)
        self.mode_var       = tk.StringVar(value="flat")
        self.by_date_var    = tk.StringVar(value="none")
        self.dup_action_var = tk.StringVar(value="move_to_duplicates")
        self.include_hidden = tk.BooleanVar(value=False)
        self.large_gb_var   = tk.DoubleVar(value=0.0)
        self.cognitive_var  = tk.StringVar(value=CognitiveMode.EXTENSION.value)
        self.ocr_var        = tk.BooleanVar(value=False)
        self.sub_cat_var    = tk.BooleanVar(value=False)
        self.tag_files_var  = tk.BooleanVar(value=False)

        self._current_plan: List[Tuple[Path, Path]] = []
        self._current_tags: Dict[str, List[str]] = {}

        self._build_ui()
        self.root_win.mainloop()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root_win, padding=12)
        outer.grid(sticky="nsew")
        self.root_win.columnconfigure(0, weight=1)
        self.root_win.rowconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)

        # ── Folder row ────────────────────────────────────────────────────────
        ttk.Label(outer, text="Target Folder:").grid(
            row=0, column=0, sticky="w", pady=4
        )
        ttk.Entry(outer, textvariable=self.target_path, width=60).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(outer, text="Browse…", command=self._browse).grid(
            row=0, column=2, padx=4
        )

        # ── Notebook (tabs) ───────────────────────────────────────────────────
        nb = ttk.Notebook(outer)
        nb.grid(row=1, column=0, columnspan=3, sticky="ew", pady=8)

        # Tab 1 — Organisation options
        tab_org = ttk.Frame(nb, padding=10)
        nb.add(tab_org, text=" 📁 Organisation ")

        ttk.Label(tab_org, text="Recursion mode:").grid(
            row=0, column=0, sticky="w"
        )
        for i, (val, lbl) in enumerate([
            ("flat",   "Flat (all → root)"),
            ("mirror", "Mirror (keep structure)"),
            ("none",   "None (top-level only)"),
        ]):
            ttk.Radiobutton(
                tab_org, text=lbl, variable=self.mode_var, value=val
            ).grid(row=0, column=i + 1, padx=8, sticky="w")

        ttk.Label(tab_org, text="Group by date:").grid(
            row=1, column=0, sticky="w", pady=6
        )
        for i, (val, lbl) in enumerate([
            ("none", "None"), ("year", "By Year"), ("year-month", "By Year-Month"),
        ]):
            ttk.Radiobutton(
                tab_org, text=lbl, variable=self.by_date_var, value=val
            ).grid(row=1, column=i + 1, padx=8, sticky="w")

        ttk.Label(tab_org, text="Duplicates:").grid(
            row=2, column=0, sticky="w", pady=6
        )
        ttk.Radiobutton(
            tab_org, text="Move to Duplicates/",
            variable=self.dup_action_var, value="move_to_duplicates",
        ).grid(row=2, column=1, padx=8, sticky="w")
        ttk.Radiobutton(
            tab_org, text="Skip (leave in place)",
            variable=self.dup_action_var, value="skip",
        ).grid(row=2, column=2, padx=8, sticky="w")

        ttk.Checkbutton(
            tab_org, text="Include hidden files (dot-files)",
            variable=self.include_hidden,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=6)

        size_row = ttk.Frame(tab_org)
        size_row.grid(row=4, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(size_row, text="Large file threshold (0 = disabled):").grid(
            row=0, column=0
        )
        ttk.Spinbox(
            size_row, from_=0, to=100, increment=0.5,
            textvariable=self.large_gb_var, width=6,
        ).grid(row=0, column=1, padx=6)
        ttk.Label(size_row, text="GB  → Large_<Category> folder").grid(
            row=0, column=2
        )

        # Tab 2 — AI / Cognitive options
        tab_ai = ttk.Frame(nb, padding=10)
        nb.add(tab_ai, text=" 🤖 AI / Cognitive ")

        ttk.Label(
            tab_ai, text="Cognitive mode:", font=("", 10, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(4, 2))

        for i, (val, desc) in enumerate([
            (
                CognitiveMode.EXTENSION.value,
                "Extension  — fast, deterministic (no AI overhead)",
            ),
            (
                CognitiveMode.CONTENT.value,
                "Content    — magic-byte & MIME analysis (ignores extension)",
            ),
            (
                CognitiveMode.ADAPTIVE.value,
                "Adaptive   — multi-sector confidence fusion (recommended)",
            ),
        ]):
            ttk.Radiobutton(
                tab_ai, text=desc, variable=self.cognitive_var, value=val,
            ).grid(row=i + 1, column=0, columnspan=3, sticky="w", padx=16, pady=2)

        ttk.Separator(tab_ai, orient="horizontal").grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=8
        )

        ocr_state = "normal" if (_PIL and _TESSERACT) else "disabled"
        ocr_text = (
            "Enable OCR for scanned images"
            if (_PIL and _TESSERACT)
            else "Enable OCR  (requires: pip install pytesseract Pillow)"
        )
        ttk.Checkbutton(
            tab_ai, text=ocr_text, variable=self.ocr_var, state=ocr_state,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=4)

        ttk.Checkbutton(
            tab_ai,
            text="Sub-categorise Documents  (Invoices, Contracts, Resumes, …)",
            variable=self.sub_cat_var,
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=4)

        ttk.Checkbutton(
            tab_ai,
            text="Save AI tags to organize_tags.json",
            variable=self.tag_files_var,
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=4)

        missing = []
        if not _MAGIC:
            missing.append("python-magic")
        if not (_PIL and _TESSERACT):
            missing.append("pytesseract + Pillow")
        if missing:
            ttk.Label(
                tab_ai,
                text=f"⚠  Optional AI libraries not installed: {', '.join(missing)}",
                foreground="#cc6600",
            ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(12, 0))

        # ── Action buttons ────────────────────────────────────────────────────
        btn_frame = ttk.Frame(outer)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=8)
        for col, (label, cmd) in enumerate([
            ("🔍 Preview Plan",    self._preview),
            ("💾 Save Plan",       self._save_plan),
            ("📂 Load & Run Plan", self._load_run),
            ("▶ Run Now",          self._run_now),
            ("↩ Undo Last Run",    self._undo),
        ]):
            ttk.Button(btn_frame, text=label, command=cmd, width=18).grid(
                row=0, column=col, padx=6
            )

        # ── Output area ───────────────────────────────────────────────────────
        self._log_area = scrolledtext.ScrolledText(
            outer, height=22, wrap=tk.WORD, font=("Consolas", 10)
        )
        self._log_area.grid(
            row=3, column=0, columnspan=3, sticky="nsew", pady=6
        )
        outer.rowconfigure(3, weight=1)

        self._log(
            "Ready.  Select a folder, choose options, then click Preview Plan.\n"
        )
        if not _MAGIC and not (_PIL and _TESSERACT):
            self._log(
                "ℹ  Install optional AI libraries for enhanced analysis:\n"
                "   pip install python-magic pytesseract Pillow\n"
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        self._log_area.insert(tk.END, msg + "\n")
        self._log_area.see(tk.END)
        self.root_win.update_idletasks()

    def _clear(self) -> None:
        self._log_area.delete("1.0", tk.END)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Select folder to organize")
        if folder:
            self.target_path.set(folder)

    def _get_root(self) -> Optional[Path]:
        root = Path(self.target_path.get()).resolve()
        if not root.is_dir():
            messagebox.showerror("Error", f"Not a valid folder:\n{root}")
            return None
        return root

    def _make_categorizer(self) -> Optional[AdaptiveCategorizer]:
        cmode = CognitiveMode(self.cognitive_var.get())
        if cmode == CognitiveMode.EXTENSION:
            return None
        return AdaptiveCategorizer(mode=cmode, enable_ocr=self.ocr_var.get())

    def _build_plan_gui(self) -> Optional[List[Tuple[Path, Path]]]:
        root = self._get_root()
        if root is None:
            return None

        cmode = CognitiveMode(self.cognitive_var.get())
        self._log(f"Scanning: {root}  [cognitive: {cmode.value}]")
        categorizer = self._make_categorizer()

        plan, stats, dup_count, tags_map = build_plan(
            root=root,
            mode=self.mode_var.get(),
            by_date=self.by_date_var.get(),
            large_gb=self.large_gb_var.get(),
            include_hidden=self.include_hidden.get(),
            dup_action=self.dup_action_var.get(),
            exclude_exts=frozenset(),
            script_name=Path(__file__).name,
            categorizer=categorizer,
            sub_categorize=self.sub_cat_var.get(),
            tag_files=self.tag_files_var.get(),
        )

        self._current_tags = tags_map
        self._log(
            f"Found {len(plan)} move(s)  |  {dup_count} duplicate(s) detected.\n"
        )
        if stats:
            self._log("Categories:")
            for cat, cnt in sorted(stats.items(), key=lambda x: -x[1]):
                self._log(f"  {cat:<32} {cnt:4} file(s)")
        self._log("")
        return plan

    # ── Button callbacks ──────────────────────────────────────────────────────

    def _preview(self) -> None:
        self._clear()
        plan = self._build_plan_gui()
        if plan is None:
            return
        self._current_plan = plan
        root = Path(self.target_path.get())

        self._log("Planned moves (first 30 shown):")
        for i, (src, dst) in enumerate(plan[:30], 1):
            try:
                self._log(
                    f"  {i:3}. {src.relative_to(root)}  →  {dst.relative_to(root)}"
                )
            except ValueError:
                self._log(f"  {i:3}. {src.name}  →  {dst.name}")
        if len(plan) > 30:
            self._log(f"  … and {len(plan) - 30} more.")

    def _save_plan(self) -> None:
        if not self._current_plan:
            messagebox.showinfo("Info", "No plan in memory.\nRun 'Preview Plan' first.")
            return
        root = Path(self.target_path.get()).resolve()
        out = root / PLAN_FILENAME
        save_plan_file(self._current_plan, root, out)
        self._log(f"Plan saved → {out}")
        messagebox.showinfo("Saved", f"Plan saved to:\n{out}")

    def _load_run(self) -> None:
        plan_path = filedialog.askopenfilename(
            title="Select plan JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not plan_path:
            return
        root = self._get_root()
        if root is None:
            return

        plan = load_plan_file(Path(plan_path), root)
        valid_plan = [(s, d) for s, d in plan if s.exists() and not d.exists()]
        self._log(
            f"Plan loaded: {len(valid_plan)}/{len(plan)} move(s) still pending."
        )
        if not valid_plan:
            messagebox.showinfo("Info", "All moves in the plan have already been executed.")
            return
        if not messagebox.askyesno(
            "Confirm", f"Execute {len(valid_plan)} move(s) from saved plan?"
        ):
            return
        self._clear()
        self._execute_gui(valid_plan, root)

    def _run_now(self) -> None:
        if not messagebox.askyesno(
            "Confirm",
            "Organize this folder now?\n(Files will be moved — an undo log will be saved.)",
        ):
            return
        self._clear()
        plan = self._build_plan_gui()
        if not plan:
            return
        self._current_plan = plan
        root = Path(self.target_path.get()).resolve()
        self._execute_gui(plan, root)

    def _undo(self) -> None:
        root = self._get_root()
        if root is None:
            return
        undo_dir   = root / UNDO_DIR_NAME
        candidates = (
            sorted(undo_dir.glob("undo_log_*.json"), reverse=True)
            if undo_dir.is_dir()
            else []
        )
        if not candidates:
            messagebox.showinfo("Undo", "No undo logs found in this folder.")
            return
        latest = candidates[0]
        if not messagebox.askyesno("Undo", f"Restore from:\n{latest.name}?"):
            return
        restored = perform_undo(root, latest)
        messagebox.showinfo("Undo complete", f"{restored} file(s) restored.")
        self._log(
            f"Undo complete — {restored} file(s) restored from {latest.name}"
        )

    def _execute_gui(self, plan: List[Tuple[Path, Path]], root: Path) -> None:
        moved  = 0
        failed = 0
        moves_made: List[Tuple[Path, Path]] = []

        for src, dst in plan:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                atomic_move(src, dst)
                try:
                    self._log(
                        f"✅ {src.relative_to(root)}  →  {dst.relative_to(root)}"
                    )
                except ValueError:
                    self._log(f"✅ {src.name}  →  {dst.name}")
                moves_made.append((src, dst))
                moved += 1
            except Exception as exc:
                self._log(f"❌ {src.name}: {exc}")
                failed += 1

        if moves_made:
            log_path = save_undo_log(moves_made, root)
            self._log(f"\nUndo log saved → {log_path.name}")

        if self._current_tags and self.tag_files_var.get():
            tp = save_tags(self._current_tags, root)
            self._log(f"Tags saved → {tp.name}")

        self._log(f"\n{'═' * 50}")
        self._log(f"Done!  Moved: {moved}   Failed: {failed}")
        self._log("═" * 50)


# ─── Entry point ──────────────────────────────────────────────────────────────

def _detect_nautilus_path() -> Optional[str]:
    """Return the current folder path when launched from a Nautilus script."""
    uri = os.environ.get("NAUTILUS_SCRIPT_CURRENT_URI", "")
    if uri.startswith("file://"):
        import urllib.parse
        return urllib.parse.unquote(uri[7:])
    return None


def main() -> None:
    force_cli     = "--cli" in sys.argv
    nautilus_path = _detect_nautilus_path()

    if not force_cli and _TK:
        SmartOrganizerApp(initial_path=nautilus_path)
    else:
        argv = [a for a in sys.argv[1:] if a != "--cli"]
        if nautilus_path and (not argv or argv[0].startswith("-")):
            argv = [nautilus_path] + argv
        sys.exit(cli_main(argv))


if __name__ == "__main__":
    main()
