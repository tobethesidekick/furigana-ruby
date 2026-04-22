"""
lang_detect.py
==============
Book-level and document-level CJK language detection for EPUBs.

Public API
----------
detect_book_language(epub_path)       → lang_info dict
should_skip_html_for_ruby(html)       → bool
lang_display(lang_info)               → human-readable string
"""

import re
import zipfile


# ── Internal helpers ──────────────────────────────────────────────────────────

def _classify(tag):
    """
    Classify a BCP-47 language tag into a simple dict.

    Returns:
        lang_raw       : original tag string (lowercased)
        is_japanese    : True for ja / ja-JP / jpn
        is_chinese     : True for zh-* / zho
        is_korean      : True for ko / ko-KR / kor
        is_simplified  : True for zh-Hans, zh-CN, zh-SG
        is_traditional : True for zh-Hant, zh-TW, zh-HK, zh-MO
                         (only meaningful when is_chinese is True)
    """
    result = {
        'lang_raw':       '',
        'is_japanese':    False,
        'is_chinese':     False,
        'is_korean':      False,
        'is_simplified':  False,
        'is_traditional': False,
    }

    if not tag:
        return result

    t = tag.lower().strip()
    result['lang_raw'] = t

    if t.startswith('ja') or t == 'jpn':
        result['is_japanese'] = True

    elif t.startswith('ko') or t == 'kor':
        result['is_korean'] = True

    elif t.startswith('zh') or t == 'zho':
        result['is_chinese'] = True
        if any(sub in t for sub in ('hans', '-cn', '-sg')):
            result['is_simplified'] = True
        elif any(sub in t for sub in ('hant', '-tw', '-hk', '-mo')):
            result['is_traditional'] = True
        # bare 'zh' or 'zho': variant unknown, leave both False

    return result


def _unknown():
    return _classify('')


# ── OPF parsing ───────────────────────────────────────────────────────────────

def _find_opf_path(zf):
    """Return the archive path to the OPF file inside an open ZipFile."""
    # EPUB 2/3: META-INF/container.xml points to the OPF
    try:
        container = zf.read('META-INF/container.xml').decode('utf-8', errors='ignore')
        m = re.search(r'full-path=["\']([^"\']+\.opf)["\']', container, re.I)
        if m:
            return m.group(1)
    except Exception:
        pass
    # Fall back: first .opf file in the archive
    for name in zf.namelist():
        if name.lower().endswith('.opf'):
            return name
    return None


def _opf_language(zf, opf_path):
    """Return the primary language tag from an OPF file, or ''."""
    try:
        opf = zf.read(opf_path).decode('utf-8', errors='ignore')
    except Exception:
        return ''

    # 1. <dc:language>tag</dc:language>
    m = re.search(r'<dc:language[^>]*>\s*([^<\s]+)', opf, re.I)
    if m:
        return m.group(1).strip()

    # 2. xml:lang on <package …>
    m = re.search(r'<package\b[^>]+\bxml:lang=["\']([^"\']+)["\']', opf, re.I)
    if m:
        return m.group(1).strip()

    return ''


# ── HTML document language ────────────────────────────────────────────────────

# Only look in the first 2 KB — the <html> open tag is always near the top.
_HTML_LANG_RE = re.compile(r'<html\b[^>]+\blang=["\']([^"\']+)["\']', re.I)


def get_html_file_lang(html_content):
    """
    Extract the lang attribute from the root <html> element.
    Returns the raw tag string, or '' if not present.
    """
    m = _HTML_LANG_RE.search(html_content[:2000])
    return m.group(1).strip() if m else ''


# ── Public API ────────────────────────────────────────────────────────────────

def detect_book_language(epub_path):
    """
    Detect the primary language of an EPUB from its OPF metadata.

    Returns a dict (same shape as _classify):
        lang_raw, is_japanese, is_chinese, is_korean,
        is_simplified, is_traditional

    Returns _unknown() (all False, lang_raw='') if detection fails.
    """
    try:
        with zipfile.ZipFile(epub_path, 'r') as zf:
            opf_path = _find_opf_path(zf)
            if not opf_path:
                return _unknown()
            tag = _opf_language(zf, opf_path)
            return _classify(tag)
    except Exception:
        return _unknown()


def should_skip_html_for_ruby(html_content):
    """
    Return True if this individual HTML file should be skipped during
    ruby annotation, based on its own <html lang="..."> declaration.

    A file is skipped when it explicitly declares a non-Japanese CJK
    language (Chinese or Korean), even inside an otherwise Japanese book.
    Files with no lang attribute, or with lang="ja*" / lang="en*" etc.,
    return False (process normally).
    """
    file_lang_tag = get_html_file_lang(html_content)
    if not file_lang_tag:
        return False          # no per-file override — inherit book default

    file_lang = _classify(file_lang_tag)
    return file_lang['is_chinese'] or file_lang['is_korean']


def lang_display(lang_info):
    """Return a short human-readable language label for UI display."""
    if lang_info['is_japanese']:
        return 'Japanese (日本語)'
    if lang_info['is_chinese']:
        if lang_info['is_simplified']:
            return 'Chinese — Simplified (简体中文)'
        if lang_info['is_traditional']:
            return 'Chinese — Traditional (繁體中文)'
        return 'Chinese (中文)'
    if lang_info['is_korean']:
        return 'Korean (한국어)'
    raw = lang_info.get('lang_raw', '')
    return raw if raw else 'Unknown / not specified'
