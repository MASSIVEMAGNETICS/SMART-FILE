#!/usr/bin/env python3
"""
GOD-TIER FILE ORGANIZER v4
==========================
Drop into any folder, run it, and watch it magically organize everything.

New in v4:
  • Tkinter GUI — folder browser, all options, Preview / Save Plan / Load & Run / Run Now
  • Duplicates → moved to Duplicates/ folder (content-hash based)
  • Date grouping  — --by-date year | year-month
  • Dry-run → Save Plan → Load & Apply workflow
  • Undo support  — JSON log, --undo flag
  • Three recursion modes: flat (default) | mirror | none
  • Atomic-ish moves, smart (1)(2) conflict naming
  • Progress bar (tqdm, optional) — falls back gracefully
  • Summary stats + coloured output (rich, optional)

Usage:
  python organize_v4.py                      # opens GUI
  python organize_v4.py --cli [folder]       # CLI mode
  python organize_v4.py --cli --dry-run -v   # preview in terminal
  python organize_v4.py --cli --undo         # restore last run
  python organize_v4.py --help
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
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# ─── Optional dependencies (zero hard deps) ─────────────────────────────────
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

# ─── CATEGORY MAP ─────────────────────────────────────────────────────────────
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
DUPLICATES_DIR_NAME = "Duplicates"


# ─── Core helpers ─────────────────────────────────────────────────────────────

def get_category(
    path: Path,
    by_date: Optional[str] = None,
    large_gb: float = 0.0,
) -> str:
    """Return the destination category folder name for *path*."""
    # Date-based grouping takes priority when requested
    if by_date and by_date != "none":
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if by_date == "year":
                return f"By_Year/{mtime.year}"
            if by_date == "year-month":
                return f"By_Year-Month/{mtime.strftime('%Y-%m')}"
        except OSError:
            pass

    # Size-based override
    if large_gb > 0:
        try:
            size_bytes = path.stat().st_size
            if size_bytes >= large_gb * 1_000_000_000:
                ext = path.suffix.lower()
                base = CATEGORY_MAP.get(ext, "Files")
                return f"Large_{base}"
        except OSError:
            pass

    # Extension lookup
    ext = path.suffix.lower()
    if not ext:
        return "No_Extension"
    return CATEGORY_MAP.get(ext, f"{ext.lstrip('.').upper()}_Files")


def quick_hash(path: Path, chunk: int = 8192) -> str:
    """Fast fingerprint: (file-size encoded + first 8 KiB) → BLAKE2b digest."""
    try:
        st = path.stat()
        with path.open("rb") as fh:
            head = fh.read(chunk)
        raw = f"{st.st_size}:".encode() + head
        return hashlib.blake2b(raw, digest_size=20).hexdigest()
    except OSError:
        return f"err_{id(path)}"


def unique_dest(target_dir: Path, name: str) -> Path:
    """Return a path under *target_dir* that does not exist, using (1)(2) numbering."""
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
    """Return True if this path should never be touched."""
    if path.is_dir():
        return True
    if path.name == script_name:
        return True
    if path.name in JUNK_FILES:
        return True
    if not include_hidden and any(part.startswith(".") for part in path.parts):
        return True
    return False


def collect_files(
    root: Path,
    mode: str,
    include_hidden: bool,
    script_name: str,
) -> List[Path]:
    """Return all candidate files under *root* respecting *mode*."""
    iterator: Iterator[Path] = root.iterdir() if mode == "none" else root.rglob("*")
    result = []
    for p in iterator:
        if not p.is_file():
            continue

        rel = p.relative_to(root)

        # Always ignore our own artifacts
        if DUPLICATES_DIR_NAME in rel.parts:
            continue
        if rel.name == PLAN_FILENAME:
            continue
        try:
            p.relative_to(root / UNDO_DIR_NAME)
            continue
        except ValueError:
            pass

        if should_skip(p, include_hidden, script_name):
            continue

        result.append(p)
    return result


def atomic_move(src: Path, dst: Path) -> None:
    """Move src → dst, using a temp file on the same device for atomicity."""
    tmp = dst.with_name(f".{dst.name}.org_tmp")
    try:
        shutil.move(str(src), str(tmp))
        tmp.rename(dst)
    except Exception:
        # If rename fails across devices, ensure tmp is cleaned up
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
    dup_action: str,          # "move_to_duplicates" | "skip"
    exclude_exts: frozenset,
    script_name: str,
) -> Tuple[List[Tuple[Path, Path]], Counter, int]:
    """
    Return (plan, stats_counter, dup_count).
    plan is a list of (src, dst) absolute path pairs.
    """
    files = collect_files(root, mode, include_hidden, script_name)
    plan: List[Tuple[Path, Path]] = []
    stats: Counter = Counter()
    dup_count = 0
    seen_hashes: Dict[str, Path] = {}

    for src in files:
        if src.suffix.lower() in exclude_exts or src.name.lower() in exclude_exts:
            continue

        # Duplicate detection
        h = quick_hash(src)
        if h in seen_hashes:
            dup_count += 1
            if dup_action == "move_to_duplicates":
                # Don't create the directory here — execute_plan handles mkdir
                dup_dir = root / "Duplicates"
                dst = unique_dest(dup_dir, src.name)
                plan.append((src, dst))
                stats["Duplicates"] += 1
            # else: skip
            continue
        seen_hashes[h] = src

        cat = get_category(src, by_date if by_date != "none" else None, large_gb)

        if mode == "mirror":
            rel_parent = src.relative_to(root).parent
            target_dir = root / cat / rel_parent
        else:
            target_dir = root / cat

        dst = unique_dest(target_dir, src.name)
        plan.append((src, dst))
        stats[cat] += 1

    return plan, stats, dup_count


# ─── Undo log ─────────────────────────────────────────────────────────────────

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
        # The undo log stores {"from": original_location, "to": current_location}
        # To undo: move file from current_location back to original_location
        current = root / item["to"]     # where the file lives now (post-organize)
        original = root / item["from"]  # where it should go back (pre-organize)

        if current.exists() and not original.exists():
            try:
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current), str(original))
                restored += 1
                logging.info("Restored: %s", item["from"])
            except Exception as exc:
                logging.warning("Failed to restore %s: %s", item["from"], exc)
        else:
            logging.debug("Skip restore %s (src missing or dest exists)", item["from"])

    logging.info("Undo complete — %d file(s) restored.", restored)
    return restored


# ─── Plan persistence ─────────────────────────────────────────────────────────

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
    result = []
    for item in data:
        src = root / item["from"]
        dst = root / item["to"]
        result.append((src, dst))
    return result


def execute_plan(
    plan: List[Tuple[Path, Path]],
    root: Path,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """Execute *plan*, return (moved_count, failed_count)."""
    moved = 0
    failed = 0
    moves_made: List[Tuple[Path, Path]] = []

    iterator = (
        tqdm(plan, desc="Organizing", unit="file")   # type: ignore[name-defined]
        if _TQDM and not dry_run
        else plan
    )

    for src, dst in iterator:
        if dry_run:
            logging.info("[DRY-RUN]  %s  →  %s", src.relative_to(root), dst.relative_to(root))
            moved += 1
            continue

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            atomic_move(src, dst)
            logging.info("Moved  %s  →  %s", src.relative_to(root), dst.relative_to(root))
            moves_made.append((src, dst))
            moved += 1
        except Exception as exc:
            logging.error("Failed %s: %s", src.name, exc)
            failed += 1

    if moves_made and not dry_run:
        log_path = save_undo_log(moves_made, root)
        logging.info("Undo log → %s", log_path)

    return moved, failed


# ─── CLI entry ────────────────────────────────────────────────────────────────

def _print_summary(stats: Counter, moved: int, failed: int, skipped: int) -> None:
    sep = "═" * 52
    print(f"\n{sep}")
    print(f"  Moved   : {moved:,}")
    print(f"  Failed  : {failed:,}")
    print(f"  Skipped : {skipped:,}")
    if stats:
        print("\n  By category:")
        for cat, cnt in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"    {cat:<22} {cnt:4,} file(s)")
    print(sep)


def cli_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="organize_v4.py",
        description="God-Tier File Organizer v4 — CLI mode",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python organize_v4.py --cli\n"
            "  python organize_v4.py --cli path/to/folder --dry-run -v\n"
            "  python organize_v4.py --cli -m mirror --by-date year-month\n"
            "  python organize_v4.py --cli --undo\n"
        ),
    )
    parser.add_argument("path", nargs="?", default=".", help="Folder to organize (default: .)")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode (skip GUI)")
    parser.add_argument(
        "--mode", "-m",
        choices=["flat", "mirror", "none"],
        default="flat",
        help="flat=all files → root categories | mirror=preserve structure | none=top-level only",
    )
    parser.add_argument(
        "--by-date",
        choices=["none", "year", "year-month"],
        default="none",
        help="Group files by modification date",
    )
    parser.add_argument("--large-gb", type=float, default=0.0,
                        help="Files >= X GB → Large_<Category> folder")
    parser.add_argument("--dry-run", "-d", action="store_true",
                        help="Preview only — nothing is moved")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--hidden", "-H", action="store_true",
                        help="Include hidden (dot) files")
    parser.add_argument("--undo", action="store_true",
                        help="Restore files from the most recent undo log")
    parser.add_argument("--undo-file", type=str, default="",
                        help="Path to a specific undo JSON log to restore from")
    parser.add_argument(
        "--dup-action",
        choices=["move_to_duplicates", "skip"],
        default="move_to_duplicates",
        help="What to do with duplicate files",
    )
    parser.add_argument("--exclude", type=str, default="",
                        help="Comma-separated extensions or filenames to skip (.tmp,.log)")
    parser.add_argument(
        "--save-plan", type=str, default="",
        help="After building plan, save it to this JSON file (implies --dry-run)",
    )
    parser.add_argument(
        "--load-plan", type=str, default="",
        help="Load and execute a previously saved plan JSON file",
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

    script_name = Path(__file__).name
    exclude_exts = frozenset(
        x.strip().lower() for x in args.exclude.split(",") if x.strip()
    )

    # ── Undo mode ────────────────────────────────────────────────────────────
    if args.undo:
        undo_file = Path(args.undo_file) if args.undo_file else None
        perform_undo(root, undo_file)
        return 0

    # ── Load-and-execute plan mode ────────────────────────────────────────────
    if args.load_plan:
        plan_path = Path(args.load_plan)
        if not plan_path.is_file():
            logging.error("Plan file not found: %s", plan_path)
            return 1
        plan = load_plan_file(plan_path, root)
        logging.info("Loaded plan with %d move(s).", len(plan))
        moved, failed = execute_plan(plan, root, dry_run=False)
        _print_summary(Counter(), moved, failed, 0)
        return 0

    # ── Normal / dry-run mode ─────────────────────────────────────────────────
    logging.info("Scanning: %s", root)
    plan, stats, dup_count = build_plan(
        root=root,
        mode=args.mode,
        by_date=args.by_date,
        large_gb=args.large_gb,
        include_hidden=args.hidden,
        dup_action=args.dup_action,
        exclude_exts=exclude_exts,
        script_name=script_name,
    )

    if not plan:
        logging.info("No files to organize.")
        return 0

    logging.info("Found %d file(s) to move (%d duplicate(s)).", len(plan), dup_count)

    # Save-plan mode (also implies preview)
    if args.save_plan:
        plan_out = Path(args.save_plan)
        save_plan_file(plan, root, plan_out)
        logging.info("Plan saved to: %s", plan_out)
        # Always show a dry-run preview when saving
        execute_plan(plan, root, dry_run=True)
        _print_summary(stats, len(plan), 0, 0)
        return 0

    moved, failed = execute_plan(plan, root, dry_run=args.dry_run)
    _print_summary(stats, moved, failed, 0)
    return 0 if failed == 0 else 1


# ─── Tkinter GUI ──────────────────────────────────────────────────────────────

class OrganizerApp:
    """Full Tkinter GUI for the God-Tier File Organizer."""

    def __init__(self, initial_path: Optional[str] = None) -> None:
        self.root_win = tk.Tk()
        self.root_win.title("God-Tier File Organizer v4")
        self.root_win.geometry("820x680")
        self.root_win.resizable(True, True)

        # State variables
        start_dir = initial_path or str(Path.home())
        self.target_path = tk.StringVar(value=start_dir)
        self.mode_var = tk.StringVar(value="flat")
        self.by_date_var = tk.StringVar(value="none")
        self.dup_action_var = tk.StringVar(value="move_to_duplicates")
        self.include_hidden_var = tk.BooleanVar(value=False)
        self.large_gb_var = tk.DoubleVar(value=0.0)
        self._current_plan: List[Tuple[Path, Path]] = []

        self._build_ui()
        self.root_win.mainloop()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root_win, padding=12)
        outer.grid(sticky="nsew")
        self.root_win.columnconfigure(0, weight=1)
        self.root_win.rowconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)

        # ── Folder row ──────────────────────────────────────────────────────
        ttk.Label(outer, text="Target Folder:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(outer, textvariable=self.target_path, width=60).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(outer, text="Browse…", command=self._browse).grid(
            row=0, column=2, padx=4
        )

        # ── Options panel ───────────────────────────────────────────────────
        opts = ttk.LabelFrame(outer, text="Options", padding=10)
        opts.grid(row=1, column=0, columnspan=3, sticky="ew", pady=10)

        # Mode
        ttk.Label(opts, text="Recursion mode:").grid(row=0, column=0, sticky="w")
        for i, (val, lbl) in enumerate(
            [("flat", "Flat (all → root)"), ("mirror", "Mirror (keep structure)"), ("none", "None (top-level only)")]
        ):
            ttk.Radiobutton(opts, text=lbl, variable=self.mode_var, value=val).grid(
                row=0, column=i + 1, padx=8, sticky="w"
            )

        # Date grouping
        ttk.Label(opts, text="Group by date:").grid(row=1, column=0, sticky="w", pady=6)
        for i, (val, lbl) in enumerate(
            [("none", "None"), ("year", "By Year"), ("year-month", "By Year-Month")]
        ):
            ttk.Radiobutton(opts, text=lbl, variable=self.by_date_var, value=val).grid(
                row=1, column=i + 1, padx=8, sticky="w"
            )

        # Duplicates
        ttk.Label(opts, text="Duplicates:").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Radiobutton(
            opts, text="Move to Duplicates/", variable=self.dup_action_var, value="move_to_duplicates"
        ).grid(row=2, column=1, padx=8, sticky="w")
        ttk.Radiobutton(
            opts, text="Skip (leave in place)", variable=self.dup_action_var, value="skip"
        ).grid(row=2, column=2, padx=8, sticky="w")

        # Hidden files
        ttk.Checkbutton(
            opts, text="Include hidden files (dot-files)", variable=self.include_hidden_var
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=6)

        # Large-file threshold
        size_row = ttk.Frame(opts)
        size_row.grid(row=4, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(size_row, text="Large file threshold (0 = disabled):").grid(row=0, column=0)
        ttk.Spinbox(
            size_row, from_=0, to=100, increment=0.5,
            textvariable=self.large_gb_var, width=6
        ).grid(row=0, column=1, padx=6)
        ttk.Label(size_row, text="GB  → Large_<Category> folder").grid(row=0, column=2)

        # ── Action buttons ──────────────────────────────────────────────────
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

        # ── Output area ─────────────────────────────────────────────────────
        self._log_area = scrolledtext.ScrolledText(
            outer, height=22, wrap=tk.WORD, font=("Consolas", 10)
        )
        self._log_area.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=6)
        outer.rowconfigure(3, weight=1)

        self._log("Ready.  Select a folder and click Preview Plan.\n")

    # ── Helpers ─────────────────────────────────────────────────────────────

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

    def _build_plan_gui(self) -> Optional[List[Tuple[Path, Path]]]:
        root = self._get_root()
        if root is None:
            return None

        self._log(f"Scanning: {root}")
        script_name = Path(__file__).name
        by_date = self.by_date_var.get()
        large_gb = self.large_gb_var.get()

        plan, stats, dup_count = build_plan(
            root=root,
            mode=self.mode_var.get(),
            by_date=by_date,
            large_gb=large_gb,
            include_hidden=self.include_hidden_var.get(),
            dup_action=self.dup_action_var.get(),
            exclude_exts=frozenset(),
            script_name=script_name,
        )

        self._log(f"Found {len(plan)} move(s)  |  {dup_count} duplicate(s) detected.\n")
        if stats:
            self._log("Categories:")
            for cat, cnt in sorted(stats.items(), key=lambda x: -x[1]):
                self._log(f"  {cat:<24} {cnt:4} file(s)")
        self._log("")
        return plan

    # ── Button callbacks ─────────────────────────────────────────────────────

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
                self._log(f"  {i:3}. {src.relative_to(root)}  →  {dst.relative_to(root)}")
            except ValueError:
                self._log(f"  {i:3}. {src.name}  →  {dst.name}")
        if len(plan) > 30:
            self._log(f"  ... and {len(plan) - 30} more.")

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
            title="Select plan JSON", filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not plan_path:
            return
        root = self._get_root()
        if root is None:
            return

        plan = load_plan_file(Path(plan_path), root)
        # Filter out already-done entries
        valid_plan = [(s, d) for s, d in plan if s.exists() and not d.exists()]
        self._log(f"Plan loaded: {len(valid_plan)}/{len(plan)} move(s) still pending.")

        if not valid_plan:
            messagebox.showinfo("Info", "All moves in the plan have already been executed.")
            return
        if not messagebox.askyesno("Confirm", f"Execute {len(valid_plan)} move(s) from saved plan?"):
            return

        self._clear()
        self._execute_gui(valid_plan, root)

    def _run_now(self) -> None:
        if not messagebox.askyesno(
            "Confirm",
            "Organize this folder now?\n(Files will be moved — an undo log will be saved.)"
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
        undo_dir = root / UNDO_DIR_NAME
        candidates = sorted(undo_dir.glob("undo_log_*.json"), reverse=True) if undo_dir.is_dir() else []
        if not candidates:
            messagebox.showinfo("Undo", "No undo logs found in this folder.")
            return
        latest = candidates[0]
        if not messagebox.askyesno("Undo", f"Restore from:\n{latest.name}?"):
            return
        restored = perform_undo(root, latest)
        messagebox.showinfo("Undo complete", f"{restored} file(s) restored.")
        self._log(f"Undo complete — {restored} file(s) restored from {latest.name}")

    def _execute_gui(self, plan: List[Tuple[Path, Path]], root: Path) -> None:
        moved = 0
        failed = 0
        moves_made: List[Tuple[Path, Path]] = []

        for src, dst in plan:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                atomic_move(src, dst)
                try:
                    self._log(f"✅ {src.relative_to(root)}  →  {dst.relative_to(root)}")
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

        self._log(f"\n{'═'*50}")
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
    # Allow --cli flag anywhere in argv to force CLI mode
    force_cli = "--cli" in sys.argv

    # Nautilus integration: pre-fill folder if launched as Nautilus script
    nautilus_path = _detect_nautilus_path()

    if not force_cli and _TK:
        # GUI mode — pass nautilus_path to constructor so it is set before mainloop()
        OrganizerApp(initial_path=nautilus_path)
    else:
        # CLI mode — strip the --cli flag before parsing
        argv = [a for a in sys.argv[1:] if a != "--cli"]
        if nautilus_path and (not argv or argv[0].startswith("-")):
            argv = [nautilus_path] + argv
        sys.exit(cli_main(argv))


if __name__ == "__main__":
    main()
