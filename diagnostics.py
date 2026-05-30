"""
diagnostics.py — plugin-wide diagnostic report for FuriganaRuby.

Generates a plain-text snapshot users can paste into a bug report.
Safe to call at any time; catches all exceptions internally.
"""

import os
import sys
import datetime
import platform as _platform


def generate_report():
    """Return a formatted diagnostic report string."""
    lines = []

    def _h(title):
        lines.append('')
        lines.append(title)
        lines.append('─' * max(len(title), 40))

    def _row(label, value):
        lines.append(f'  {label:<22} {value}')

    def _safe(fn, fallback='(error)'):
        try:
            return fn()
        except Exception as e:
            return f'{fallback}: {e}'

    # ── Header ────────────────────────────────────────────────────
    lines.append('FuriganaRuby Plugin — Diagnostic Report')
    lines.append('=' * 42)
    lines.append(f'Generated : {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    # ── Plugin ────────────────────────────────────────────────────
    _h('Plugin')
    try:
        from calibre_plugins.furigana_ruby import FuriganaPluginBase
        ver = '.'.join(str(x) for x in FuriganaPluginBase.version)
    except Exception:
        try:
            from __init__ import FuriganaPluginBase
            ver = '.'.join(str(x) for x in FuriganaPluginBase.version)
        except Exception:
            ver = '(unknown)'
    _row('Version', ver)

    # ── Platform ──────────────────────────────────────────────────
    _h('Platform')
    _row('OS',              _safe(lambda: f'{_platform.system()} {_platform.release()} ({_platform.machine()})'))
    _row('Calibre Python',  _safe(lambda: f'{sys.version.split()[0]} ({getattr(sys.implementation, "cache_tag", "?")}'))
    try:
        from calibre.constants import numeric_version as _cv
        _row('Calibre',     '.'.join(str(x) for x in _cv))
    except Exception:
        _row('Calibre',     '(not importable)')
    try:
        from calibre.utils.config import config_dir as _cd
        _row('config_dir',  _cd)
    except Exception:
        _row('config_dir',  '(not importable)')

    # ── Settings ──────────────────────────────────────────────────
    _h('Plugin Settings')
    try:
        from calibre.utils.config import JSONConfig
        prefs = JSONConfig('plugins/furigana_ruby')
        _row('tile_action',           prefs.get('tile_action', '?'))
        _row('keep_original',         str(prefs.get('keep_original', '?')))
        _row('manual_engine',         prefs.get('manual_engine', '?'))
        _row('auto_engine',           prefs.get('auto_engine', '?'))
        _row('include_viewer_toggle', str(prefs.get('include_viewer_toggle', '?')))
        _row('annotate_levels',       ', '.join(prefs.get('annotate_levels', [])))
        _row('auto_ruby_enabled',     str(prefs.get('auto_ruby_enabled', '?')))
        _row('auto_ruby_levels',      ', '.join(prefs.get('auto_ruby_levels', [])))
        _row('auto_chinese_enabled',  str(prefs.get('auto_chinese_enabled', '?')))
        _row('auto_chinese_direction',prefs.get('auto_chinese_direction', '?'))
        _row('s2t_variant',           prefs.get('s2t_variant', '?'))
        wf = prefs.get('watch_folders', [])
        _row('watch_folders',         f'{len(wf)} configured')
    except Exception as e:
        lines.append(f'  (error reading prefs: {e})')

    # ── SudachiPy ─────────────────────────────────────────────────
    _h('SudachiPy')
    try:
        try:
            from calibre_plugins.furigana_ruby.engines.sudachi import (
                get_sudachi_dir, _marker_path, get_status, SudachiStatus,
                _find_system_python, _subprocess_kwargs, _HELPER)
        except ImportError:
            from engines.sudachi import (
                get_sudachi_dir, _marker_path, get_status, SudachiStatus,
                _find_system_python, _subprocess_kwargs, _HELPER)

        import json, subprocess

        sudachi_dir = get_sudachi_dir()
        _row('Install dir',   sudachi_dir)
        _row('Dir exists',    str(os.path.isdir(sudachi_dir)))

        marker = _marker_path()
        _row('Marker file',   str(os.path.isfile(marker)))

        info = {}
        if os.path.isfile(marker):
            try:
                with open(marker, encoding='utf-8') as f:
                    info = json.load(f)
                _row('Stored version',  info.get('version', '?'))
                _row('Stored ABI',      info.get('calibre_abi', '?'))
                _row('Install Python',  info.get('system_py', '?'))
            except Exception as e:
                _row('Marker read',     f'ERROR: {e}')

        current_abi = getattr(sys.implementation, 'cache_tag', '')
        _row('Current ABI',   current_abi)
        stored_abi = info.get('calibre_abi', '')
        if stored_abi and current_abi:
            _row('ABI match',
                 '✓' if stored_abi == current_abi else '✗ MISMATCH (Calibre updated)')

        # Python discovery
        lines.append('')
        lines.append('  Python Discovery:')
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
                    [py, '-c', 'import sys; print(sys.version.split()[0])'],
                    capture_output=True, text=True, timeout=5, **kw)
                if r.returncode == 0:
                    r2 = subprocess.run(
                        [py, '-m', 'pip', '--version'],
                        capture_output=True, text=True, timeout=5, **kw)
                    pip_ok = r2.returncode == 0
                    tag = '→ selected' if (pip_ok and found_py is None) else ''
                    lines.append(f'    ✓ {py:<32} Python {r.stdout.strip()} '
                                 f'{"pip ✓" if pip_ok else "pip ✗"} {tag}')
                    if pip_ok and found_py is None:
                        found_py = py
                else:
                    lines.append(f'    ✗ {py:<32} (exit {r.returncode})')
            except FileNotFoundError:
                lines.append(f'    – {py:<32} (not in PATH)')
            except Exception as e:
                lines.append(f'    ✗ {py:<32} ({e})')

        if not found_py:
            lines.append('    ⚠ No usable Python 3 + pip found')

        # Live health check
        lines.append('')
        lines.append('  Health Check:')
        if not found_py or not os.path.isdir(sudachi_dir):
            lines.append('    Skipped (no Python or not installed)')
        else:
            try:
                kw2 = _subprocess_kwargs()
                r = subprocess.run(
                    [found_py, '-c', _HELPER, sudachi_dir],
                    input='テスト', capture_output=True, text=True,
                    timeout=15, **kw2)
                lines.append(f'    Exit code : {r.returncode}')
                lines.append(f'    Output    : {r.stdout.strip()[:80]}')
                if r.stderr.strip():
                    lines.append(f'    Stderr    : {r.stderr.strip()[:120]}')
                lines.append(f'    Result    : {"✓ READY" if r.returncode == 0 else "✗ BROKEN"}')
            except Exception as e:
                lines.append(f'    Error     : {e}')

    except Exception as e:
        lines.append(f'  (error in Sudachi section: {e})')

    # ── Calibre Monitor ───────────────────────────────────────────
    _h('Calibre Monitor')
    try:
        import subprocess as _sp
        r = _sp.run(['pgrep', '-f', 'calibre_monitor.py'],
                    capture_output=True, timeout=3)
        _row('Monitor running', '✓ yes' if r.returncode == 0 else '✗ no')
    except Exception:
        _row('Monitor running', '(check unavailable on this platform)')

    try:
        from calibre.utils.config import JSONConfig
        prefs = JSONConfig('plugins/furigana_ruby')
        cfg_path = prefs.get('monitor_config_path', '')
        _row('Config path',    cfg_path if cfg_path else '(not set)')
        if cfg_path:
            _row('Config exists', str(os.path.isfile(cfg_path)))
    except Exception:
        pass

    # ── Recent Log ────────────────────────────────────────────────
    _h('Recent Log (last 30 lines)')
    try:
        try:
            from calibre_plugins.furigana_ruby.plugin_logger import get_recent_lines
        except ImportError:
            from plugin_logger import get_recent_lines
        recent = get_recent_lines(30)
        lines.append(recent if recent else '  (log is empty)')
    except Exception as e:
        lines.append(f'  (error reading log: {e})')

    lines.append('')
    return '\n'.join(lines)
