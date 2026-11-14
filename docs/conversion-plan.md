# Chinese S↔T conversion — unification & maintenance plan

Status: approved 2026-11-14. Step 1 done (uncommitted); steps 2–4 pending.

## Background
- Plugin (`chinese_engine.py`) converts with Python `opencc-python-reimplemented` 0.1.7 (last release; dictionaries stale).
- Chinese learning app reader converts with `opencc-js` 1.3.1 (`public/opencc-js/`), currently plain `cn→t` (no Taiwan phrases; `twp` data is in the bundle but unused).
- Test (2026-11-14, novel 分手后我靠综艺爆红娱乐圈, 35,081 lines): feeding opencc-js's dictionaries
  (STPhrases, STCharacters, TWPhrases, TWVariants) into the Python library cut differing lines vs JS
  from 335 → 122 (0.35%, remaining = word-segmentation engine differences). Speed 3.9 s / 1 MB.
- Newer data is MIXED: fixes 實時→即時, but adds errors: 一出事/一出手/一出門/話一出 → 一齣… (wrong),
  只剩 → 隻剩 (wrong); and shifts 透過→通過 (style change, both valid).
  => unify the DATA, but ship a guard layer + regression tests.

## Decision
Unify on data, not engine. Python stays in the plugin, JS stays in the app, both fed the same dictionaries.

## Layers (highest priority first)
1. User phrases (per user; future feature)
2. Our phrases + guards (shared JSON): 数字专辑→數位專輯, 的士, 乍得, 一出/一齣, 只剩, …
3. OpenCC data (refreshed from opencc-js releases)
Layers 1–2 are emitted as LITERAL text so OpenCC cannot re-convert them (s2twp's phrase stage is
keyed on Traditional and would turn our 數據 back into 資料).

## Scope rules (learned the hard way)
- Overrides apply to CHAPTER TEXT only: .xhtml/.html/.htm, TXT, standalone HTML.
- Never to .opf/.ncx/.xml, FB2 (author fields in <description>), or Calibre metadata
  (title, authors, tags, series, publisher, comments). Reason: 天蚕土豆 → 天蠶馬鈴薯.
- Gated to the `s2twp` variant; other variants and all T→S directions are untouched.
- Guard: 土豆 not converted when preceded by 天蚕/天蠶.
- Deliberately NOT overridden (ambiguous without context): 酒店 (hotel/tavern), 质量 (quality/mass),
  数据 (數據/資料 both used), 评论, 支持, 项目, 程序. 信息 → 資訊 (s2twp default) is accepted.

## Build order
1. [DONE, uncommitted] Fix metadata/OPF regression; `overrides` flag on `_convert_text` /
   `_convert_html_text_nodes`; call sites wired; tested on EPUB/TXT/FB2/metadata.
2. Data refresh script (`scripts/refresh_opencc_data.py`): reads dictionaries from an opencc-js release,
   writes STPhrases/STCharacters/TWPhrases/TWVariants (format `key<TAB>value`, first value only),
   records the opencc-js version (show in diagnostics). Golden regression set (~50 KB of the novel +
   one sentence per guard); diff report on every refresh. Add guards for 一齣 and 隻剩.
3. Shared overrides JSON (`tw_overrides.json`) read by the plugin (Python) and the app (JS);
   app switches reader from `cn→t` to `twp` using the placeholder technique + plain converter for
   script detection (twp rewrites Traditional variants like 爲/啓, which breaks per-char detection).
4. User customization (separate feature release): JSON in Calibre config dir; per-direction lists
   (s2t / t2s); chapter-text scope by default, opt-in "also metadata"; table UI in the S↔T panel
   with add/edit/delete + import/export; precedence user > ours > OpenCC, longest match within a layer.
   Known edge: a user phrase cuts the text so OpenCC cannot see a longer phrase spanning it.

## Maintenance routine (on each opencc-js release; Dependabot in the app repo is the signal)
1. Run refresh script → new dictionaries.
2. Run golden set → read diff report; add guards for new misfires; accept style shifts knowingly.
3. Bump plugin version (minor), changelog notes data version; rebuild zip with `setup_plugin.py`
   (installed Calibre copy keeps old behaviour until rebuilt + reinstalled).
4. App: `pnpm update opencc-js` (sync script copies bundles), re-run same golden set.

## Risks
- Re-converting an old book with new data yields different words (note in release notes).
- 0.35% engine difference persists unless one engine is later ported.
- If opencc-python-reimplemented is abandoned: vendor its single file.
- Shared overrides couple the two projects (see "Shared override" note below).

## Shared override note
Keep the shared file's schema versioned and each project's copy pinned (copied by a sync script, not
live-linked), so either project can ship without the other. See chat discussion 2026-11-14.
