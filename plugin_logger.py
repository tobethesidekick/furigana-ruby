"""
plugin_logger.py — rolling log file for the FuriganaRuby plugin.

Writes to furigana_ruby_log.txt in Calibre's config directory.
Keeps the last MAX_LINES lines; silently rotates when the file exceeds that.
Thread-safe. Never raises — logging must never crash the plugin.

Usage:
    from plugin_logger import logger
    logger.info('Processing book 42')
    logger.warn('Sudachi unavailable, falling back')
    logger.error('Failed to save EPUB: permission denied')
"""

import os
import sys
import threading
import datetime

MAX_LINES = 500
_LOG_FILENAME = 'furigana_ruby_log.txt'

_lock      = threading.Lock()
_path      = None   # resolved on first write


def _resolve_path():
    global _path
    if _path:
        return _path
    try:
        from calibre.utils.config import config_dir
        _path = os.path.join(config_dir, _LOG_FILENAME)
    except Exception:
        # Outside Calibre (unit tests, standalone scripts)
        _path = os.path.join(os.path.expanduser('~'), _LOG_FILENAME)
    return _path


def get_log_path():
    """Return the full path to the log file (creates parents if needed)."""
    return _resolve_path()


def _write(level, message):
    ts   = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] [{level:<5}] {message}\n'
    path = _resolve_path()
    with _lock:
        try:
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
            else:
                lines = []
            lines.append(line)
            if len(lines) > MAX_LINES:
                lines = lines[-MAX_LINES:]
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except Exception:
            pass   # silent — logging must never crash the plugin


def get_recent_lines(n=30):
    """Return the last n log lines as a plain string (for diagnostic report)."""
    path = _resolve_path()
    try:
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            return ''.join(lines[-n:]).rstrip()
    except Exception:
        pass
    return '(log unavailable)'


class _Logger:
    """Thin wrapper so callers can do `logger.info(...)` etc."""
    def info(self, msg):  _write('INFO',  msg)
    def warn(self, msg):  _write('WARN',  msg)
    def error(self, msg): _write('ERROR', msg)
    def debug(self, msg): _write('DEBUG', msg)


logger = _Logger()
