/**
 * Furigana Ruby Plugin — Viewer JS (Calibre 6–9 + browser content-server)
 *
 * Injects a compact floating toggle pill that auto-fades when idle.
 * Moving the mouse (or tapping) reveals it; hover also keeps it visible.
 * No layout changes — the pill floats over the corner at low opacity.
 */
(function () {
    'use strict';

    const KEY    = 'fg_ruby_v1';   // must match RUBY_JS in furigana_engine.py
    const MODES  = ['all', 'publisher', 'off'];
    const ICONS  = { all: '🈳', publisher: '📖', off: '🈚' };
    const LABELS = { all: 'すべて', publisher: '出版社', off: '非表示' };
    const COLORS = {
        all:       'rgba(42,90,170,0.9)',
        publisher: 'rgba(20,110,50,0.9)',
        off:       'rgba(100,100,100,0.8)',
    };

    // ── Inject CSS ────────────────────────────────────────────────
    function injectCSS() {
        if (document.getElementById('furigana-css')) return;
        const s = document.createElement('style');
        s.id = 'furigana-css';
        s.textContent = `
            /* Auto-generated ruby colour */
            ruby.auto rt {
                color: #5a7fbf !important;
                opacity: 0.9;
            }
            @media (prefers-color-scheme: dark) {
                ruby.auto rt { color: #7aa8e8 !important; }
            }

            /* Toggle states */
            [data-ruby="off"] rt,
            [data-ruby="off"] rp { display: none !important; }
            [data-ruby="publisher"] ruby.auto rt,
            [data-ruby="publisher"] ruby.auto rp { display: none !important; }

            /* ── Square floating toggle — bottom-left ────────────────────
               Icon (emoji) on the left, 3-char vertical label on the right.
               Auto-fades at rest; mouse move / tap / hover restores opacity.
               ──────────────────────────────────────────────────────────── */
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
            #fg-btn.fg-show { opacity: 1 !important; transition: opacity 0.15s ease !important; }
            #fg-btn:hover   { opacity: 1 !important; transition: opacity 0.15s ease !important; }
            #fg-btn .fg-icon {
                font-size: 20px;
                line-height: 1;
                display: block;
            }
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
        `;
        document.head.appendChild(s);
    }

    // ── State ─────────────────────────────────────────────────────
    // Four-layer storage so mode survives across any iframe navigation
    // strategy Calibre's browser reader may use (see RUBY_JS comments).
    function _pw() {
        try { return window.parent !== window ? window.parent : null; } catch(e) { return null; }
    }
    function _frame() {
        const pw = _pw();
        if (!pw) return null;
        try {
            const fs = pw.document.querySelectorAll('iframe');
            for (let i = 0; i < fs.length; i++) {
                if (fs[i].contentWindow === window) return fs[i];
            }
        } catch(e) {}
        return null;
    }

    function getMode() {
        let v;
        try { const f = _frame(); if (f) { v = f.getAttribute('data-fg-mode'); if (v && MODES.includes(v)) return v; } } catch(e) {}
        try { const pw = _pw(); if (pw && pw.__fgM && MODES.includes(pw.__fgM)) return pw.__fgM; } catch(e) {}
        try { const n = (window.name || '').match(/\bfgM=(\w+)/); if (n && MODES.includes(n[1])) return n[1]; } catch(e) {}
        try { v = localStorage.getItem(KEY);   if (v && MODES.includes(v)) return v; } catch(e) {}
        try { v = sessionStorage.getItem(KEY); if (v && MODES.includes(v)) return v; } catch(e) {}
        return 'all';
    }

    function setMode(m) {
        try { const f = _frame(); if (f) f.setAttribute('data-fg-mode', m); } catch(e) {}
        try { const pw = _pw(); if (pw) pw.__fgM = m; } catch(e) {}
        try { window.name = (window.name || '').replace(/\bfgM=\w+/g, '').trim() + ' fgM=' + m; } catch(e) {}
        try { localStorage.setItem(KEY, m);   } catch(e) {}
        try { sessionStorage.setItem(KEY, m); } catch(e) {}
        document.documentElement.setAttribute('data-ruby', m);
        updateBtn(m);
    }

    function cycleMode() {
        setMode(MODES[(MODES.indexOf(getMode()) + 1) % MODES.length]);
    }

    // ── Auto-hide helpers ─────────────────────────────────────────
    let _fadeTimer = null;

    function showBtn(ms) {
        const btn = document.getElementById('fg-btn');
        if (!btn) return;
        btn.classList.add('fg-show');
        clearTimeout(_fadeTimer);
        _fadeTimer = setTimeout(() => btn.classList.remove('fg-show'), ms || 2500);
    }

    // ── Button ────────────────────────────────────────────────────

    // Position bottom-left for vertical text, bottom-right for horizontal
    function positionBtn() {
        const btn = document.getElementById('fg-btn');
        if (!btn) return;
        try {
            const wm = (getComputedStyle(document.documentElement).writingMode ||
                        getComputedStyle(document.body).writingMode || '');
            if (wm.includes('vertical')) {
                btn.style.left  = '8px';
                btn.style.right = 'auto';
            } else {
                btn.style.right = '8px';
                btn.style.left  = 'auto';
            }
        } catch (e) {}
    }

    function createBtn() {
        if (document.getElementById('fg-btn')) return;   // RUBY_JS already created it
        if (!document.querySelector('ruby')) return;      // no ruby on this page

        const btn = document.createElement('button');
        btn.id    = 'fg-btn';
        btn.title = 'Toggle furigana — R / F7 / Cmd+Shift+F';

        function blockAndStop(e) {
            e.stopPropagation(); e.stopImmediatePropagation(); e.preventDefault();
        }
        // pointerdown fires before Calibre's tap-to-navigate capture listeners
        btn.addEventListener('pointerdown', function(e) {
            blockAndStop(e);
            cycleMode();
            showBtn(3000);
        });
        // Block all subsequent events so the reader can't interpret the
        // button tap as a page-turn gesture
        ['pointerup', 'click', 'touchstart', 'touchend', 'mousedown', 'mouseup'].forEach(function(ev) {
            btn.addEventListener(ev, blockAndStop);
        });

        document.body.appendChild(btn);
        updateBtn(getMode());
        positionBtn();

        // Show on any mouse/touch activity; fade after idle
        document.addEventListener('mousemove',  () => showBtn(2500), { passive: true });
        document.addEventListener('touchstart', () => showBtn(3000), { passive: true });
    }

    function updateBtn(m) {
        const btn = document.getElementById('fg-btn');
        if (!btn) return;
        btn.innerHTML = `<span class="fg-icon">${ICONS[m]}</span>` +
                        `<span class="fg-text" style="color:${COLORS[m]}">${LABELS[m]}</span>`;
    }

    // ── Keyboard shortcuts ────────────────────────────────────────
    function isShortcut(e) {
        const kl   = (e.key || '').toLowerCase();
        const meta = e.metaKey || e.ctrlKey;
        const none = !meta && !e.shiftKey && !e.altKey;
        return (
            (none && kl === 'r') ||
            (e.key === 'F7') ||
            (meta && e.shiftKey && kl === 'f') ||
            (meta && e.shiftKey && kl === 'r')
        );
    }

    ['keydown', 'keyup'].forEach(function(evType) {
        document.addEventListener(evType, function(e) {
            if (isShortcut(e)) {
                e.preventDefault();
                e.stopImmediatePropagation();
                if (evType === 'keydown') {
                    cycleMode();
                    showBtn(2500);   // briefly reveal so user sees new state
                }
            }
        }, true);
    });

    // ── Init ──────────────────────────────────────────────────────
    function init() {
        injectCSS();
        createBtn();
        setMode(getMode());
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
