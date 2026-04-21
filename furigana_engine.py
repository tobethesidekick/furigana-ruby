"""
furigana_engine.py  v9
Key fixes:
  - Ruby CSS uses display:ruby / ruby-base / ruby-text (not inline/block variants)
  - -webkit-ruby-position: before for correct right-side placement in vertical-rl
  - Toggle button: small, transparent, fades in on hover
  - _split_trailing_kana: only annotate kanji portion of morpheme
"""

import re
from html.parser import HTMLParser


def is_kanji(char):
    cp = ord(char)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0xF900 <= cp <= 0xFAFF)

def contains_kanji(text):
    return any(is_kanji(c) for c in text)


SKIP_TAGS = {'ruby', 'rt', 'rp', 'script', 'style', 'code', 'pre'}

class RubyAwareParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.result = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attr_str = ''.join(
            f' {n}' if v is None else f' {n}="{v}"' for n, v in attrs
        )
        self.result.append(('tag', f'<{tag}{attr_str}>'))
        if tag.lower() in SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        self.result.append(('tag', f'</{tag}>'))
        if tag.lower() in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_startendtag(self, tag, attrs):
        attr_str = ''.join(
            f' {n}' if v is None else f' {n}="{v}"' for n, v in attrs
        )
        self.result.append(('tag', f'<{tag}{attr_str}/>'))

    def handle_data(self, data):
        if self._skip_depth > 0:
            self.result.append(('tag', data))
        else:
            self.result.append(('text', data))

    def handle_entityref(self, name): self.result.append(('tag', f'&{name};'))
    def handle_charref(self, name):   self.result.append(('tag', f'&#{name};'))
    def handle_comment(self, data):   self.result.append(('tag', f'<!--{data}-->'))
    def handle_decl(self, decl):      self.result.append(('tag', f'<!{decl}>'))
    def handle_pi(self, data):        self.result.append(('tag', f'<?{data}>'))
    def unknown_decl(self, data):     self.result.append(('tag', f'<![{data}]>'))


# ── CSS ───────────────────────────────────────────────────────────────────────
# Key insight: publisher ruby works with ZERO CSS — Chromium UA handles layout.
# Explicit display:ruby / writing-mode overrides break vertical-rl ruby.
# Auto ruby uses <rb>…</rb><rt>…</rt> (no <rp>) to match publisher structure.

RUBY_CSS = """<style id="furigana-ruby-css">
/* Furigana Ruby Plugin */

/* Auto-generated ruby colour only — no layout overrides */
ruby.auto rt { color: #4a72c4; }
@media (prefers-color-scheme: dark) {
    ruby.auto rt { color: #7fb3f5; }
}

/* ── Toggle states ── */
html[data-ruby="off"] ruby.auto rt,
html[data-ruby="off"] ruby.auto rp,
html[data-ruby="off"] ruby:not(.auto) rt,
html[data-ruby="off"] ruby:not(.auto) rp { display: none !important; }

html[data-ruby="publisher"] ruby.auto rt,
html[data-ruby="publisher"] ruby.auto rp { display: none !important; }

/* ── Square floating toggle ───────────────────────────────────────────
   Bottom-left corner. Icon on the left, 3-char vertical label on the
   right — gives a near-square shape. Fades to nearly invisible at rest;
   mouse movement / tap / hover restores full opacity (see RUBY_JS).
   ──────────────────────────────────────────────────────────────────── */
#fg-btn {
    position: fixed;
    bottom: 36px;
    left: 8px;
    z-index: 2147483647;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 3px;
    padding: 7px 7px;
    border-radius: 10px;
    border: 1px solid rgba(120,120,120,0.35);
    background: rgba(255,255,255,0.92);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    cursor: pointer;
    font-family: -apple-system, "Hiragino Sans", "Yu Gothic UI", sans-serif;
    user-select: none;
    writing-mode: horizontal-tb !important;
    -webkit-writing-mode: horizontal-tb !important;
    opacity: 0.12;
    transition: opacity 0.5s ease;
    pointer-events: auto;
}
/* Revealed by JS (.fg-show) or CSS hover */
#fg-btn.fg-show { opacity: 1 !important; transition: opacity 0.15s ease !important; }
#fg-btn:hover   { opacity: 1 !important; transition: opacity 0.15s ease !important; }
/* Icon (emoji) */
#fg-btn .fg-icon {
    font-size: 20px;
    line-height: 1;
    display: block;
}
/* 3-char vertical label */
#fg-btn .fg-text {
    font-size: 10px;
    line-height: 1;
    writing-mode: vertical-rl;
    -webkit-writing-mode: vertical-rl;
    letter-spacing: 0.05em;
    display: block;
}
@media (prefers-color-scheme: dark) {
    #fg-btn {
        background: rgba(28,28,38,0.92);
        border-color: rgba(150,150,150,0.35);
    }
}
</style>
"""

RUBY_JS = """<script id="furigana-ruby-js">
(function(){
    'use strict';
    var MODES  = ['all','publisher','off'];
    var ICONS  = {all:'🈳', publisher:'📖', off:'🈚'};
    var LABELS = {all:'すべて', publisher:'出版社', off:'非表示'};
    var COLORS = {all:'rgba(42,90,170,0.9)', publisher:'rgba(20,110,50,0.9)', off:'rgba(100,100,100,0.8)'};
    var KEY    = 'fg_ruby_v1';

    /* ── Persistent storage ────────────────────────────────────────────
       Calibre's browser reader loads each EPUB page into the same
       <iframe> element but creates a new window object every navigation,
       so sessionStorage and sometimes localStorage reset each page.

       We try four mechanisms in order — the first write that succeeds
       is the one reads will use on the next page:

       1. data-fg-mode on the <iframe> element in the parent frame
          → element stays in parent DOM through src changes ✓
       2. window.parent.__fgM property
          → parent SPA frame never reloads ✓
       3. window.name
          → browser spec guarantees survival through same-window nav ✓
       4. localStorage / sessionStorage  (normal browsers / desktop viewer)
       ──────────────────────────────────────────────────────────────── */
    function _pw(){ try{ return window.parent!==window?window.parent:null; }catch(e){ return null; } }
    function _frame(){
        var pw=_pw(); if(!pw) return null;
        try{
            var fs=pw.document.querySelectorAll('iframe');
            for(var i=0;i<fs.length;i++){ if(fs[i].contentWindow===window) return fs[i]; }
        }catch(e){}
        return null;
    }
    function getMode(){
        var v;
        try{ var f=_frame(); if(f){ v=f.getAttribute('data-fg-mode'); if(v&&MODES.indexOf(v)>=0) return v; } }catch(e){}
        try{ var pw=_pw(); if(pw&&pw.__fgM&&MODES.indexOf(pw.__fgM)>=0) return pw.__fgM; }catch(e){}
        try{ var n=(window.name||'').match(/\bfgM=(\w+)/); if(n&&MODES.indexOf(n[1])>=0) return n[1]; }catch(e){}
        try{ v=localStorage.getItem(KEY); if(v&&MODES.indexOf(v)>=0) return v; }catch(e){}
        try{ v=sessionStorage.getItem(KEY); if(v&&MODES.indexOf(v)>=0) return v; }catch(e){}
        return 'all';
    }
    function applyMode(m){
        document.documentElement.setAttribute('data-ruby', m);
        var btn = document.getElementById('fg-btn');
        if(btn){
            btn.innerHTML = '<span class="fg-icon">'+ICONS[m]+'</span>'+
                            '<span class="fg-text" style="color:'+COLORS[m]+'">'+LABELS[m]+'</span>';
        }
    }
    function setMode(m){
        try{ var f=_frame(); if(f) f.setAttribute('data-fg-mode',m); }catch(e){}
        try{ var pw=_pw(); if(pw) pw.__fgM=m; }catch(e){}
        try{ window.name=(window.name||'').replace(/\bfgM=\w+/g,'').trim()+' fgM='+m; }catch(e){}
        try{ localStorage.setItem(KEY,m); }catch(e){}
        try{ sessionStorage.setItem(KEY,m); }catch(e){}
        applyMode(m);
    }
    function cycle(){ var i=MODES.indexOf(getMode()); setMode(MODES[(i+1)%MODES.length]); }

    /* ── Auto-hide helpers ── */
    var _fadeTimer = null;
    function showBtn(ms) {
        var b = document.getElementById('fg-btn');
        if(!b) return;
        b.classList.add('fg-show');
        clearTimeout(_fadeTimer);
        _fadeTimer = setTimeout(function(){ b.classList.remove('fg-show'); }, ms || 2500);
    }

    function blockAndStop(e){ e.stopPropagation(); e.stopImmediatePropagation(); e.preventDefault(); }

    function makeBtn(){
        if(document.getElementById('fg-btn')) return;
        if(!document.querySelector('ruby')) return;

        var b = document.createElement('button');
        b.id  = 'fg-btn';
        b.title = 'Toggle furigana — R / F7 / Cmd+Shift+F';

        /* pointerdown fires before reader tap-to-navigate handlers.
           Block all subsequent pointer/touch/click events so the reader
           cannot interpret the button tap as a page-turn. */
        b.addEventListener('pointerdown', function(e){
            blockAndStop(e);
            cycle();
            showBtn(3000);
        });
        ['pointerup','click','touchstart','touchend','mousedown','mouseup'].forEach(function(ev){
            b.addEventListener(ev, blockAndStop);
        });

        document.body.appendChild(b);
        applyMode(getMode());

        /* Show button on any mouse/touch activity; fade after idle */
        document.addEventListener('mousemove',  function(){ showBtn(2500); }, {passive:true});
        document.addEventListener('touchstart', function(){ showBtn(3000); }, {passive:true});
    }

    /* ── Keyboard shortcuts ── */
    function isShortcut(e){
        var kl=e.key ? e.key.toLowerCase() : '';
        var meta=e.metaKey||e.ctrlKey, none=!meta&&!e.shiftKey&&!e.altKey;
        return (none&&kl==='r')||(e.key==='F7')||(meta&&e.shiftKey&&kl==='f')||(meta&&e.shiftKey&&kl==='r');
    }
    ['keydown','keyup'].forEach(function(t){
        document.addEventListener(t, function(e){
            if(isShortcut(e)){
                e.preventDefault(); e.stopImmediatePropagation();
                if(t==='keydown'){ cycle(); showBtn(2500); }
            }
        }, true);
    });

    applyMode(getMode());
    if(document.readyState==='loading'){
        document.addEventListener('DOMContentLoaded', makeBtn);
    } else { makeBtn(); }
})();
</script>
"""


def inject_css_js(html):
    if 'id="furigana-ruby-css"' in html:
        return html
    if '</head>' in html:
        html = html.replace('</head>', RUBY_CSS + '</head>', 1)
    elif '<body' in html:
        idx = html.index('<body')
        html = html[:idx] + RUBY_CSS + html[idx:]
    else:
        html = RUBY_CSS + html
    if '</body>' in html:
        html = html.replace('</body>', RUBY_JS + '</body>', 1)
    else:
        html += RUBY_JS
    return html


def strip_css_js(html):
    html = re.sub(r'<style\s+id="furigana-ruby-css">.*?</style>\s*',
                  '', html, flags=re.DOTALL)
    html = re.sub(r'<script\s+id="furigana-ruby-js">.*?</script>\s*',
                  '', html, flags=re.DOTALL)
    return html


# ── pykakasi ──────────────────────────────────────────────────────────────────

_kakasi = None

def init_kakasi():
    global _kakasi
    if _kakasi is not None:
        return _kakasi
    errors = []
    try:
        from calibre_plugins.furigana_ruby.deps_loader import ensure_deps
        ok = ensure_deps()
        if not ok:
            errors.append("deps_loader.ensure_deps() returned False")
    except Exception as e:
        errors.append(f"deps_loader import failed: {e}")
    try:
        import pykakasi
    except ImportError as e:
        msg = f"Cannot import pykakasi: {e}"
        if errors: msg += "\n" + "\n".join(errors)
        raise ImportError(msg)
    try:
        _kakasi = pykakasi.kakasi()
    except Exception as e:
        raise RuntimeError(f"pykakasi.kakasi() failed: {e}")
    return _kakasi

def get_kakasi():
    return init_kakasi()


# ── Kana suffix splitting ─────────────────────────────────────────────────────

def _split_trailing_kana(orig, hira):
    """
    Strip trailing hiragana/katakana from orig so only the kanji part
    gets annotated.

    大き / おおき → ('大', 'おお', 'き')
    走って / はしって → ('走', 'はし', 'って')
    人勢 / じんせい → ('人勢', 'じんせい', '')
    """
    suffix_len = 0
    for c in reversed(orig):
        cp = ord(c)
        if 0x3040 <= cp <= 0x30FF:
            suffix_len += 1
        else:
            break
    if suffix_len == 0:
        return orig, hira, ''
    suffix = orig[-suffix_len:]
    if hira.endswith(suffix) and len(hira) > suffix_len:
        return orig[:-suffix_len], hira[:-suffix_len], suffix
    return orig, hira, ''


# ── Conversion ────────────────────────────────────────────────────────────────

def text_to_ruby_segments(text, annotate_levels=None):
    if not contains_kanji(text):
        return [('plain', text)]
    kks = get_kakasi()
    items = kks.convert(text)
    try:
        from calibre_plugins.furigana_ruby.jlpt_filter import word_needs_annotation
    except ImportError:
        from jlpt_filter import word_needs_annotation
    segments = []
    for item in items:
        orig = item.get('orig', '')
        if not orig:
            continue
        hira = item.get('hira', '')
        if not contains_kanji(orig):
            segments.append(('plain', orig))
            continue
        if not hira or orig == hira:
            segments.append(('plain', orig))
            continue
        if not word_needs_annotation(orig, annotate_levels=annotate_levels):
            segments.append(('plain', orig))
            continue
        segments.append(('ruby', orig, hira))
    return segments


def segments_to_html(segments):
    parts = []
    for seg in segments:
        if seg[0] == 'plain':
            parts.append(seg[1])
        else:
            orig, reading = seg[1], seg[2]
            kanji_part, kanji_reading, kana_suffix = _split_trailing_kana(orig, reading)
            if kanji_part and any(is_kanji(c) for c in kanji_part):
                parts.append(
                    f'<ruby class="auto">'
                    f'<rb>{kanji_part}</rb>'
                    f'<rt>{kanji_reading}</rt>'
                    f'</ruby>'
                )
            else:
                parts.append(orig)
            if kana_suffix:
                parts.append(kana_suffix)
    return ''.join(parts)


def inject_furigana_html(html_content, annotate_levels=None):
    parser = RubyAwareParser()
    parser.feed(html_content)
    parts = []
    for token_type, content in parser.result:
        if token_type == 'tag':
            parts.append(content)
        else:
            if not contains_kanji(content):
                parts.append(content)
            else:
                segs = text_to_ruby_segments(content, annotate_levels=annotate_levels)
                parts.append(segments_to_html(segs))
    return inject_css_js(''.join(parts))


def strip_auto_furigana_html(html_content):
    pattern = re.compile(
        r'<ruby\s+class=["\']auto["\']>'
        r'(?:<rb>)?(.*?)(?:</rb>)?'   # handle old format with rb tags
        r'(?:<rp>[^<]*</rp>)?'        # handle old format with rp tags
        r'<rt>[^<]*</rt>'
        r'(?:<rp>[^<]*</rp>)?'        # handle old format with rp tags
        r'</ruby>',
        re.DOTALL
    )
    return strip_css_js(pattern.sub(r'\1', html_content))


def strip_auto_furigana_by_levels(html_content, remove_levels):
    """
    Strip only auto ruby annotations whose kanji belong to any level in
    remove_levels.  Annotations for other levels are left untouched.

    remove_levels: set of level strings, e.g. {'N4', 'N5', 'unlisted'}
                   Pass None or empty set to strip nothing.

    After stripping, the embedded CSS/JS is removed only if no auto ruby
    remains in the document (full strip).  Partial strips keep it so the
    toggle button still works for remaining annotations.
    """
    if not remove_levels:
        return html_content

    try:
        from calibre_plugins.furigana_ruby.jlpt_filter import word_needs_annotation
    except ImportError:
        from jlpt_filter import word_needs_annotation

    pattern = re.compile(
        r'<ruby\s+class=["\']auto["\']>'
        r'(?:<rb>)?(.*?)(?:</rb>)?'
        r'(?:<rp>[^<]*</rp>)?'
        r'<rt>[^<]*</rt>'
        r'(?:<rp>[^<]*</rp>)?'
        r'</ruby>',
        re.DOTALL
    )

    def replacer(m):
        kanji_text = m.group(1)
        # Remove this ruby only if its kanji belong to a level we're stripping
        if word_needs_annotation(kanji_text, remove_levels):
            return kanji_text
        return m.group(0)   # keep untouched

    result = pattern.sub(replacer, html_content)

    # Strip embedded CSS/JS only when no auto ruby remains at all
    if 'class="auto"' not in result:
        result = strip_css_js(result)

    return result


def has_auto_furigana(html_content):
    return 'class="auto"' in html_content


def get_annotated_levels(epub_path):
    """
    Scan an EPUB and return the set of JLPT levels that currently have
    auto-generated ruby annotations.

    Returns a subset of {'N1','N2','N3','N4','N5','unlisted'}.
    Returns an empty set if no auto ruby is present or the file can't be read.

    Note: uses get_kanji_level_exact so that kanji outside any JLPT list
    are reported as 'unlisted' rather than being folded into 'N1'.
    """
    import zipfile as _zf

    try:
        from calibre_plugins.furigana_ruby.jlpt_filter import (
            get_kanji_level_exact, is_kanji)
    except ImportError:
        from jlpt_filter import get_kanji_level_exact, is_kanji

    pattern = re.compile(
        r'<ruby\s+class=["\']auto["\']>'
        r'(?:<rb>)?(.*?)(?:</rb>)?'
        r'<rt>[^<]*</rt>'
        r'</ruby>',
        re.DOTALL
    )

    levels_found = set()
    _all_possible = {'N1', 'N2', 'N3', 'N4', 'N5', 'unlisted'}

    try:
        with _zf.ZipFile(epub_path, 'r') as zf:
            for name in zf.namelist():
                if not name.lower().endswith(('.xhtml', '.html', '.htm')):
                    continue
                try:
                    txt = zf.read(name).decode('utf-8', errors='ignore')
                    for m in pattern.finditer(txt):
                        for char in m.group(1):
                            if is_kanji(char):
                                levels_found.add(get_kanji_level_exact(char))
                except Exception:
                    pass
                # Early exit once all levels are detected
                if levels_found >= _all_possible:
                    return levels_found
    except Exception:
        pass

    return levels_found


# ── EPUB processor ────────────────────────────────────────────────────────────

def process_epub_file(epub_path, output_path, mode='add', annotate_levels=None,
                      remove_levels=None, progress_callback=None):
    import zipfile, os, tempfile, shutil

    if mode == 'add':
        init_kakasi()

    tmp = tempfile.mktemp(suffix='.epub')
    shutil.copy2(epub_path, tmp)

    html_ext = {'.xhtml', '.html', '.htm'}
    skip_names = {
        'toc.xhtml','toc.html','nav.xhtml','nav.html',
        'navigation.xhtml','navigation.html','ncx.xhtml',
    }

    def is_content(name):
        base = name.lower().split('/')[-1]
        return any(base.endswith(e) for e in html_ext) and base not in skip_names

    ruby_added = 0
    file_errors = []

    with zipfile.ZipFile(tmp, 'r') as zin:
        names = zin.namelist()
        html_files = [n for n in names if is_content(n)]
        total = len(html_files)
        processed = 0
        out_tmp = tempfile.mktemp(suffix='.epub')

        with zipfile.ZipFile(out_tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                data = zin.read(name)
                if name in html_files:
                    try:
                        text = data.decode('utf-8')
                        before = text.count('class="auto"')
                        if mode == 'add':
                            text = inject_furigana_html(text, annotate_levels=annotate_levels)
                        elif remove_levels is not None:
                            text = strip_auto_furigana_by_levels(text, remove_levels)
                        else:
                            text = strip_auto_furigana_html(text)
                        ruby_added += text.count('class="auto"') - before
                        data = text.encode('utf-8')
                    except Exception as e:
                        file_errors.append(f'{name}: {e}')
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total, name)
                if name == 'mimetype':
                    zout.writestr(
                        zipfile.ZipInfo('mimetype'), data,
                        compress_type=zipfile.ZIP_STORED)
                else:
                    zout.writestr(name, data)

    shutil.move(out_tmp, output_path)
    os.unlink(tmp)
    return processed, ruby_added, file_errors
