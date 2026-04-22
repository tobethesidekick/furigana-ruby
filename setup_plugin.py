#!/usr/bin/env python3
"""
setup_plugin.py
Run this script ONCE on your Mac to build the final FuriganaRuby.zip
with pykakasi bundled inside it.

Usage:
  python3 setup_plugin.py

Requirements:
  - FuriganaRuby_base.zip must be in the same folder as this script
  - pykakasi must be installed (pip3 install pykakasi)

Output:
  FuriganaRuby.zip  — the complete plugin, ready to load into Calibre
"""

import sys
import os
import zipfile
import shutil

# ── Locate pykakasi on the system ────────────────────────────────────────────

DEPS = ['pykakasi', 'jaconv', 'deprecated', 'wrapt']

def find_package_dir(pkg_name):
    """Find the directory of an installed Python package."""
    try:
        import importlib
        mod = importlib.import_module(pkg_name)
        path = getattr(mod, '__file__', None)
        if path:
            return os.path.dirname(path)
        # Namespace package
        paths = getattr(mod, '__path__', None)
        if paths:
            return list(paths)[0]
    except ImportError:
        return None
    return None

print("Furigana Ruby Plugin — Setup")
print("=" * 50)

# Check all deps are available
missing = []
pkg_dirs = {}
for dep in DEPS:
    d = find_package_dir(dep)
    if d:
        pkg_dirs[dep] = d
        print(f"  ✓ Found {dep}: {d}")
    else:
        missing.append(dep)
        print(f"  ✗ Missing {dep}")

if missing:
    print(f"\nERROR: Missing packages: {', '.join(missing)}")
    print("Please run:  pip3 install pykakasi")
    sys.exit(1)

print()

# ── Find base plugin zip ──────────────────────────────────────────────────────

script_dir = os.path.dirname(os.path.abspath(__file__))
base_zip = os.path.join(script_dir, 'FuriganaRuby_base.zip')
out_zip  = os.path.join(script_dir, 'FuriganaRuby.zip')

if not os.path.exists(base_zip):
    # Maybe user renamed it
    for fname in os.listdir(script_dir):
        if 'furigana' in fname.lower() and fname.endswith('.zip') and 'base' in fname.lower():
            base_zip = os.path.join(script_dir, fname)
            break
    else:
        print(f"ERROR: Cannot find FuriganaRuby_base.zip in {script_dir}")
        print("Make sure this script is in the same folder as FuriganaRuby_base.zip")
        sys.exit(1)

print(f"Base plugin: {base_zip}")
print(f"Output:      {out_zip}")
print()

# ── Build the bundled_deps structure ─────────────────────────────────────────

def add_dir_to_zip(zf, src_dir, zip_prefix):
    """Recursively add a directory to a zip file under zip_prefix."""
    added = 0
    for root, dirs, files in os.walk(src_dir):
        # Skip __pycache__ to keep zip small (not strictly necessary)
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fname in files:
            # Skip .pyc files — Python will recompile from .py as needed
            if fname.endswith('.pyc'):
                continue
            fpath = os.path.join(root, fname)
            rel   = os.path.relpath(fpath, src_dir)
            arc   = os.path.join(zip_prefix, rel)
            zf.write(fpath, arc)
            added += 1
    return added

# ── Source files that always override whatever is in the base zip ─────────────

SOURCE_FILES = [
    '__init__.py',
    'action.py',
    'config.py',
    'deps_loader.py',
    'furigana_engine.py',
    'jlpt_filter.py',
    'orientation_engine.py',
    'plugin-import-name-furigana_ruby.txt',
    'viewer_inject.css',
    'viewer_inject.js',
    'viewer_plugin.py',
]
SOURCE_DIRS = ['images']   # directories to include recursively

print("Building plugin zip with bundled dependencies...")

with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
    # 1. Copy base zip contents (provides any files we don't override)
    with zipfile.ZipFile(base_zip, 'r') as zin:
        base_names = set(zin.namelist())
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
    print(f"  + Copied base plugin files")

    # 2. Overlay updated source files from this directory (overrides base zip)
    overridden = 0
    for fname in SOURCE_FILES:
        src = os.path.join(script_dir, fname)
        if os.path.isfile(src):
            with open(src, 'rb') as f:
                data = f.read()
            # ZipFile.writestr with an existing name appends a second entry;
            # readers use the last entry, so this effectively overrides it.
            zout.writestr(fname, data)
            overridden += 1
    for dname in SOURCE_DIRS:
        src_dir = os.path.join(script_dir, dname)
        if os.path.isdir(src_dir):
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if d != '__pycache__']
                for fname in files:
                    if fname.endswith('.pyc'):
                        continue
                    fpath = os.path.join(root, fname)
                    arc   = os.path.relpath(fpath, script_dir)
                    with open(fpath, 'rb') as f:
                        data = f.read()
                    zout.writestr(arc, data)
                    overridden += 1
    print(f"  + Overlaid {overridden} source files from {script_dir}")

    # 3. Add each dependency package into bundled_deps/
    total_files = 0
    for dep, pkg_dir in pkg_dirs.items():
        n = add_dir_to_zip(zout, pkg_dir, f'bundled_deps/{dep}')
        total_files += n
        print(f"  + Bundled {dep}: {n} files from {pkg_dir}")

print()
print(f"✓ Done! {total_files} dependency files bundled.")
print(f"✓ Plugin ready: {out_zip}")
print()

# ── Verify ────────────────────────────────────────────────────────────────────

size_mb = os.path.getsize(out_zip) / 1024 / 1024
print(f"  File size: {size_mb:.1f} MB")

with zipfile.ZipFile(out_zip, 'r') as zf:
    all_names = zf.namelist()
    dep_files = [n for n in all_names if n.startswith('bundled_deps/')]
    print(f"  Total entries: {len(all_names)} ({len(dep_files)} in bundled_deps/)")

print()
print("Next steps:")
print("  1. Open Calibre")
print("  2. Preferences → Plugins → Load plugin from file")
print(f"  3. Select: {out_zip}")
print("  4. Restart Calibre")
print("  5. Select a Japanese EPUB → click '振り仮名' in toolbar → Add Furigana")
