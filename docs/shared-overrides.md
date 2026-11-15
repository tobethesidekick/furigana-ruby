# Shared Taiwan overrides (`tw_overrides.json`)

**Owner: this repo (furigana-ruby).** The Chinese Learning App consumes a pinned copy.
Decided 2026-11-14. Background and the wider plan: `conversion-plan.md`.

## What it is
`tw_overrides.json` (repo root) holds literal Simplified → Traditional (Taiwan) overrides applied
on top of OpenCC `s2twp`, e.g. `数字专辑 → 數位專輯`, plus guards that keep newer OpenCC data from
misfiring (`一出事`, `只剩`).

```json
{ "schema_version": 1, "name": "tw_overrides", "owner": "furigana-ruby",
  "overrides": { "数字专辑": "數位專輯", "只剩": "只剩", ... } }
```

- Keys = Simplified source text. Values = FINAL Traditional output.
- Values are emitted **literally** — never run them back through OpenCC (s2twp's phrase stage is keyed
  on Traditional and would turn 數據 back into 資料).
- Longest key wins. A key mapping to itself (`只剩`) is a guard: it stops OpenCC converting it.
- `schema_version` is bumped on any breaking format change; consumers must refuse unknown versions.

## Rules that live in CODE, not in the JSON (each consumer must reimplement)
1. Apply to **chapter text only** (XHTML/HTML/TXT body). Never to metadata, OPF/NCX, or author fields
   (otherwise 天蚕土豆 → 天蠶馬鈴薯).
2. Only for the `s2twp` direction; not T→S.
3. `土豆` is skipped when preceded by `天蚕`/`天蠶` (pen name).
4. Other plugin guards (的士兵, adverbial 乍得) are plugin-only today; see `chinese_engine.py`.

## How the plugin uses it
`chinese_engine.py::_load_tw_overrides()` — reads it via Calibre's `get_resources` (inside the zip) or
from next to the module. If missing/invalid it logs and falls back to plain s2twp. `setup_plugin.py`
lists it in `SOURCE_FILES`, so it ships in the zip. Edit the JSON, run
`OPENCC_PATH=<opencc> python3 tests/test_conversion_golden.py`, bump the version, rebuild.

## How the learning app should use it (future, plan step 3)
- **Do not live-link.** Copy a pinned version into the app (e.g. `src/data/tw_overrides.json`) with a
  small sync script that fetches a tagged release/commit of this repo and records the commit hash.
  Either project can then ship without the other.
- Switch the reader from plain `cn→t` to OpenCC-js `twp`. opencc-js has no literal-override hook, so
  use the **placeholder technique**: replace each override key in the text with a private-use
  placeholder, convert, then substitute the literal value back.
- Keep a plain `cn→t` converter for script detection (`twp` rewrites Traditional variants like
  爲/啓, which breaks per-character detection).
- Re-implement scope rules 1–3 above.
- Run the same golden cases (`tests/test_conversion_golden.py` lists them) against the JS output.

## Changing it
Add entries only for terms unambiguous without context. Deliberately NOT included: 酒店, 质量, 数据,
评论, 支持, 项目, 程序. Add a golden case for every new entry, and note the change in the changelog so
the app's next sync picks it up.
