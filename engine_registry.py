"""
engine_registry.py
Pluggable furigana engine interface, registry, and fallback chain.

Adding a new engine:
  1. Create a class that subclasses FuriganaEngine and implements tokenize()
  2. Decorate with @register
  3. Import it in engines/__init__.py

The fallback chain is: high_accuracy → enhanced → standard
"""


class FuriganaEngine:
    id = ''
    display_name = ''

    def is_available(self):
        return False

    def tokenize(self, text):
        """
        Tokenize text and return readings for kanji-containing segments.

        Returns a list of (orig, hiragana) pairs covering the full input text.
        Segments without kanji should still be included as (text, '') so the
        caller can reconstruct the original text.
        Segments where orig == hiragana (no real reading) are treated as plain.
        """
        raise NotImplementedError


_registry = {}
_FALLBACK_CHAIN = ['high_accuracy', 'enhanced', 'standard']


def register(cls):
    _registry[cls.id] = cls
    return cls


def resolve_engine(preferred_id):
    """
    Return (engine_instance, actual_id) for the best available engine,
    walking the fallback chain from preferred_id downward.
    Returns (None, None) if nothing is available.
    """
    try:
        start = _FALLBACK_CHAIN.index(preferred_id)
    except ValueError:
        start = 0
    for eid in _FALLBACK_CHAIN[start:]:
        cls = _registry.get(eid)
        if cls:
            try:
                inst = cls()
                if inst.is_available():
                    return inst, eid
            except Exception:
                continue
    return None, None


def _ensure_all_registered():
    """Import engines package to trigger all @register decorators."""
    try:
        from calibre_plugins.furigana_ruby import engines as _e  # noqa
    except ImportError:
        try:
            import engines as _e  # noqa
        except ImportError:
            pass
