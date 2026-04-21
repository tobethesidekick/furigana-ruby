"""
orientation_engine.py
Converts EPUB books between vertical-rl (traditional CJK) and
horizontal-tb text layout.

Handles:
  - CSS writing-mode declarations (with -webkit- and -epub- vendor prefixes)
  - OPF spine page-progression-direction
  - Inline style= attributes in HTML files
  - Detection of current orientation from OPF / CSS

No extra dependencies beyond Python stdlib.
"""

import re
import zipfile
import os
import tempfile
import shutil


# ── OPF / container helpers ───────────────────────────────────────────────────

def _find_opf_path(zf):
    """Locate the OPF package document inside the EPUB zip."""
    try:
        container = zf.read('META-INF/container.xml').decode('utf-8', errors='ignore')
        m = re.search(r'full-path\s*=\s*["\']([^"\']+\.opf)["\']', container, re.I)
        if m:
            return m.group(1)
    except Exception:
        pass
    # Fallback: scan for any .opf file
    for name in zf.namelist():
        if name.lower().endswith('.opf'):
            return name
    return None


# ── Orientation detection ─────────────────────────────────────────────────────

def detect_orientation(epub_path):
    """
    Detect the dominant text orientation of an EPUB.

    Returns 'vertical' or 'horizontal'.

    Check order (CSS first — OPF is checked second because many Japanese
    publishers incorrectly write page-progression-direction="ltr" even in
    vertical EPUBs, which would cause a false horizontal result):

      1. CSS files — writing-mode declarations are authoritative for rendering
      2. OPF spine page-progression-direction (RTL = vertical confirmation)
      3. OPF metadata primary-writing-mode hint
    """
    try:
        with zipfile.ZipFile(epub_path, 'r') as zf:

            names = zf.namelist()

            # 1. Scan CSS files — matches unprefixed, -webkit-, and -epub- variants,
            #    plus the old CSS2 tb-rl / tb-lr syntax used in older Japanese EPUBs.
            #    NOTE: \b word-boundary cannot precede '-webkit-', so we match the
            #    optional vendor prefix explicitly instead.
            _wm_re = re.compile(
                r'(?:-webkit-|-epub-)?writing-mode\s*:\s*'
                r'(?:vertical-(?:rl|lr)|tb-rl|tb-lr)',
                re.I)
            for name in names:
                if name.lower().endswith('.css'):
                    try:
                        css = zf.read(name).decode('utf-8', errors='ignore')
                        if _wm_re.search(css):
                            return 'vertical'
                    except Exception:
                        pass

            # 2. Scan embedded <style> blocks in the first 10 HTML files.
            #    Some EPUBs inline all their CSS rather than using .css files.
            html_names = [n for n in names
                          if n.lower().endswith(('.xhtml', '.html', '.htm'))]
            for name in html_names[:10]:
                try:
                    content = zf.read(name).decode('utf-8', errors='ignore')
                    for sm in re.finditer(
                            r'<style\b[^>]*>(.*?)</style>', content,
                            re.DOTALL | re.I):
                        if _wm_re.search(sm.group(1)):
                            return 'vertical'
                except Exception:
                    pass

            # 3. OPF primary-writing-mode metadata (EPUB3 standard signal).
            #    page-progression-direction="rtl" is NOT used here because it
            #    only means pages turn right-to-left — all Japanese books use it,
            #    horizontal and vertical alike.
            opf_path = _find_opf_path(zf)
            if opf_path:
                opf = zf.read(opf_path).decode('utf-8', errors='ignore')
                if re.search(
                        r'primary-writing-mode[^<]*vertical', opf, re.I):
                    return 'vertical'

    except Exception:
        pass

    return 'horizontal'  # safe default — most EPUBs are horizontal


# ── CSS transformations ───────────────────────────────────────────────────────

def _css_to_horizontal(css):
    """
    Convert a CSS string from vertical to horizontal layout.
    - Removes -webkit- / -epub- prefixed vertical writing-mode declarations.
    - Replaces unprefixed vertical writing-mode with horizontal-tb.
    - Removes text-orientation (only meaningful in vertical context).
    """
    # Remove vendor-prefixed vertical writing-mode
    css = re.sub(
        r'-(?:webkit|epub)-writing-mode\s*:\s*vertical-(?:rl|lr)\s*;?',
        '', css, flags=re.I)
    # Replace standard vertical writing-mode
    css = re.sub(
        r'\bwriting-mode\s*:\s*vertical-(?:rl|lr)\s*;?',
        'writing-mode: horizontal-tb;', css, flags=re.I)
    # Remove text-orientation property
    css = re.sub(
        r'\btext-orientation\s*:\s*[\w-]+\s*;?',
        '', css, flags=re.I)
    return css


def _css_to_vertical(css):
    """
    Convert a CSS string from horizontal to vertical layout.
    - Replaces horizontal-tb writing-mode with vertical-rl + vendor prefixes.
    - If no writing-mode is found, injects one into the body/html rule or
      appends a new rule at the end.
    """
    if re.search(r'\bwriting-mode\s*:\s*horizontal-tb', css, re.I):
        # Replace vendor-prefixed horizontal
        css = re.sub(
            r'-(?:webkit|epub)-writing-mode\s*:\s*horizontal-tb\s*;?',
            '', css, flags=re.I)
        # Replace standard horizontal with vertical + re-add vendor prefixes
        css = re.sub(
            r'\bwriting-mode\s*:\s*horizontal-tb\s*;?',
            ('writing-mode: vertical-rl;\n'
             '    -webkit-writing-mode: vertical-rl;\n'
             '    -epub-writing-mode: vertical-rl;'),
            css, flags=re.I)
    else:
        css = _inject_vertical_into_body(css)
    return css


def _inject_vertical_into_body(css):
    """
    Add writing-mode: vertical-rl to an existing body/html rule, or append
    a new rule if neither exists.  Used when converting a horizontal EPUB
    whose CSS has no writing-mode declaration at all.
    """
    _INJECT = (
        '\n    writing-mode: vertical-rl;'
        '\n    -webkit-writing-mode: vertical-rl;'
        '\n    -epub-writing-mode: vertical-rl;'
    )

    # Try body rule first (may optionally be preceded by "html, ")
    body_re = re.compile(
        r'((?:html\s*,\s*)?body\s*\{)([^}]*?)(\})',
        re.DOTALL | re.IGNORECASE)
    html_re = re.compile(
        r'(html\s*\{)([^}]*?)(\})',
        re.DOTALL | re.IGNORECASE)

    if body_re.search(css):
        return body_re.sub(
            lambda m: m.group(1) + m.group(2) + _INJECT + '\n' + m.group(3),
            css, count=1)
    if html_re.search(css):
        return html_re.sub(
            lambda m: m.group(1) + m.group(2) + _INJECT + '\n' + m.group(3),
            css, count=1)

    # No suitable rule found — append a new one
    css += (
        '\n\n/* Orientation: vertical-rl — added by Furigana Ruby Plugin */\n'
        'html, body {\n'
        '    writing-mode: vertical-rl;\n'
        '    -webkit-writing-mode: vertical-rl;\n'
        '    -epub-writing-mode: vertical-rl;\n'
        '}\n'
    )
    return css


# ── OPF transformations ───────────────────────────────────────────────────────

def _opf_to_horizontal(opf):
    """Set page-progression-direction to ltr and clean up vertical metadata."""
    # spine: rtl → ltr
    opf = re.sub(
        r'(page-progression-direction\s*=\s*["\'])rtl(["\'])',
        r'\1ltr\2', opf, flags=re.I)
    # Remove primary-writing-mode vertical hint (EPUB3 metadata)
    opf = re.sub(
        r'<meta\b[^>]*primary-writing-mode[^>]*vertical[^>]*/?>',
        '', opf, flags=re.I | re.DOTALL)
    return opf


def _opf_to_vertical(opf):
    """Set page-progression-direction to rtl, adding the attribute if absent."""
    if re.search(r'page-progression-direction\s*=\s*["\']ltr["\']', opf, re.I):
        opf = re.sub(
            r'(page-progression-direction\s*=\s*["\'])ltr(["\'])',
            r'\1rtl\2', opf, flags=re.I)
    elif '<spine' in opf and 'page-progression-direction' not in opf:
        opf = re.sub(
            r'(<spine\b)([^>]*>)',
            r'\1 page-progression-direction="rtl"\2',
            opf, count=1)
    return opf


# ── Embedded furigana-ruby-css button position ───────────────────────────────

def _update_ruby_css_btn_position(html, target):
    """
    When an EPUB's orientation is converted, flip the #fg-btn left/right value
    inside the embedded <style id="furigana-ruby-css"> tag so the toggle appears
    on the correct side without requiring JS runtime detection.

    Only modifies HTML files that already contain our injected CSS — a no-op on
    all other files.
    """
    if 'id="furigana-ruby-css"' not in html:
        return html

    _style_re = re.compile(
        r'(<style\b[^>]*id=["\']furigana-ruby-css["\'][^>]*>)(.*?)(</style>)',
        re.DOTALL
    )

    def _flip(m):
        css = m.group(2)
        if target == 'horizontal':
            css = re.sub(r'\bleft\s*:\s*8px\s*;', 'right: 8px;', css)
        else:
            css = re.sub(r'\bright\s*:\s*8px\s*;', 'left: 8px;', css)
        return m.group(1) + css + m.group(3)

    return _style_re.sub(_flip, html)


# ── Inline-style transformations (HTML) ──────────────────────────────────────

def _html_inline_to_horizontal(html):
    """Strip/replace vertical writing-mode in inline style= attributes."""
    # Remove vendor-prefixed vertical
    html = re.sub(
        r'-(?:webkit|epub)-writing-mode\s*:\s*vertical-(?:rl|lr)\s*;?\s*',
        '', html, flags=re.I)
    # Replace standard vertical with horizontal
    html = re.sub(
        r'\bwriting-mode\s*:\s*vertical-(?:rl|lr)\s*;?',
        'writing-mode: horizontal-tb;', html, flags=re.I)
    return html


def _html_inline_to_vertical(html):
    """Replace horizontal writing-mode in inline style= attributes."""
    html = re.sub(
        r'-(?:webkit|epub)-writing-mode\s*:\s*horizontal-tb\s*;?',
        '-webkit-writing-mode: vertical-rl; -epub-writing-mode: vertical-rl;',
        html, flags=re.I)
    html = re.sub(
        r'\bwriting-mode\s*:\s*horizontal-tb\s*;?',
        'writing-mode: vertical-rl;', html, flags=re.I)
    return html


# ── EPUB processor ────────────────────────────────────────────────────────────

def process_epub_orientation(epub_path, output_path, target,
                             progress_callback=None):
    """
    Convert an EPUB's text orientation.

    Parameters
    ----------
    epub_path : str
        Path to the source EPUB.
    output_path : str
        Path where the converted EPUB will be written.
    target : str
        'horizontal' or 'vertical'.
    progress_callback : callable(current, total, filename), optional

    Returns
    -------
    (css_changed, html_changed, opf_changed, errors)
        css_changed  — number of CSS files modified
        html_changed — number of HTML files with inline-style changes
        opf_changed  — True if the OPF was modified
        errors       — list of (filename, error_message) tuples
    """
    if target not in ('horizontal', 'vertical'):
        raise ValueError(
            f"target must be 'horizontal' or 'vertical', got {target!r}")

    tmp = tempfile.mktemp(suffix='.epub')
    shutil.copy2(epub_path, tmp)

    css_changed  = 0
    html_changed = 0
    opf_changed  = False
    errors       = []

    try:
        with zipfile.ZipFile(tmp, 'r') as zin:
            names    = zin.namelist()
            opf_path = _find_opf_path(zin)

            # Files we actively process (for progress reporting)
            work_files = [n for n in names if (
                n.lower().endswith('.css') or
                n.lower().endswith(('.xhtml', '.html', '.htm')) or
                n == opf_path
            )]
            total     = max(len(work_files), 1)
            processed = 0
            out_tmp   = tempfile.mktemp(suffix='.epub')

            with zipfile.ZipFile(out_tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
                for name in names:
                    data = zin.read(name)

                    # ── CSS files ──────────────────────────────────────
                    if name.lower().endswith('.css'):
                        processed += 1
                        if progress_callback:
                            progress_callback(processed, total, name)
                        try:
                            css = data.decode('utf-8')
                            new_css = (_css_to_horizontal(css)
                                       if target == 'horizontal'
                                       else _css_to_vertical(css))
                            if new_css != css:
                                css_changed += 1
                            data = new_css.encode('utf-8')
                        except Exception as e:
                            errors.append((name, str(e)))

                    # ── HTML / XHTML files ─────────────────────────────
                    elif name.lower().endswith(('.xhtml', '.html', '.htm')):
                        processed += 1
                        if progress_callback:
                            progress_callback(processed, total, name)
                        try:
                            html = data.decode('utf-8')
                            new_html = (_html_inline_to_horizontal(html)
                                        if target == 'horizontal'
                                        else _html_inline_to_vertical(html))
                            # Flip the embedded toggle button position to match new layout
                            new_html = _update_ruby_css_btn_position(new_html, target)
                            if new_html != html:
                                html_changed += 1
                            data = new_html.encode('utf-8')
                        except Exception as e:
                            errors.append((name, str(e)))

                    # ── OPF file ───────────────────────────────────────
                    elif name == opf_path:
                        processed += 1
                        if progress_callback:
                            progress_callback(processed, total, name)
                        try:
                            opf = data.decode('utf-8')
                            new_opf = (_opf_to_horizontal(opf)
                                       if target == 'horizontal'
                                       else _opf_to_vertical(opf))
                            if new_opf != opf:
                                opf_changed = True
                            data = new_opf.encode('utf-8')
                        except Exception as e:
                            errors.append((name, str(e)))

                    # mimetype must be stored uncompressed
                    if name == 'mimetype':
                        zout.writestr(
                            zipfile.ZipInfo('mimetype'), data,
                            compress_type=zipfile.ZIP_STORED)
                    else:
                        zout.writestr(name, data)

        shutil.move(out_tmp, output_path)

    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

    return css_changed, html_changed, opf_changed, errors
