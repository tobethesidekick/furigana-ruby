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


def _find_system_python():
    """Find a system Python 3 executable with pip available."""
    if sys.platform == 'darwin':
        candidates = ['/usr/local/bin/python3', '/opt/homebrew/bin/python3',
                      '/usr/bin/python3', 'python3']
    elif sys.platform.startswith('linux'):
        candidates = ['/usr/bin/python3', '/usr/local/bin/python3', 'python3']
    else:
        candidates = ['python3', 'python']

    for py in candidates:
        try:
            r = subprocess.run(
                [py, '-c', 'import sys; print(sys.version_info.major)'],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip() == '3':
                # Verify pip is available
                r2 = subprocess.run(
                    [py, '-m', 'pip', '--version'],
                    capture_output=True, text=True, timeout=5)
                if r2.returncode == 0:
                    return py
        except Exception:
            continue
    return None


# ── Helper scripts run by system Python ──────────────────────────────────────

# Single-shot helper: used only by get_status() health check.
# Reads raw text from stdin, tokenizes, writes one JSON line to stdout.
_HELPER = r"""
import sys, json, os

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
import sys, json

sudachi_dir = sys.argv[1]
sys.path.insert(0, sudachi_dir)

try:
    from sudachipy import Dictionary

    def k2h(s):
        return ''.join(
            chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c
            for c in s
        )

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
        r = subprocess.run(
            [py, '-c', _HELPER, sudachi_dir],
            input='テスト',
            capture_output=True, text=True, timeout=15)
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

    if progress_callback:
        progress_callback('Downloading SudachiPy and dictionary (~40 MB)…')

    r = subprocess.run(
        [py, '-m', 'pip', 'install',
         'sudachipy', 'sudachidict_small',
         '--target', sudachi_dir,
         '--prefer-binary',
         '--quiet', '--no-warn-script-location'],
        capture_output=True, text=True, timeout=300)

    if r.returncode != 0:
        err = (r.stderr or r.stdout or 'unknown error').strip()
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
            capture_output=True, text=True, timeout=10)
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
        p = subprocess.Popen(
            [py, '-c', _HELPER_DAEMON, sudachi_dir],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding='utf-8', bufsize=1)

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
