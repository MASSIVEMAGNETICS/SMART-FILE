# SMART-FILE — God-Tier File Organizer v4

Drop a single Python file into any folder, run it, and watch it organize
everything automatically by file type, date, or size.

---

## Features

| Feature | Details |
|---------|---------|
| **Auto-categorize** | 60+ extensions → Images, Videos, Audio, Documents, Code, Fonts, Ebooks, Executables, … |
| **Duplicate detection** | Content-hash based → duplicates go to `Duplicates/` folder |
| **Date grouping** | Group files by modification year or year-month |
| **Large-file rules** | Files above a configurable GB threshold → `Large_<Category>/` |
| **Three recursion modes** | `flat` (default), `mirror` (preserve structure), `none` (top-level only) |
| **Dry-run → Save Plan → Apply** | Preview all moves, save to JSON, apply later |
| **Undo support** | Every real run saves a JSON log → restore with `--undo` or GUI button |
| **Tkinter GUI** | Folder browser, all options, Preview / Save Plan / Load & Run / Run Now / Undo |
| **CLI** | Full feature parity with the GUI via flags |
| **Atomic moves** | Temp-file rename pattern — reduces risk of data loss on same filesystem |
| **Conflict naming** | Never overwrites — uses `file (1).ext`, `file (2).ext`, … |
| **File manager integration** | One-command install for Windows Explorer, Linux Nautilus/Nemo/Thunar, macOS Automator |
| **Zero hard dependencies** | Pure stdlib; `tqdm` and `rich` are optional (auto-detected) |

---

## Quick Start

### GUI (default)

```bash
python organize_v4.py
```

A window opens.  
1. Choose a folder with **Browse…**  
2. Pick options (mode, date grouping, duplicate handling, …)  
3. Click **🔍 Preview Plan** — review moves in the output pane  
4. Click **▶ Run Now** — files are moved, undo log saved automatically  
5. Made a mistake? Click **↩ Undo Last Run**

### CLI

```bash
# Preview everything (no files moved)
python organize_v4.py --cli --dry-run -v

# Organize current folder (flat mode — most common)
python organize_v4.py --cli

# Preserve subfolder structure inside each category
python organize_v4.py --cli -m mirror

# Top-level files only (no recursion)
python organize_v4.py --cli -m none

# Group files by year of last modification
python organize_v4.py --cli --by-date year

# Group by year-month (e.g. By_Year-Month/2025-03/)
python organize_v4.py --cli --by-date year-month

# Files ≥ 2 GB go to Large_<Category>/ folders
python organize_v4.py --cli --large-gb 2

# Save plan to JSON, review it, then apply later
python organize_v4.py --cli --save-plan my_plan.json
python organize_v4.py --cli --load-plan my_plan.json

# Undo the last run
python organize_v4.py --cli --undo

# Skip certain extensions
python organize_v4.py --cli --exclude .log,.tmp

# Organize a specific folder (not current directory)
python organize_v4.py --cli /path/to/messy/folder
```

### All CLI flags

```
positional:
  path                    Folder to organize (default: current directory)

options:
  --cli                   Force CLI mode (skips GUI even when Tkinter is available)
  -m, --mode              flat | mirror | none  (default: flat)
  --by-date               none | year | year-month
  --large-gb X            Files ≥ X GB → Large_<Category>/ folder
  -d, --dry-run           Preview only — nothing is moved
  -v, --verbose           Show every move in the terminal
  -H, --hidden            Include hidden dot-files
  --dup-action            move_to_duplicates | skip  (default: move_to_duplicates)
  --exclude EXT,...       Comma-separated extensions/names to skip
  --save-plan FILE        Save the move plan to FILE (JSON), implies dry-run preview
  --load-plan FILE        Load FILE and execute the saved plan
  --undo                  Restore files from the most recent undo log
  --undo-file FILE        Restore from a specific undo log JSON file
```

---

## Category Map

| Folder | Extensions |
|--------|-----------|
| Images | `.jpg` `.jpeg` `.png` `.gif` `.bmp` `.tiff` `.webp` `.heic` `.svg` `.ico` `.raw` |
| Design | `.psd` `.ai` `.xd` `.sketch` |
| Videos | `.mp4` `.mkv` `.avi` `.mov` `.wmv` `.flv` `.webm` `.m4v` `.mpg` `.3gp` |
| Audio  | `.mp3` `.wav` `.flac` `.m4a` `.aac` `.ogg` `.wma` `.opus` |
| Documents | `.pdf` `.doc` `.docx` `.txt` `.md` `.rtf` `.odt` `.pages` |
| Spreadsheets | `.xls` `.xlsx` `.csv` `.ods` `.numbers` |
| Presentations | `.ppt` `.pptx` `.odp` `.key` |
| Archives | `.zip` `.rar` `.7z` `.tar` `.gz` `.bz2` `.xz` `.zst` |
| Code | `.py` `.js` `.ts` `.html` `.css` `.json` `.yaml` `.sh` `.go` `.rs` `.java` … |
| Fonts | `.ttf` `.otf` `.woff` `.woff2` |
| 3D_Models | `.obj` `.fbx` `.stl` `.blend` `.dae` |
| Ebooks | `.epub` `.mobi` `.azw3` |
| Executables | `.exe` `.msi` `.dmg` `.apk` `.deb` `.rpm` `.appimage` |
| Databases | `.db` `.sqlite` `.sqlite3` |
| Disk_Images | `.iso` `.img` `.vmdk` |
| Duplicates | (content-duplicates — any extension) |
| No_Extension | Files with no extension |
| `XYZ_Files` | Any unrecognised extension `.xyz` → `XYZ_Files/` |

---

## File Manager Integration

Run this **once** to add an *"Organize Files Here"* entry to your OS file
manager's right-click menu:

```bash
python setup_integration.py           # install
python setup_integration.py --check   # verify
python setup_integration.py --remove  # uninstall
```

| OS | Integration |
|----|-------------|
| **Windows** | Adds entry to Explorer background context menu via the registry |
| **Linux** | Installs executable script for Nautilus, Nemo, and Thunar |
| **macOS** | Prints step-by-step Automator Quick Action instructions |

After installation:  
- **Windows**: right-click inside any folder in Explorer  
- **Linux**: right-click inside any folder → **Scripts** → *Organize Files Here (God-Tier)*  
- **macOS**: right-click any folder → **Quick Actions** → *Organize Files Here*

---

## Undo

Every real run (GUI or CLI) automatically writes an undo log to
`ORGANIZE_UNDO_LOGS/undo_log_YYYYMMDD_HHMMSS.json` inside the organized folder.

```bash
# Restore the most recent run
python organize_v4.py --cli --undo

# Restore a specific log
python organize_v4.py --cli --undo-file ORGANIZE_UNDO_LOGS/undo_log_20250310_143000.json
```

Or click **↩ Undo Last Run** in the GUI.

---

## Optional Dependencies

Install for enhanced output (both are optional — the script works without them):

```bash
pip install tqdm   # progress bar during large runs
pip install rich   # coloured tree previews in CLI
```

---

## Files

| File | Purpose |
|------|---------|
| `organize_v4.py` | Main organizer script (GUI + CLI) |
| `setup_integration.py` | One-time file manager integration installer |
