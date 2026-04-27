"""
chinese_engine.py
=================
Simplified ↔ Traditional Chinese conversion for EPUB, HTML, FB2 and TXT books.
Uses opencc-python-reimplemented (pure Python, bundled with the plugin).

Public API
----------
convert_epub_s2t(epub_path, output_path, variant, progress_callback) → (files_done, errors)
convert_html_s2t(html_path, output_path, variant)                    → (1, errors)
convert_fb2_s2t(fb2_path,  output_path, variant)                    → (chars_done, errors)
convert_txt_s2t(txt_path,  output_path, variant)                     → (chars_done, errors)
ensure_opencc()                                                       → bool
"""

import re
import os
import zipfile
import tempfile
import shutil


# ── Supported conversion variants ────────────────────────────────────────────

# Each entry: (opencc_variant, display_label, direction, description)
# direction: 's2t' = Simplified→Traditional, 't2s' = Traditional→Simplified
VARIANTS = [
    # Simplified → Traditional
    ('s2t',   'Generic Traditional (s2t)',
              's2t', 'Basic S→T mapping. Works for any simplified source. Fastest option.'),
    ('s2tw',  'Taiwan Traditional 正體 (s2tw)',
              's2t', 'Taiwan standard character set (正體). Recommended for Taiwan-published ebooks.'),
    ('s2twp', 'Taiwan Traditional 正體 — phrases (s2twp)',
              's2t', 'Taiwan Traditional + phrase-level vocabulary (e.g. 軟件→軟體). More accurate, slower.'),
    ('s2hk',  'Hong Kong Traditional 港式 (s2hk)',
              's2t', 'Hong Kong standard character set (港式繁體). Use for HK-published ebooks.'),
    # Traditional → Simplified (all produce Mainland China GB Simplified)
    ('t2s',   'Generic Simplified (t2s)',
              't2s', 'Basic T→S mapping. Works for any traditional source. Fastest option.'),
    ('tw2s',  'Taiwan Traditional → Simplified (tw2s)',
              't2s', 'Source is Taiwan Traditional (正體). Output is Mainland Simplified.'),
    ('tw2sp', 'Taiwan Traditional → Simplified — phrases (tw2sp)',
              't2s', 'Taiwan Traditional → Simplified + phrase-level vocabulary. More accurate, slower.'),
    ('hk2s',  'Hong Kong Traditional → Simplified (hk2s)',
              't2s', 'Source is Hong Kong Traditional (港式). Output is Mainland Simplified.'),
]

VARIANTS_S2T = [v for v in VARIANTS if v[2] == 's2t']
VARIANTS_T2S = [v for v in VARIANTS if v[2] == 't2s']


# ── OpenCC loader ─────────────────────────────────────────────────────────────

_converters = {}   # variant → opencc.OpenCC instance


def ensure_opencc():
    """Return True if opencc can be imported (loads from bundled deps if needed).

    Fully self-contained — does not rely on deps_loader so it works from any
    import context (including QThread workers).  Handles stale extraction
    caches that pre-date the opencc bundle being added to the zip.
    """
    try:
        import opencc   # noqa
        return True
    except ImportError:
        pass

    import sys as _sys, os as _os, zipfile as _zf
    import tempfile as _tmp, shutil as _sh

    def _find_plugin_zip():
        try:
            from calibre.utils.config import config_dir
            pdir = _os.path.join(config_dir, 'plugins')
            if _os.path.isdir(pdir):
                for fn in sorted(_os.listdir(pdir)):
                    if 'furigana' in fn.lower() and fn.endswith('.zip'):
                        return _os.path.join(pdir, fn)
        except Exception:
            pass
        for p in _sys.path:
            if isinstance(p, str) and p.endswith('.zip') and 'furigana' in p.lower():
                return p
        return None

    def _extract(zip_path, force=False):
        base   = _os.path.join(_tmp.gettempdir(), 'calibre_furigana_deps')
        marker = _os.path.join(base, '.extracted')
        if not force:
            # Cache valid only when: marker matches zip path AND opencc is present
            if _os.path.exists(marker):
                try:
                    with open(marker) as mf:
                        cached_path = mf.read().strip()
                    deps = _os.path.join(base, 'bundled_deps')
                    if (cached_path == zip_path
                            and _os.path.isdir(_os.path.join(deps, 'opencc'))):
                        return deps   # cache is good
                except Exception:
                    pass
            force = True   # missing marker, wrong path, or opencc absent
        try:
            with _zf.ZipFile(zip_path, 'r') as z:
                members = [n for n in z.namelist()
                           if n.startswith('bundled_deps/')]
                if not members:
                    return None
                if _os.path.exists(base):
                    _sh.rmtree(base, ignore_errors=True)
                _os.makedirs(base, exist_ok=True)
                z.extractall(base, members=members)
            with open(marker, 'w') as mf:
                mf.write(zip_path)
        except Exception:
            return None
        deps = _os.path.join(base, 'bundled_deps')
        return deps if _os.path.isdir(deps) else None

    zip_path = _find_plugin_zip()
    if zip_path:
        deps = _extract(zip_path)
        if deps:
            if deps not in _sys.path:
                _sys.path.insert(0, deps)
            try:
                import opencc   # noqa
                return True
            except ImportError:
                pass

    # Dev / test mode: bundled_deps sitting next to this file
    try:
        here    = _os.path.dirname(_os.path.abspath(__file__))
        bundled = _os.path.join(here, 'bundled_deps')
        if _os.path.isdir(bundled):
            if bundled not in _sys.path:
                _sys.path.insert(0, bundled)
            import opencc   # noqa
            return True
    except Exception:
        pass

    return False


def _get_converter(variant='s2tw'):
    """Return a cached opencc.OpenCC instance for the given variant."""
    if variant in _converters:
        return _converters[variant]
    if not ensure_opencc():
        raise ImportError(
            'opencc could not be loaded. '
            'Rebuild the plugin zip with opencc-python-reimplemented bundled '
            '(run setup_plugin.py after: pip3 install opencc-python-reimplemented).'
        )
    import opencc
    cc = opencc.OpenCC(variant)
    _converters[variant] = cc
    return cc


# ── HTML / XML text-node walker ───────────────────────────────────────────────
# Converts only text nodes — never touches tag names, attributes, or CSS/JS.

_SKIP_TAGS = frozenset(['script', 'style'])


def _convert_html_text_nodes(html, converter):
    """
    Walk HTML/XML as a token stream; run converter.convert() on every text
    node outside <script> and <style> blocks.
    """
    parts = re.split(r'(<[^>]+>|<!--.*?-->)', html, flags=re.DOTALL)
    result = []
    skip_depth = 0

    for part in parts:
        if part.startswith('<') or part.startswith('<!--'):
            result.append(part)
            if part.startswith('<!--'):
                continue
            m = re.match(r'<(/?)([A-Za-z][A-Za-z0-9]*)', part)
            if not m:
                continue
            is_closing    = m.group(1) == '/'
            tag           = m.group(2).lower()
            is_selfclosing = (not is_closing) and part.rstrip().endswith('/>')
            if tag in _SKIP_TAGS:
                if is_closing:
                    skip_depth = max(0, skip_depth - 1)
                elif not is_selfclosing:
                    skip_depth += 1
        else:
            if skip_depth == 0 and part:
                part = converter.convert(part)
            result.append(part)

    return ''.join(result)


# ── EPUB processor ────────────────────────────────────────────────────────────

# File types inside the EPUB to convert (text content inside XML/HTML tags)
_CONVERT_EXTENSIONS = {'.xhtml', '.html', '.htm', '.opf', '.ncx', '.xml'}
# File types to leave completely untouched
_SKIP_EXTENSIONS    = {'.css', '.js', '.png', '.jpg', '.jpeg', '.gif',
                       '.svg', '.ttf', '.otf', '.woff', '.woff2', '.mp3',
                       '.mp4', '.smil'}


def convert_epub_s2t(epub_path, output_path, variant='s2tw',
                     progress_callback=None):
    """
    Convert Simplified → Traditional Chinese in an EPUB file.

    Converts text nodes in all HTML, OPF, and NCX files.
    CSS, images, fonts and other binary assets are passed through unchanged.

    progress_callback(current, total, filename)

    Returns (files_converted, errors_list).
    """
    converter = _get_converter(variant)

    tmp = tempfile.mktemp(suffix='.epub')
    shutil.copy2(epub_path, tmp)

    convert_ext = _CONVERT_EXTENSIONS
    files_converted = 0
    errors = []

    with zipfile.ZipFile(tmp, 'r') as zin:
        names    = zin.namelist()
        to_convert = [n for n in names
                      if os.path.splitext(n.lower())[1] in convert_ext]
        total     = len(to_convert)
        processed = 0
        out_tmp   = tempfile.mktemp(suffix='.epub')

        with zipfile.ZipFile(out_tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                data = zin.read(name)
                ext  = os.path.splitext(name.lower())[1]

                if ext in convert_ext:
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total, name)
                    try:
                        text = data.decode('utf-8')
                        text = _convert_html_text_nodes(text, converter)
                        data = text.encode('utf-8')
                        files_converted += 1
                    except Exception as e:
                        errors.append(f'{name}: {e}')

                if name == 'mimetype':
                    zout.writestr(zipfile.ZipInfo('mimetype'), data,
                                  compress_type=zipfile.ZIP_STORED)
                else:
                    zout.writestr(name, data)

    shutil.move(out_tmp, output_path)
    os.unlink(tmp)
    return files_converted, errors


# ── TXT processor ─────────────────────────────────────────────────────────────

def convert_txt_s2t(txt_path, output_path, variant='s2tw'):
    """
    Convert Simplified ↔ Traditional Chinese in a plain-text file.

    Returns (char_count, errors_list).
    """
    converter = _get_converter(variant)
    errors = []
    try:
        # Try common Chinese encodings — many mainland TXT files are GBK/GB18030
        text = None
        for enc in ('utf-8', 'gb18030', 'big5'):
            try:
                with open(txt_path, 'r', encoding=enc, errors='strict') as f:
                    text = f.read()
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if text is None:
            with open(txt_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        converted = converter.convert(text)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(converted)
        return len(text), errors
    except Exception as e:
        return 0, [str(e)]


def convert_string_s2t(text, variant='s2tw'):
    """Convert a plain string from Simplified to Traditional Chinese."""
    return _get_converter(variant).convert(text)


# ── HTML processor ────────────────────────────────────────────────────────────

def convert_html_s2t(html_path, output_path, variant='s2tw'):
    """
    Convert Simplified ↔ Traditional Chinese in a standalone HTML file.

    Uses the same token-walker as the EPUB processor so tags, attributes,
    scripts and styles are left untouched.

    Returns (1, errors_list) on success.
    """
    converter = _get_converter(variant)
    errors = []
    try:
        with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        result = _convert_html_text_nodes(content, converter)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        return 1, errors
    except Exception as e:
        return 0, [str(e)]


# ── FB2 processor ─────────────────────────────────────────────────────────────

def _fb2_encoding(fb2_path):
    """Read the encoding declared in the FB2's XML header, default utf-8."""
    try:
        with open(fb2_path, 'rb') as f:
            header = f.read(200)
        m = re.match(rb"<\?xml[^>]+encoding=[\"']([^\"']+)[\"']", header)
        if m:
            return m.group(1).decode('ascii', errors='ignore').lower()
    except Exception:
        pass
    return 'utf-8'


def convert_fb2_s2t(fb2_path, output_path, variant='s2tw'):
    """
    Convert Simplified ↔ Traditional Chinese in an FB2 (FictionBook2) file.

    FB2 is well-formed XML so the same HTML token-walker handles it correctly —
    element tags, XML declarations and attributes are left untouched; only
    text nodes are converted.  The original file encoding is preserved.

    Returns (char_count, errors_list).
    """
    converter = _get_converter(variant)
    errors = []
    try:
        encoding = _fb2_encoding(fb2_path)
        with open(fb2_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
        result = _convert_html_text_nodes(content, converter)
        with open(output_path, 'w', encoding=encoding) as f:
            f.write(result)
        return len(content), errors
    except Exception as e:
        return 0, [str(e)]
