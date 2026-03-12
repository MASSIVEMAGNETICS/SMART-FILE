#!/usr/bin/env python3
"""
add_context_menu.py — Windows Context Menu Integration for SMART-FILE
======================================================================

Adds "Smart Organize" and "Undo Smart Organize" options to the Windows
Explorer right-click (context) menu for directories and directory backgrounds.

Usage:
    python add_context_menu.py            # add context menu entries
    python add_context_menu.py --remove   # remove context menu entries
    python add_context_menu.py --check    # check if entries exist

Requirements:
    • Windows OS
    • Administrator privileges (needed to write HKEY_CLASSES_ROOT)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Registry key paths for background of a folder (right-click inside folder)
_BG_ROOT = r"Directory\Background\shell"
# Registry key paths for right-clicking directly on a folder
_DIR_ROOT = r"Directory\shell"

_SMART_ORGANIZE_KEY   = "SmartOrganize"
_UNDO_ORGANIZE_KEY    = "UndoSmartOrganize"

_SMART_ORGANIZE_LABEL = "Smart Organize"
_UNDO_ORGANIZE_LABEL  = "Undo Smart Organize"


def _get_paths() -> tuple[str, str]:
    """Return (python_executable, main_script_path) for registry commands."""
    here = Path(__file__).parent.resolve()
    main_script = here / "main.py"

    # Prefer the venv Python if it exists alongside this script
    venv_python = here / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        python_exe = str(venv_python)
    else:
        python_exe = sys.executable

    return python_exe, str(main_script)


def _write_menu_entry(
    reg,  # winreg module
    root_key: str,
    action_key: str,
    label: str,
    command: str,
) -> None:
    """Create a single context-menu entry under *root_key*\\*action_key*."""
    import winreg  # type: ignore  # noqa: F401 — re-imported for type usage

    key_path = rf"{root_key}\{action_key}"
    cmd_path = rf"{key_path}\command"

    with reg.CreateKeyEx(reg.HKEY_CLASSES_ROOT, key_path, 0, reg.KEY_WRITE) as hkey:
        reg.SetValueEx(hkey, "", 0, reg.REG_SZ, label)

    with reg.CreateKeyEx(reg.HKEY_CLASSES_ROOT, cmd_path, 0, reg.KEY_WRITE) as hkey:
        reg.SetValueEx(hkey, "", 0, reg.REG_SZ, command)


def add_context_menu() -> None:
    """Add 'Smart Organize' and 'Undo Smart Organize' to the Windows context menu."""
    try:
        import winreg as reg  # type: ignore
    except ImportError:
        print("❌ winreg is not available. This script must be run on Windows.")
        sys.exit(1)

    python_exe, script_path = _get_paths()

    smart_cmd = f'"{python_exe}" "{script_path}" smart_organize "%V"'
    undo_cmd  = f'"{python_exe}" "{script_path}" undo_smart_organize "%V"'

    errors: list[str] = []

    for root in (_BG_ROOT, _DIR_ROOT):
        try:
            _write_menu_entry(reg, root, _SMART_ORGANIZE_KEY,
                              _SMART_ORGANIZE_LABEL, smart_cmd)
            _write_menu_entry(reg, root, _UNDO_ORGANIZE_KEY,
                              _UNDO_ORGANIZE_LABEL, undo_cmd)
            print(f"✅ Entries added under HKCR\\{root}")
        except OSError as exc:
            errors.append(f"HKCR\\{root}: {exc}")

    if errors:
        print("\n⚠️  Some entries could not be written:")
        for err in errors:
            print(f"   {err}")
        print("\nTry running as Administrator.")
        sys.exit(1)
    else:
        print("\n✅ Context menu options added successfully.")
        print("   Right-click inside (or on) any folder to use them.")
        print("   You may need to restart Explorer:")
        print("   taskkill /f /im explorer.exe && start explorer")


def _delete_registry_tree(reg, hive, key_path: str) -> bool:
    """Delete *key_path* and all its subkeys under *hive* using winreg only.

    Returns ``True`` if the key was deleted, ``False`` if it was not found.
    Raises ``OSError`` for any other failure.
    """
    try:
        handle = reg.OpenKey(hive, key_path, 0, reg.KEY_ALL_ACCESS)
    except OSError:
        return False  # not present — nothing to do

    with handle:
        # Collect subkey names before iterating (the count changes as we delete)
        subkeys: list[str] = []
        try:
            i = 0
            while True:
                subkeys.append(reg.EnumKey(handle, i))
                i += 1
        except OSError:
            pass  # end of subkeys

    # Recurse into each subkey first
    for sub in subkeys:
        _delete_registry_tree(reg, hive, rf"{key_path}\{sub}")

    reg.DeleteKey(hive, key_path)
    return True


def remove_context_menu() -> None:
    """Remove 'Smart Organize' and 'Undo Smart Organize' from the Windows context menu."""
    try:
        import winreg as reg  # type: ignore
    except ImportError:
        print("❌ winreg is not available. This script must be run on Windows.")
        sys.exit(1)

    keys_to_delete = [
        (reg.HKEY_CLASSES_ROOT, rf"{_BG_ROOT}\{_SMART_ORGANIZE_KEY}"),
        (reg.HKEY_CLASSES_ROOT, rf"{_BG_ROOT}\{_UNDO_ORGANIZE_KEY}"),
        (reg.HKEY_CLASSES_ROOT, rf"{_DIR_ROOT}\{_SMART_ORGANIZE_KEY}"),
        (reg.HKEY_CLASSES_ROOT, rf"{_DIR_ROOT}\{_UNDO_ORGANIZE_KEY}"),
    ]

    any_failed = False
    for hive, key_path in keys_to_delete:
        try:
            deleted = _delete_registry_tree(reg, hive, key_path)
            if deleted:
                print(f"✅ Removed: HKCR\\{key_path}")
            else:
                print(f"   Skipped (not present): HKCR\\{key_path}")
        except OSError as exc:
            print(f"⚠️  Could not remove HKCR\\{key_path}: {exc}")
            any_failed = True

    if any_failed:
        sys.exit(1)
    else:
        print("\n✅ Context menu entries removed.")


def check_context_menu() -> bool:
    """Check whether the context menu entries exist."""
    try:
        import winreg as reg  # type: ignore
    except ImportError:
        print("❌ winreg is not available. This script must be run on Windows.")
        sys.exit(1)

    found_all = True
    for root in (_BG_ROOT, _DIR_ROOT):
        for action in (_SMART_ORGANIZE_KEY, _UNDO_ORGANIZE_KEY):
            key_path = rf"{root}\{action}"
            try:
                reg.OpenKey(reg.HKEY_CLASSES_ROOT, key_path)
                print(f"✅ Present: HKCR\\{key_path}")
            except OSError:
                print(f"✗  Missing: HKCR\\{key_path}")
                found_all = False

    return found_all


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add/remove Windows context menu entries for SMART-FILE"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--remove", action="store_true",
                       help="Remove context menu entries")
    group.add_argument("--check", action="store_true",
                       help="Check whether entries are installed")
    args = parser.parse_args()

    if sys.platform != "win32":
        print("⚠️  This script is intended for Windows only.")
        print(f"   Current platform: {sys.platform}")
        sys.exit(1)

    if args.remove:
        remove_context_menu()
    elif args.check:
        active = check_context_menu()
        sys.exit(0 if active else 1)
    else:
        add_context_menu()


if __name__ == "__main__":
    main()
