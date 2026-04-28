"""
deps_loader.py  v6

The Traversable error comes from pykakasi/properties.py calling:
    importlib.resources.files("pykakasi") / "data" / fname

When pykakasi is loaded from our temp directory, it is not a registered
package so importlib.resources.files returns a non-Path Traversable that
os.path.join cannot use.

Fix: patch importlib.resources.files() BEFORE importing pykakasi,
so it returns a pathlib.Path for "pykakasi". This intercepts at the
stdlib level regardless of .py/.pyc caching.
"""

import sys
import os
import zipfile
import tempfile
import shutil
import threading
import pathlib

_lock = threading.Lock()
_extracted_path = None
_ready = False
_resources_patched = False


def _find_plugin_zip():
    # 1. Inside Calibre — use calibre's own config_dir
    try:
        from calibre.utils.config import config_dir
        plugins_dir = os.path.join(config_dir, 'plugins')
        if os.path.isdir(plugins_dir):
            for fname in sorted(os.listdir(plugins_dir)):
                if 'furigana' in fname.lower() and fname.endswith('.zip'):
                    return os.path.join(plugins_dir, fname)
    except Exception:
        pass
    # 2. Standalone script — check standard per-platform Calibre locations
    _candidates = []
    if sys.platform == 'darwin':
        _candidates.append(os.path.expanduser(
            '~/Library/Preferences/calibre/plugins'))
    elif sys.platform.startswith('linux'):
        _candidates.append(os.path.expanduser(
            '~/.config/calibre/plugins'))
    else:
        _candidates.append(os.path.expanduser(
            '~/AppData/Roaming/calibre/plugins'))
    for plugins_dir in _candidates:
        if os.path.isdir(plugins_dir):
            for fname in sorted(os.listdir(plugins_dir)):
                if 'furigana' in fname.lower() and fname.endswith('.zip'):
                    return os.path.join(plugins_dir, fname)
    # 3. Something on sys.path is the zip directly
    for path in sys.path:
        if isinstance(path, str) and path.endswith('.zip'):
            if 'furigana' in path.lower():
                return path
    return None


def _extract_bundled_deps(zip_path):
    """Extract bundled_deps/ from plugin zip to a stable temp dir."""
    extract_base = os.path.join(tempfile.gettempdir(), 'calibre_furigana_deps')
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            members = [n for n in zf.namelist() if n.startswith('bundled_deps/')]
            if not members:
                return None
            marker = os.path.join(extract_base, '.extracted')
            need_extract = True
            if os.path.exists(marker):
                try:
                    with open(marker) as f:
                        if f.read().strip() == zip_path:
                            need_extract = False
                except Exception:
                    pass
            if need_extract:
                if os.path.exists(extract_base):
                    shutil.rmtree(extract_base, ignore_errors=True)
                os.makedirs(extract_base, exist_ok=True)
                zf.extractall(extract_base, members=members)
                with open(marker, 'w') as f:
                    f.write(zip_path)
            deps_path = os.path.join(extract_base, 'bundled_deps')
            return deps_path if os.path.isdir(deps_path) else None
    except Exception:
        return None


def _patch_importlib_resources(pykakasi_pkg_path):
    """
    Patch importlib.resources.files() so that when called with 'pykakasi'
    it returns a pathlib.Path pointing to our extracted package directory.

    This intercepts at the stdlib level — works regardless of how Python
    caches or loads the pykakasi .py/.pyc files.
    """
    global _resources_patched

    pkg_path = pathlib.Path(pykakasi_pkg_path)

    try:
        import importlib.resources as _ir

        _orig = getattr(_ir, '_furigana_orig_files', None) or _ir.files

        def _patched(package, *args, **kwargs):
            pkg_name = package if isinstance(package, str) else getattr(package, '__name__', str(package))
            if pkg_name == 'pykakasi' or (hasattr(package, '__name__') and package.__name__ == 'pykakasi'):
                return pkg_path
            return _orig(package, *args, **kwargs)

        _ir._furigana_orig_files = _orig
        _ir.files = _patched
        _resources_patched = True
        return True
    except Exception as e:
        return False


def _load_pykakasi(deps_path):
    """
    Add deps_path to sys.path, patch importlib.resources, clear any cached
    pykakasi modules, then import pykakasi fresh.
    Returns (success, error_str).
    """
    pykakasi_pkg = os.path.join(deps_path, 'pykakasi')
    if not os.path.isdir(pykakasi_pkg):
        return False, f"pykakasi package not found at {pykakasi_pkg}"

    # 1. Patch importlib.resources BEFORE importing
    _patch_importlib_resources(pykakasi_pkg)

    # 2. Add to sys.path
    if deps_path not in sys.path:
        sys.path.insert(0, deps_path)

    # 3. Evict any previously imported (possibly broken) pykakasi modules
    for mod in list(sys.modules.keys()):
        if mod == 'pykakasi' or mod.startswith('pykakasi.'):
            del sys.modules[mod]

    # 4. Import
    try:
        import pykakasi  # noqa
        return True, 'ok'
    except Exception as e:
        return False, str(e)


def ensure_deps():
    """Make pykakasi importable. Thread-safe. Returns True on success."""
    global _extracted_path, _ready

    if _ready:
        return True

    with _lock:
        if _ready:
            return True

        # 1. Try extracting from plugin zip
        zip_path = _find_plugin_zip()
        if zip_path:
            deps_path = _extract_bundled_deps(zip_path)
            if deps_path:
                _extracted_path = deps_path
                ok, msg = _load_pykakasi(deps_path)
                if ok:
                    _ready = True
                    return True

        # 2. Dev mode — bundled_deps next to this file
        try:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            bundled = os.path.join(plugin_dir, 'bundled_deps')
            if os.path.isdir(bundled):
                _extracted_path = bundled
                ok, msg = _load_pykakasi(bundled)
                if ok:
                    _ready = True
                    return True
        except Exception:
            pass

        # 3. System pykakasi — still patch resources in case it has same issue
        try:
            import pykakasi as _pk
            pkg_dir = os.path.dirname(os.path.abspath(_pk.__file__))
            _patch_importlib_resources(pkg_dir)
            # Re-import with patch active
            for mod in list(sys.modules.keys()):
                if mod == 'pykakasi' or mod.startswith('pykakasi.'):
                    del sys.modules[mod]
            import pykakasi  # noqa
            _ready = True
            return True
        except Exception:
            pass

        return False


def ensure_opencc():
    """
    Make opencc (opencc-python-reimplemented) importable from bundled deps.
    Thread-safe.  Returns True on success.

    opencc doesn't need the importlib.resources patch that pykakasi requires —
    it locates its dict files relative to __file__ using plain os.path, so
    extracting it to a temp dir is sufficient.
    """
    global _extracted_path

    # Already importable?
    try:
        import opencc   # noqa
        return True
    except ImportError:
        pass

    with _lock:
        # Reuse extraction already done by ensure_deps(), or do it now
        if not _extracted_path:
            zip_path = _find_plugin_zip()
            if zip_path:
                deps_path = _extract_bundled_deps(zip_path)
                if deps_path:
                    _extracted_path = deps_path

        if _extracted_path:
            if _extracted_path not in sys.path:
                sys.path.insert(0, _extracted_path)
            try:
                import opencc   # noqa
                return True
            except ImportError:
                pass

        # Dev mode — bundled_deps next to this file
        try:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            bundled = os.path.join(plugin_dir, 'bundled_deps')
            if os.path.isdir(bundled):
                if bundled not in sys.path:
                    sys.path.insert(0, bundled)
                import opencc   # noqa
                _ready = True
                return True
        except Exception:
            pass

    return False


def get_status():
    if _ready:
        try:
            import pykakasi
            return (f"pykakasi {pykakasi.__version__} ready "
                    f"({'system' if not _extracted_path else _extracted_path})"
                    f"{' [resources patched]' if _resources_patched else ''}")
        except Exception:
            pass
    return f"NOT available (extracted={_extracted_path!r}, resources_patched={_resources_patched})"
