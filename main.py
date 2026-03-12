#!/usr/bin/env python3
"""
main.py — SMART-FILE: Smart Organize & Undo
============================================

Command-line entry point for the SMART-FILE application.  Provides two
core actions that can be invoked directly from the Windows context menu
or the terminal:

  smart_organize      — Move files into categorised sub-folders.
  undo_smart_organize — Revert the last smart_organize run in a folder.

Usage:
    python main.py smart_organize [target_path]
    python main.py undo_smart_organize [target_path]

If *target_path* is omitted, the current working directory is used.

The log file (``organize.log``) is stored inside *target_path* so that
undo operations are always scoped to the correct folder.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────

LOG_FILENAME = "organize.log"

#: Maps category name → list of file extensions (lower-case, with leading dot)
FILE_CATEGORIES: dict[str, list[str]] = {
    "Documents":     [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt",
                      ".md", ".markdown", ".pages"],
    "Images":        [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
                      ".tif", ".webp", ".svg", ".heic", ".raw", ".ico"],
    "Videos":        [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
                      ".webm", ".m4v", ".mpg", ".mpeg", ".3gp"],
    "Music":         [".mp3", ".wav", ".flac", ".m4a", ".aac",
                      ".ogg", ".wma", ".opus"],
    "Archives":      [".zip", ".rar", ".7z", ".tar", ".gz",
                      ".bz2", ".xz", ".zst"],
    "Spreadsheets":  [".xls", ".xlsx", ".csv", ".ods", ".numbers"],
    "Presentations": [".ppt", ".pptx", ".odp", ".key"],
    "Code":          [".py", ".js", ".ts", ".jsx", ".tsx", ".html",
                      ".htm", ".css", ".scss", ".json", ".yaml", ".yml",
                      ".toml", ".xml", ".sh", ".bash", ".zsh", ".ps1",
                      ".rb", ".go", ".rs", ".c", ".cpp", ".h", ".java",
                      ".kt", ".swift", ".php", ".lua"],
    "Design":        [".psd", ".ai", ".xd", ".sketch"],
    "Executables":   [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm",
                      ".appimage"],
    "Fonts":         [".ttf", ".otf", ".woff", ".woff2"],
}

# Build a reverse lookup: extension → category
_EXT_TO_CATEGORY: dict[str, str] = {
    ext: cat
    for cat, exts in FILE_CATEGORIES.items()
    for ext in exts
}

# ─── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _category_for(filename: str) -> str | None:
    """Return the category name for *filename*, or ``None`` for unknown types."""
    ext = Path(filename).suffix.lower()
    return _EXT_TO_CATEGORY.get(ext)


def _log_path(target: Path) -> Path:
    """Return the path of the JSON undo-log inside *target*."""
    return target / LOG_FILENAME


# ─── Smart Organize ───────────────────────────────────────────────────────────

def smart_organize(target_path: str | os.PathLike = ".") -> None:
    """Organise files in *target_path* into categorised sub-folders.

    Moves every recognised file into a sub-folder named after its category
    (e.g. ``Documents``, ``Images``).  Unknown extensions are left in place.

    A JSON undo-log is written to ``<target_path>/organize.log`` so that the
    operation can be fully reversed with :func:`undo_smart_organize`.

    Args:
        target_path: Directory to organise.  Defaults to the current directory.
    """
    target = Path(target_path).resolve()
    if not target.is_dir():
        _log.error("Target is not a directory: %s", target)
        sys.exit(1)

    log_file = _log_path(target)
    moves: list[dict[str, str]] = []
    skipped = 0

    _log.info("Starting smart_organize in: %s", target)

    for entry in sorted(target.iterdir()):
        # Skip directories, the log file itself, and hidden files
        if entry.is_dir():
            continue
        if entry.name == LOG_FILENAME:
            continue
        if entry.name.startswith("."):
            continue

        category = _category_for(entry.name)
        if category is None:
            _log.debug("No category for %s — skipping", entry.name)
            skipped += 1
            continue

        dest_dir = target / category
        dest_dir.mkdir(exist_ok=True)

        dest = dest_dir / entry.name

        # Avoid overwriting: append a counter suffix if needed
        counter = 1
        while dest.exists():
            stem = entry.stem
            suffix = entry.suffix
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        _log.info("Moving %s → %s", entry.name, dest.relative_to(target))
        shutil.move(str(entry), str(dest))

        moves.append({
            "src":       str(entry),
            "dest":      str(dest),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    # Persist undo-log
    log_data = {
        "version":    1,
        "organized":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target":     str(target),
        "moves":      moves,
    }
    log_file.write_text(json.dumps(log_data, indent=2), encoding="utf-8")

    _log.info(
        "smart_organize complete: %d file(s) moved, %d skipped. "
        "Undo log: %s",
        len(moves), skipped, log_file,
    )


# ─── Undo Smart Organize ──────────────────────────────────────────────────────

def undo_smart_organize(target_path: str | os.PathLike = ".") -> None:
    """Revert the last :func:`smart_organize` run in *target_path*.

    Reads the JSON undo-log produced by :func:`smart_organize` and moves every
    file back to its original location.  The log is deleted upon success.

    Args:
        target_path: Directory that was previously organised.
    """
    target = Path(target_path).resolve()
    log_file = _log_path(target)

    if not log_file.exists():
        _log.error(
            "No undo log found at %s. Cannot undo.", log_file
        )
        sys.exit(1)

    try:
        log_data: dict = json.loads(log_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _log.error("Failed to read undo log: %s", exc)
        sys.exit(1)

    moves: list[dict[str, str]] = log_data.get("moves", [])
    if not moves:
        _log.warning("Undo log is empty — nothing to revert.")
        log_file.unlink(missing_ok=True)
        return

    _log.info(
        "Starting undo_smart_organize in: %s (%d move(s) to revert)",
        target, len(moves),
    )

    errors: list[str] = []

    for move in reversed(moves):
        src_original = Path(move["src"])
        dest_current = Path(move["dest"])

        if not dest_current.exists():
            _log.warning(
                "File no longer at expected location, skipping: %s",
                dest_current,
            )
            errors.append(f"Not found: {dest_current}")
            continue

        # Recreate the original directory if it was removed
        src_original.parent.mkdir(parents=True, exist_ok=True)

        # Avoid overwriting an existing file at the original location
        restore_target = src_original
        counter = 1
        while restore_target.exists():
            restore_target = src_original.with_stem(
                f"{src_original.stem}_restored_{counter}"
            )
            counter += 1

        _log.info(
            "Restoring %s → %s",
            dest_current.relative_to(target),
            restore_target.relative_to(target),
        )
        shutil.move(str(dest_current), str(restore_target))

    # Clean up empty category directories created during organisation
    for category in FILE_CATEGORIES:
        cat_dir = target / category
        if cat_dir.is_dir():
            try:
                cat_dir.rmdir()  # only removes if empty
                _log.debug("Removed empty directory: %s", cat_dir)
            except OSError:
                pass  # not empty — leave it

    # Remove the undo log
    log_file.unlink(missing_ok=True)

    if errors:
        _log.warning(
            "undo_smart_organize finished with %d warning(s). "
            "Some files could not be restored.",
            len(errors),
        )
    else:
        _log.info("undo_smart_organize complete: all files restored.")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print(
            "SMART-FILE — Smart Organize\n"
            "\n"
            "Usage:\n"
            "  python main.py smart_organize [target_path]\n"
            "  python main.py undo_smart_organize [target_path]\n"
            "\n"
            "If target_path is omitted, the current directory is used."
        )
        sys.exit(1)

    action = sys.argv[1]
    target_path = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

    if action == "smart_organize":
        smart_organize(target_path)
    elif action == "undo_smart_organize":
        undo_smart_organize(target_path)
    else:
        _log.error("Unknown action '%s'. Use smart_organize or undo_smart_organize.", action)
        sys.exit(1)


if __name__ == "__main__":
    main()
