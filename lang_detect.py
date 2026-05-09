"""
lang_detect.py
==============
Book-level and document-level CJK language detection for EPUBs.

Public API
----------
detect_book_language(epub_path)       → lang_info dict
detect_script_from_text(text)         → 'simplified' | 'traditional' | 'unknown'
detect_script_from_epub(epub_path)    → 'simplified' | 'traditional' | 'unknown'
should_skip_html_for_ruby(html)       → bool
lang_display(lang_info)               → human-readable string
"""

import re
import zipfile


# ── Script detection character sets ──────────────────────────────────────────
#
# Characters that appear ONLY in simplified Chinese text (never in traditional).
# Each char here has a distinct Traditional counterpart in _TRAD_ONLY (same order).
_SIMP_ONLY = frozenset(
    # Core set (high-frequency function words and common characters)
    '来时这说话见开个们样过还给让头实国为会对无电动长门问学关岁'
    '虽双点办欢间请谢边发书读语东从种车务经认义属专历总别处达'
    # Extended — very common in Chinese fiction titles and author names
    '爱梦旧戏变谁万娇忆惊泪静战亲缘传续归宠凤网龙飞华丽恋'
    '灵剑风怀兴环执获纪协换该讨损购护积众齐继严坏态农沧尝试'
    '维师温残厌轻权伤难强现际级终绝阳阴带统观报图标选编产线联'
    '听营业侦笔记韵哑饱浓鱼丧苍贫暧苏闲两镖词蓝鸡萝临阵乱弃随陆决'
    '妆犹裤猫兰桥马号结场尽纯团诗红许闪机饼败误须陈济废铁刚儿骄瑶钟晓腻错'
    '称职调当灯气娱乐钰颠镜恶闻敌纠绮顾跃笼蛊钱离异录与户圣殒谐鸦潜麦秽袜'
)
# Their traditional-script counterparts (never appear in simplified).
_TRAD_ONLY = frozenset(
    # Core set
    '來時這說話見開個們樣過還給讓頭實國為會對無電動長門問學關歲'
    '雖雙點辦歡間請謝邊發書讀語東從種車務經認義屬專歷總別處達'
    # Extended — very common in Chinese fiction titles and author names
    '愛夢舊戲變誰萬嬌憶驚淚靜戰親緣傳續歸寵鳳網龍飛華麗戀'
    '靈劍風懷興環執獲紀協換該討損購護積眾齊繼嚴壞態農滄嘗試'
    '維師溫殘厭輕權傷難強現際級終絕陽陰帶統觀報圖標選編產線聯'
    '聽營業偵筆記韻啞飽濃魚喪蒼貧曖蘇閒兩鏢詞藍雞蘿臨陣亂棄隨陸決'
    '妝猶褲貓蘭橋馬號結場盡純團詩紅許閃機餅敗誤須陳濟廢鐵剛兒驕瑤鍾曉膩錯'
    '稱職調當燈氣娛樂鈺顛鏡惡聞敵糾綺顧躍籠蠱錢離異錄與戶聖殞諧鴉潛麥穢襪'
)


def detect_script_from_text(text):
    """
    Count simplified-only vs traditional-only characters in *text*.

    Returns 'simplified', 'traditional', or 'unknown' when inconclusive
    (fewer than 10 discriminating characters found, or ratio < 2:1).
    """
    simp = sum(1 for c in text if c in _SIMP_ONLY)
    trad = sum(1 for c in text if c in _TRAD_ONLY)
    total = simp + trad
    if total < 10:
        return 'unknown'
    if simp >= trad * 2:
        return 'simplified'
    if trad >= simp * 2:
        return 'traditional'
    return 'unknown'


def detect_script_short(text):
    """Script detection for short strings (title, author) — works with even 1 character.

    Unlike detect_script_from_text, uses no minimum threshold so short titles
    are not returned as 'unknown' just because there aren't enough characters.
    Returns 'simplified', 'traditional', or 'unknown' (tie or no CJK found).
    """
    simp = sum(1 for c in text if c in _SIMP_ONLY)
    trad = sum(1 for c in text if c in _TRAD_ONLY)
    if trad > simp:
        return 'traditional'
    if simp > trad:
        return 'simplified'
    return 'unknown'


def detect_script_from_epub(epub_path, max_chars=6000):
    """
    Sample up to three content HTML files from the EPUB to detect script.
    Returns 'simplified', 'traditional', or 'unknown'.
    """
    try:
        with zipfile.ZipFile(epub_path, 'r') as zf:
            names = zf.namelist()
            content_files = [
                n for n in names
                if n.lower().endswith(('.html', '.xhtml', '.htm'))
                and not any(skip in n.lower() for skip in ('nav', 'toc', 'cover'))
            ]
            sampled = ''
            for name in content_files[:5]:
                try:
                    raw = zf.read(name).decode('utf-8', errors='ignore')
                    text = re.sub(r'<[^>]+>', '', raw)
                    sampled += text[:max_chars // 3]
                    if len(sampled) >= max_chars:
                        break
                except Exception:
                    continue
            if sampled:
                return detect_script_from_text(sampled)
    except Exception:
        pass
    return 'unknown'


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
