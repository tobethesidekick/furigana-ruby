"""
engines/sudachi.py
High-accuracy engine using SudachiPy via system Python subprocess.

Why subprocess instead of direct import:
  Calibre ships its own embedded Python with a hardened runtime. macOS
  enforces Team ID matching when loading .so files — SudachiPy's compiled
  extension is signed by a different team and cannot be loaded into
  Calibre's process regardless of Python version. Running SudachiPy in a
  separate system Python process bypasses this restriction entirely.

Install location:
  ~/Library/Preferences/calibre/furigana_sudachi/  (macOS)
  ~/.config/calibre/furigana_sudachi/              (Linux)
  ~/AppData/Roaming/calibre/furigana_sudachi/      (Windows)

This directory is outside the plugin ZIP and survives plugin updates.
A version marker file records which Python ABI was used for the install,
so a Calibre update that changes Python version is detected and flagged.
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path

try:
    from calibre_plugins.furigana_ruby.engine_registry import FuriganaEngine, register
except ImportError:
    from engine_registry import FuriganaEngine, register


# ── Paths ─────────────────────────────────────────────────────────────────────

def get_sudachi_dir():
    try:
        from calibre.utils.config import config_dir as _cd
        base = _cd
    except ImportError:
        if sys.platform == 'darwin':
            base = os.path.expanduser('~/Library/Preferences/calibre')
        elif sys.platform.startswith('linux'):
            base = os.path.expanduser('~/.config/calibre')
        else:
            base = os.path.expanduser('~/AppData/Roaming/calibre')
    return os.path.join(base, 'furigana_sudachi')


def _marker_path():
    return os.path.join(get_sudachi_dir(), '.sudachi_marker.json')


def _subprocess_kwargs():
    """Return kwargs for subprocess calls that are safe on all platforms.

    - encoding='utf-8' / errors='replace': avoids cp1252/cp932 mangling on
      Windows and handles any stray non-UTF-8 bytes in pip output.
    - env with PYTHONIOENCODING: ensures the child process itself uses UTF-8
      for its own stdin/stdout even when the Windows console code page differs.
    - CREATE_NO_WINDOW (Windows only): suppresses the console window flash that
      appears every time a subprocess is spawned from a GUI application.
    """
    kw = dict(encoding='utf-8', errors='replace')
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'          # PEP 540 — UTF-8 mode (Python 3.7+)
    kw['env'] = env
    if sys.platform == 'win32':
        kw['creationflags'] = 0x08000000  # CREATE_NO_WINDOW
    return kw


def _find_system_python():
    """Find a system Python 3 executable with pip available.

    Windows notes:
    - 'py'      → Windows Python Launcher (most reliable, installed with Python)
    - 'python3' → rarely exists on Windows
    - 'python'  → may open Microsoft Store on Win10/11 if Python is not installed
    The launcher is tried first so it takes precedence over Store stubs.
    """
    if sys.platform == 'darwin':
        candidates = ['/usr/local/bin/python3', '/opt/homebrew/bin/python3',
                      '/usr/bin/python3', 'python3']
    elif sys.platform.startswith('linux'):
        candidates = ['/usr/bin/python3', '/usr/local/bin/python3', 'python3']
    else:
        # Windows — try the Python Launcher first, then bare names
        candidates = ['py', 'python3', 'python']

    kw = _subprocess_kwargs()
    for py in candidates:
        try:
            r = subprocess.run(
                [py, '-c', 'import sys; print(sys.version_info.major)'],
                capture_output=True, text=True, timeout=5, **kw)
            if r.returncode == 0 and r.stdout.strip() == '3':
                # Verify pip is available
                r2 = subprocess.run(
                    [py, '-m', 'pip', '--version'],
                    capture_output=True, text=True, timeout=5, **kw)
                if r2.returncode == 0:
                    return py
        except Exception:
            continue
    return None


# ── Helper scripts run by system Python ──────────────────────────────────────

# Single-shot helper: used only by get_status() health check.
# Reads raw text from stdin, tokenizes, writes one JSON line to stdout.
_HELPER = r"""
import sys, json, os, warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

sudachi_dir = sys.argv[1]
sys.path.insert(0, sudachi_dir)

try:
    import sudachipy
    from sudachipy import Dictionary

    def k2h(s):
        return ''.join(
            chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c
            for c in s
        )

    text = sys.stdin.read()
    # dict= is the current API (dict_type= deprecated in 0.6.x, removed in future)
    try:
        tok = Dictionary(dict='small').create()
    except TypeError:
        tok = Dictionary(dict_type='small').create()
    tokens = tok.tokenize(text)
    result = [(t.surface(), k2h(t.reading_form())) for t in tokens]
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)
except Exception as e:
    sys.stderr.write(str(e))
    sys.exit(1)
"""

# Daemon helper: stays alive between tokenize() calls so the dictionary is
# loaded only once per Calibre session instead of once per HTML file.
# Protocol: write "READY\n" on start; then for each request read one JSON
# line (the text), write one JSON line (the result), flush.
_HELPER_DAEMON = r"""
import sys, json, warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

sudachi_dir = sys.argv[1]
sys.path.insert(0, sudachi_dir)

try:
    from sudachipy import Dictionary

    def k2h(s):
        return ''.join(
            chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c
            for c in s
        )

    # dict= is the current API (dict_type= deprecated in 0.6.x, removed in future)
    try:
        tok = Dictionary(dict='small').create()
    except TypeError:
        tok = Dictionary(dict_type='small').create()
    sys.stdout.write('READY\n')
    sys.stdout.flush()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line or line == 'EXIT':
            break
        try:
            text = json.loads(line)
            tokens = tok.tokenize(text)
            result = [(t.surface(), k2h(t.reading_form())) for t in tokens]
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + '\n')
        except Exception as e:
            sys.stdout.write(json.dumps({'error': str(e)}) + '\n')
        sys.stdout.flush()

    sys.exit(0)
except Exception as e:
    sys.stderr.write(str(e) + '\n')
    sys.exit(1)
"""


# ── Status helpers ────────────────────────────────────────────────────────────

class SudachiStatus:
    NOT_DOWNLOADED = 'not_downloaded'
    READY          = 'ready'
    BROKEN         = 'broken'
    CALIBRE_UPDATED = 'calibre_updated'


def get_status():
    """Return (SudachiStatus, version_str_or_None)."""
    sudachi_dir = get_sudachi_dir()
    if not os.path.isdir(sudachi_dir):
        return SudachiStatus.NOT_DOWNLOADED, None

    marker = _marker_path()
    if not os.path.isfile(marker):
        return SudachiStatus.NOT_DOWNLOADED, None

    try:
        with open(marker, encoding='utf-8') as f:
            info = json.load(f)
    except Exception:
        return SudachiStatus.BROKEN, None

    # Check for Calibre Python ABI mismatch (e.g. after Calibre update)
    current_abi = getattr(sys.implementation, 'cache_tag', '')
    stored_abi  = info.get('calibre_abi', '')
    if stored_abi and current_abi and stored_abi != current_abi:
        return SudachiStatus.CALIBRE_UPDATED, info.get('version')

    # Quick runtime check
    py = _find_system_python()
    if not py:
        return SudachiStatus.BROKEN, info.get('version')

    try:
        kw = _subprocess_kwargs()
        r = subprocess.run(
            [py, '-c', _HELPER, sudachi_dir],
            input='テスト',
            capture_output=True, text=True, timeout=15, **kw)
        if r.returncode == 0:
            return SudachiStatus.READY, info.get('version')
        return SudachiStatus.BROKEN, info.get('version')
    except Exception:
        return SudachiStatus.BROKEN, info.get('version')


def is_ready():
    status, _ = get_status()
    return status == SudachiStatus.READY


def get_version():
    _, ver = get_status()
    return ver


# ── Install / remove ──────────────────────────────────────────────────────────

def install(progress_callback=None):
    """
    Install SudachiPy + sudachidict_small for system Python into get_sudachi_dir().
    progress_callback(message: str) is called with status text updates.
    Raises RuntimeError on failure.
    Always wipes the existing install directory first so a broken prior install
    cannot block a fresh download.
    """
    import shutil

    py = _find_system_python()
    if not py:
        raise RuntimeError(
            'Python 3 with pip not found. '
            'Install Python 3 from python.org, then try again.')

    sudachi_dir = get_sudachi_dir()

    # Wipe any existing (possibly broken) install before downloading fresh.
    # This avoids pip --upgrade failing due to corrupted or partial files.
    if os.path.isdir(sudachi_dir):
        SudachiEngine._stop_daemon()   # kill daemon before wiping its files
        shutil.rmtree(sudachi_dir, ignore_errors=True)
    os.makedirs(sudachi_dir, exist_ok=True)

    try:
        from calibre_plugins.furigana_ruby.plugin_logger import logger as _lg
    except ImportError:
        try:
            from plugin_logger import logger as _lg
        except ImportError:
            _lg = None

    if _lg:
        _lg.info(f'Sudachi: starting install — python={py} target={sudachi_dir}')

    if progress_callback:
        progress_callback('Downloading SudachiPy and dictionary (~40 MB)…')

    kw = _subprocess_kwargs()
    r = subprocess.run(
        [py, '-m', 'pip', 'install',
         'sudachipy', 'sudachidict_small',
         '--target', sudachi_dir,
         '--prefer-binary',
         '--quiet', '--no-warn-script-location'],
        capture_output=True, text=True, timeout=300, **kw)

    if r.returncode != 0:
        err = (r.stderr or r.stdout or 'unknown error').strip()
        if _lg:
            _lg.error(f'Sudachi: pip install failed — {err[:200]}')
        raise RuntimeError(f'pip install failed: {err}')

    if progress_callback:
        progress_callback('Verifying installation…')

    # Detect installed version
    version = None
    try:
        rv = subprocess.run(
            [py, '-c',
             f'import sys; sys.path.insert(0,{sudachi_dir!r}); '
             f'import sudachipy; print(sudachipy.__version__)'],
            capture_output=True, text=True, timeout=10, **kw)
        if rv.returncode == 0:
            version = rv.stdout.strip()
    except Exception:
        pass

    # Write version marker
    try:
        with open(_marker_path(), 'w', encoding='utf-8') as f:
            json.dump({
                'version':     version,
                'calibre_abi': getattr(sys.implementation, 'cache_tag', ''),
                'system_py':   py,
            }, f)
    except Exception:
        pass

    if _lg:
        _lg.info(f'Sudachi: install complete — version={version} python={py}')


def generate_diagnostics():
    """Return a formatted diagnostic report string for bug reports.

    Covers platform, Python discovery, install state, ABI check, and a live
    health-check run.  Safe to call at any time — catches all exceptions.
    """
    import datetime, platform as _platform

    lines = []
    def _h(title):
        lines.append('')
        lines.append(title)
        lines.append('─' * len(title))

    lines.append('FuriganaRuby Plugin — SudachiPy Diagnostics')
    lines.append('=' * 44)
    lines.append(f'Generated : {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    # ── Platform ──────────────────────────────────────────────────
    _h('Platform')
    try:
        lines.append(f'OS        : {_platform.system()} {_platform.release()} '
                     f'({_platform.machine()})')
    except Exception as e:
        lines.append(f'OS        : (error: {e})')

    try:
        lines.append(f'Python    : {sys.version.split()[0]} '
                     f'({getattr(sys.implementation, "cache_tag", "?")})')
    except Exception as e:
        lines.append(f'Python    : (error: {e})')

    try:
        from calibre.constants import numeric_version as _cv
        lines.append(f'Calibre   : {".".join(str(x) for x in _cv)}')
    except Exception:
        lines.append('Calibre   : (not importable)')

    try:
        from calibre.utils.config import config_dir as _cd
        lines.append(f'config_dir: {_cd}')
    except Exception:
        lines.append('config_dir: (not importable)')

    # ── Python Discovery ──────────────────────────────────────────
    _h('Python Discovery')
    if sys.platform == 'darwin':
        candidates = ['/usr/local/bin/python3', '/opt/homebrew/bin/python3',
                      '/usr/bin/python3', 'python3']
    elif sys.platform.startswith('linux'):
        candidates = ['/usr/bin/python3', '/usr/local/bin/python3', 'python3']
    else:
        candidates = ['py', 'python3', 'python']

    kw = _subprocess_kwargs()
    found_py = None
    for py in candidates:
        try:
            r = subprocess.run(
                [py, '-c', 'import sys; print(sys.version)'],
                capture_output=True, text=True, timeout=5, **kw)
            if r.returncode == 0:
                ver_line = r.stdout.strip().split('\n')[0]
                r2 = subprocess.run(
                    [py, '-m', 'pip', '--version'],
                    capture_output=True, text=True, timeout=5, **kw)
                pip_ok = r2.returncode == 0
                pip_ver = r2.stdout.strip().split('\n')[0] if pip_ok else 'not found'
                lines.append(f'  ✓ {py!r:30s} Python {ver_line[:30]}')
                lines.append(f'    pip: {pip_ver}')
                if pip_ok and found_py is None:
                    found_py = py
                    lines.append(f'    → selected')
            else:
                lines.append(f'  ✗ {py!r:30s} (exit {r.returncode})')
        except FileNotFoundError:
            lines.append(f'  – {py!r:30s} (not found in PATH)')
        except Exception as e:
            lines.append(f'  ✗ {py!r:30s} (error: {e})')

    if found_py is None:
        lines.append('  ⚠ No usable Python 3 + pip found')

    # ── Install State ─────────────────────────────────────────────
    _h('SudachiPy Install')
    sudachi_dir = get_sudachi_dir()
    lines.append(f'Install dir: {sudachi_dir}')
    lines.append(f'Dir exists : {os.path.isdir(sudachi_dir)}')

    marker = _marker_path()
    lines.append(f'Marker file: {os.path.isfile(marker)}')
    info = {}
    if os.path.isfile(marker):
        try:
            with open(marker, encoding='utf-8') as f:
                info = json.load(f)
            lines.append(f'Stored ver : {info.get("version", "?")}')
            lines.append(f'Stored ABI : {info.get("calibre_abi", "?")}')
            lines.append(f'System py  : {info.get("system_py", "?")}')
        except Exception as e:
            lines.append(f'Marker read: ERROR — {e}')

    current_abi = getattr(sys.implementation, 'cache_tag', '')
    stored_abi  = info.get('calibre_abi', '')
    lines.append(f'Current ABI: {current_abi}')
    if stored_abi and current_abi:
        match = '✓ match' if stored_abi == current_abi else '✗ MISMATCH (Calibre updated)'
        lines.append(f'ABI check  : {match}')

    # ── Health Check ──────────────────────────────────────────────
    _h('Health Check')
    if not found_py:
        lines.append('Skipped — no usable Python found')
    elif not os.path.isdir(sudachi_dir):
        lines.append('Skipped — SudachiPy not installed')
    else:
        try:
            kw2 = _subprocess_kwargs()
            r = subprocess.run(
                [found_py, '-c', _HELPER, sudachi_dir],
                input='テスト',
                capture_output=True, text=True, timeout=15, **kw2)
            lines.append(f'Exit code  : {r.returncode}')
            lines.append(f'stdout     : {r.stdout.strip()[:120]}')
            if r.stderr.strip():
                lines.append(f'stderr     : {r.stderr.strip()[:200]}')
            if r.returncode == 0:
                lines.append('Result     : ✓ READY')
            else:
                lines.append('Result     : ✗ BROKEN')
        except Exception as e:
            lines.append(f'Error      : {e}')

    lines.append('')
    return '\n'.join(lines)


def remove():
    """Remove the SudachiPy install directory."""
    import shutil
    SudachiEngine._stop_daemon()   # kill daemon before wiping its files
    sudachi_dir = get_sudachi_dir()
    if os.path.isdir(sudachi_dir):
        shutil.rmtree(sudachi_dir, ignore_errors=True)


# ── Engine class ──────────────────────────────────────────────────────────────

@register
class SudachiEngine(FuriganaEngine):
    id = 'high_accuracy'
    display_name = 'High-accuracy (SudachiPy)'

    _py   = None   # cached system Python path
    _proc = None   # persistent daemon process (class-level, shared across instances)

    def is_available(self):
        return is_ready()

    def _get_py(self):
        if not SudachiEngine._py:
            SudachiEngine._py = _find_system_python()
        return SudachiEngine._py

    @classmethod
    def _stop_daemon(cls):
        p = cls._proc
        cls._proc = None
        if p is not None:
            try:
                p.stdin.write('EXIT\n')
                p.stdin.flush()
            except Exception:
                pass
            try:
                p.wait(timeout=3)
            except Exception:
                pass
            try:
                p.kill()
            except Exception:
                pass

    def _ensure_daemon(self):
        """Return the running daemon, starting it if necessary."""
        p = SudachiEngine._proc
        if p is not None and p.poll() is None:
            return p   # still alive

        py = self._get_py()
        if not py:
            raise RuntimeError('System Python 3 not found.')

        sudachi_dir = get_sudachi_dir()
        kw = _subprocess_kwargs()
        # Popen doesn't take capture_output — map to explicit PIPE args
        kw.pop('creationflags', None)  # handle separately below
        create_flags = 0x08000000 if sys.platform == 'win32' else 0
        p = subprocess.Popen(
            [py, '-c', _HELPER_DAEMON, sudachi_dir],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
            env=kw.get('env'),
            **({'creationflags': create_flags} if create_flags else {}))

        try:
            ready = p.stdout.readline()
        except Exception:
            ready = ''

        if ready.strip() != 'READY':
            err = ''
            try:
                err = p.stderr.read(500)
            except Exception:
                pass
            try:
                p.kill()
            except Exception:
                pass
            raise RuntimeError(
                f'SudachiPy daemon failed to start: {err.strip()}')

        SudachiEngine._proc = p
        return p

    def tokenize(self, text):
        p = self._ensure_daemon()
        try:
            p.stdin.write(json.dumps(text, ensure_ascii=False) + '\n')
            p.stdin.flush()
            line = p.stdout.readline()
        except Exception as e:
            SudachiEngine._proc = None
            raise RuntimeError(f'SudachiPy daemon I/O error: {e}')

        if not line:
            SudachiEngine._proc = None
            raise RuntimeError('SudachiPy daemon process died unexpectedly.')

        try:
            data = json.loads(line)
        except Exception as e:
            raise RuntimeError(f'SudachiPy output parse error: {e}')

        if isinstance(data, dict) and 'error' in data:
            raise RuntimeError(f'SudachiPy error: {data["error"]}')

        return [(orig, hira) for orig, hira in data]
