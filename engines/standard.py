"""
engines/standard.py
Standard engine: raw pykakasi. Fallback of last resort — not user-facing.
"""

try:
    from calibre_plugins.furigana_ruby.engine_registry import FuriganaEngine, register
except ImportError:
    from engine_registry import FuriganaEngine, register


@register
class StandardEngine(FuriganaEngine):
    id = 'standard'
    display_name = 'Standard (pykakasi)'

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
            pairs.append((orig, hira if hira else orig))
        return pairs
