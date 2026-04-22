"""
orientation_engine.py
Converts EPUB books between vertical-rl (traditional CJK) and
horizontal-tb text layout.

Handles:
  - CSS writing-mode declarations (with -webkit- and -epub- vendor prefixes)
  - OPF spine page-progression-direction
  - Inline style= attributes in HTML files
  - Tate-chu-yoko (text-combine-upright) for digits and short Latin runs
  - CJK corner-bracket substitution for Western curly quotes
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


# ── Tate-chu-yoko CSS ────────────────────────────────────────────────────────

_TCY_CSS_MARKER = 'Tate-chu-yoko — added by Furigana Ruby Plugin'

_TCY_CSS_BLOCK = (
    '\n/* Tate-chu-yoko — added by Furigana Ruby Plugin */\n'
    '.tcy {\n'
    '    text-combine-upright: all;\n'
    '    -webkit-text-combine: horizontal;\n'
    '    -ms-text-combine-horizontal: all;\n'
    '}\n'
)


def _css_add_tcy(css):
    """Append TCY CSS block once if not already present."""
    if _TCY_CSS_MARKER in css:
        return css
    return css + _TCY_CSS_BLOCK


def _css_remove_tcy(css):
    """Remove the TCY CSS block injected by this plugin."""
    return re.sub(
        r'/\*\s*Tate-chu-yoko[^*]*\*/\s*\.tcy\s*\{[^}]*\}\s*',
        '', css, flags=re.DOTALL)


# ── HTML text-node processor ──────────────────────────────────────────────────

# Tags whose text content must NOT be processed (layout/code/math/our own spans)
_TEXT_SKIP_TAGS = frozenset([
    'ruby', 'rt', 'rp',
    'pre', 'code',
    'script', 'style',
    'head', 'title',
    'math', 'svg',
])


def _process_html_text_nodes(html, text_fn):
    """
    Apply text_fn to every text node in an HTML document.

    Skips text inside <ruby>, <rt>, <rp>, <pre>, <code>, <script>,
    <style>, <head>, <math>, <svg>, and <span class="tcy"> so we never
    double-wrap or corrupt markup.

    text_fn(str) -> str
    """
    # Split into alternating [text, tag/comment, text, tag/comment, …]
    parts = re.split(r'(<[^>]+>|<!--.*?-->)', html, flags=re.DOTALL)

    result         = []
    skip_depth     = 0   # depth inside _TEXT_SKIP_TAGS  (script/style/ruby/…)
    tcy_span_depth = 0   # depth inside <span class="tcy"> — tracked separately
                         # because closing </span> has no class attribute to
                         # identify it, so it cannot use the same gate as opening

    for part in parts:
        if part.startswith('<') or part.startswith('<!--'):
            result.append(part)
            if part.startswith('<!--'):
                continue

            tag_m = re.match(r'<(/?)([A-Za-z][A-Za-z0-9]*)', part)
            if not tag_m:
                continue

            is_closing     = tag_m.group(1) == '/'
            tag_name       = tag_m.group(2).lower()
            is_selfclosing = (not is_closing) and part.rstrip().endswith('/>')

            # ── tcy span depth (open detected by class attr; close by tag name)
            if tag_name == 'span':
                if not is_closing and not is_selfclosing:
                    # Opening <span> — is it a tcy span?
                    if re.search(r'\bclass=["\'][^"\']*\btcy\b', part):
                        tcy_span_depth += 1
                elif is_closing and tcy_span_depth > 0:
                    # Any closing </span> closes the innermost tracked tcy span
                    tcy_span_depth -= 1

            # ── regular skip-tag depth (script / style / ruby / pre / …)
            if tag_name in _TEXT_SKIP_TAGS:
                if is_closing:
                    skip_depth = max(0, skip_depth - 1)
                elif not is_selfclosing:
                    skip_depth += 1

        else:
            # Text node — only transform when outside ALL skip zones
            if skip_depth == 0 and tcy_span_depth == 0:
                part = text_fn(part)
            result.append(part)

    return ''.join(result)


# ── Tate-chu-yoko span wrapping ───────────────────────────────────────────────

# Matches (all anchored to NOT be part of a longer run):
#   • 1–4 consecutive digits, optionally followed by .digits (e.g. 2.0, 3.14)
#     — covers single chapter numbers (第1章), years (2024), decimals (2.0)
#   • 1–8 char Latin-led sequences (USB, iPhone, mvp, A)
_TCY_RE = re.compile(r'\d{1,4}(?:\.\d{1,4})?|[A-Za-z][A-Za-z0-9]{0,7}')


def _html_wrap_tcy(html):
    """
    Wrap digit runs and short Latin sequences in <span class="tcy"> so
    they render upright (tate-chu-yoko) inside a vertical text column.
    Skips text inside ruby/pre/code/script/style/head and existing .tcy spans.
    """
    def _wrap(text):
        return _TCY_RE.sub(r'<span class="tcy">\g<0></span>', text)
    return _process_html_text_nodes(html, _wrap)


def _html_unwrap_tcy(html):
    """Remove all <span class="tcy">…</span> spans added by this plugin."""
    return re.sub(
        r'<span\s+class=["\']tcy["\']>(.*?)</span>',
        r'\1', html, flags=re.DOTALL)


# ── Punctuation substitution ──────────────────────────────────────────────────

# Western curly quotes → CJK corner brackets (H→V direction)
# Reversed automatically for V→H.
_PUNCT_TO_VERTICAL = [
    ('\u201C', '\u300C'),  # " → 「
    ('\u201D', '\u300D'),  # " → 」
    ('\u2018', '\u300E'),  # ' → 『
    ('\u2019', '\u300F'),  # ' → 』
]
# Period substitution is one-way only — we never reverse 。→. because the
# original book may already have 。 that we must not corrupt on V→H.
_PUNCT_TO_HORIZONTAL = [(v, h) for h, v in _PUNCT_TO_VERTICAL]

# ASCII period NOT flanked by two Latin letters (exclude abbreviations like e.g.)
_BARE_PERIOD_RE = re.compile(r'(?<![A-Za-z])\.(?![A-Za-z])')

# Tab / multi-whitespace normaliser: in vertical text there are no tab stops,
# so \t creates an ugly vertical gap; collapse to a single ideographic space.
_TAB_RE = re.compile(r'\t+')


def _html_punct_to_vertical(html):
    """
    In text nodes:
      • Replace Western curly quotes with CJK corner brackets
      • Replace bare ASCII period (.) with ideographic full stop (。)
        — except when sandwiched between two Latin letters (abbreviations)
        — decimal periods inside TCY spans are already protected
      • Normalise tab characters to a single ideographic space (U+3000)
    """
    def _subst(text):
        for src, dst in _PUNCT_TO_VERTICAL:
            text = text.replace(src, dst)
        text = _BARE_PERIOD_RE.sub('\u3002', text)   # . → 。
        text = _TAB_RE.sub('\u3000', text)            # \t →
        return text
    return _process_html_text_nodes(html, _subst)


def _html_punct_to_horizontal(html):
    """
    Reverse CJK corner brackets back to Western curly quotes in text nodes.
    Undoes the quote part of _html_punct_to_vertical so round-trips are lossless.
    (Period and tab normalisation are intentionally not reversed.)
    """
    def _subst(text):
        for src, dst in _PUNCT_TO_HORIZONTAL:
            text = text.replace(src, dst)
        return text
    return _process_html_text_nodes(html, _subst)


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

    css_changed      = 0
    html_changed     = 0
    opf_changed      = False
    errors           = []
    tcy_css_injected = False   # inject TCY CSS into the first modified CSS file only

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
                            if target == 'horizontal':
                                new_css = _css_to_horizontal(css)
                                new_css = _css_remove_tcy(new_css)
                            else:
                                new_css = _css_to_vertical(css)
                                # Inject TCY CSS into the first CSS file we touch
                                if not tcy_css_injected:
                                    new_css = _css_add_tcy(new_css)
                                    tcy_css_injected = True
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
                            if target == 'horizontal':
                                new_html = _html_inline_to_horizontal(html)
                                new_html = _html_unwrap_tcy(new_html)
                                new_html = _html_punct_to_horizontal(new_html)
                            else:
                                new_html = _html_inline_to_vertical(html)
                                new_html = _html_wrap_tcy(new_html)
                                new_html = _html_punct_to_vertical(new_html)
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
