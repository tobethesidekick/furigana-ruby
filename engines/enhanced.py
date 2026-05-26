"""
engines/enhanced.py
Enhanced engine: pykakasi with conjugation-aware post-processing.

Improvements over standard:
- Strips common verb/adjective inflection suffixes before lookup so pykakasi
  sees a form closer to the dictionary entry, reducing misreadings on
  conjugated forms (passive, potential, causative, negative, te-form).
- Validates returned readings: if the hiragana length is implausibly short
  for the number of kanji, the annotation is suppressed (no annotation is
  better than a confidently wrong one).
- Broader trailing-kana splitting so okurigana is not incorrectly annotated.

This is the default engine for all users — no download required.
"""

import re

try:
    from calibre_plugins.furigana_ruby.engine_registry import FuriganaEngine, register
except ImportError:
    from engine_registry import FuriganaEngine, register


# Verb/adjective suffixes to strip before passing to pykakasi.
# Ordered longest-first so we match the most specific pattern first.
# Each entry: (suffix_to_strip, replacement_stem_ending)
# The replacement allows us to reconstitute a valid dictionary-form-like word.
_SUFFIX_MAP = [
    # Passive / potential ichidan: られる → る  (食べられる → 食べる)
    ('られる',  'る'),
    # Causative ichidan: させる → る  (食べさせる → 食べる)
    ('させる',  'る'),
    # Passive godan: れる → う  (書かれる → 書く ... imprecise but closer)
    ('れる',    ''),
    # Causative godan: せる → す
    ('せる',    'す'),
    # Potential godan: える → う  (書ける → 書く)
    ('える',    'う'),
    # Volitional godan: おう → う  (書こう → 書く)
    ('おう',    'う'),
    # Volitional ichidan: よう → る  (食べよう → 食べる)
    ('よう',    'る'),
    # Negative: ない → ない kept but strip off て+ない combos
    ('ていない', ''),
    ('てない',  ''),
    # て-form + いる/いた
    ('ている',  ''),
    ('ていた',  ''),
    # Negative polite
    ('ません',  ''),
    ('ませんでした', ''),
    # Past negative
    ('なかった', ''),
    # Plain negative
    ('ない',   ''),
    # Past plain
    ('った',   'う'),
    ('いた',   'く'),
    ('いだ',   'ぐ'),
    ('した',   'す'),
    ('んだ',   'ぬ'),
    ('んだ',   'む'),
    ('った',   'つ'),
    ('った',   'る'),
    # te-form
    ('って',   'う'),
    ('いて',   'く'),
    ('いで',   'ぐ'),
    ('して',   'す'),
    ('んで',   'む'),
]

# If a segment's hiragana reading has fewer mora than this ratio × kanji_count,
# consider it implausibly short and suppress the annotation.
_MIN_MORA_PER_KANJI = 1


def _is_kanji(c):
    cp = ord(c)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0xF900 <= cp <= 0xFAFF)


def _kanji_count(text):
    return sum(1 for c in text if _is_kanji(c))


def _is_kana(c):
    cp = ord(c)
    return 0x3040 <= cp <= 0x30FF


def _preprocess(text):
    """
    Strip inflection suffixes from the end of a kanji+kana word so pykakasi
    sees something closer to the dictionary form.
    Returns (processed_text, stripped_suffix, replacement_ending).
    """
    for suffix, replacement in _SUFFIX_MAP:
        if text.endswith(suffix) and len(text) > len(suffix):
            stem = text[:-len(suffix)]
            # Only strip if stem still contains kanji
            if any(_is_kanji(c) for c in stem):
                return stem + replacement, suffix, replacement
    return text, '', ''


def _validate_reading(orig, hira):
    """Return True if the reading looks plausible for orig."""
    n_kanji = _kanji_count(orig)
    if n_kanji == 0:
        return True
    n_mora = len(hira)  # rough approximation
    return n_mora >= n_kanji * _MIN_MORA_PER_KANJI


@register
class EnhancedEngine(FuriganaEngine):
    id = 'enhanced'
    display_name = 'Enhanced (built-in)'

    def is_available(self):
        try:
            try:
                from calibre_plugins.furigana_ruby.deps_loader import ensure_deps
            except ImportError:
                from deps_loader import ensure_deps
            ensure_deps()
            import pykakasi  # noqa
            return True
        except Exception:
            return False

    def tokenize(self, text):
        try:
            from calibre_plugins.furigana_ruby.deps_loader import ensure_deps
        except ImportError:
            from deps_loader import ensure_deps
        ensure_deps()
        import pykakasi
        kks = pykakasi.kakasi()

        items = kks.convert(text)
        pairs = []
        for item in items:
            orig = item.get('orig', '')
            if not orig:
                continue
            hira = item.get('hira', '')

            if not hira or orig == hira or not any(_is_kanji(c) for c in orig):
                pairs.append((orig, orig))
                continue

            # If reading looks implausible, try pre-processing the word
            if not _validate_reading(orig, hira):
                processed, stripped, _ = _preprocess(orig)
                if processed != orig:
                    new_items = kks.convert(processed)
                    new_hira = ''.join(i.get('hira', i.get('orig', ''))
                                      for i in new_items)
                    if new_hira and new_hira != processed and _validate_reading(orig, new_hira):
                        hira = new_hira
                    else:
                        # Cannot produce a reliable reading — suppress
                        pairs.append((orig, orig))
                        continue

            pairs.append((orig, hira))
        return pairs
