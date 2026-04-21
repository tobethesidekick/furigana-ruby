"""
viewer_plugin.py
Calibre viewer plugin — injects CSS+JS into every page.

Calibre 9 uses a viewer plugin system where plugins register
a javascript() method that returns JS to inject.
"""

import os

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def _read(fname):
    path = os.path.join(PLUGIN_DIR, fname)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ''


def javascript():
    """
    Called by Calibre viewer for each page load.
    Returns JS string to inject (CSS is injected via JS here for reliability).
    """
    return _read('viewer_inject.js')


def stylesheet():
    """
    Called by some Calibre viewer versions for CSS injection.
    """
    return _read('viewer_inject.css')
