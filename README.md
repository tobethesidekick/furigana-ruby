# 振り仮名 Ruby & More — Calibre Plugin

A [Calibre](https://calibre-ebook.com) plugin for East Asian ebooks. Select one or more books, click the **振り仮名** toolbar button to add furigana. Or use the dropdown menu for additional commands. All core dependencies are bundled — no separate installs needed for the default engine.

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/tobethesidekick)

---

## Features

### 振り仮名 — Edit Ruby (Japanese EPUBs)
- **Two furigana engines** — Enhanced (built-in, no download) and High-accuracy (SudachiPy, ~40 MB optional download)
- **Preserves publisher ruby** — hand-verified readings are never overwritten
- **JLPT-level filtering** — annotate only the difficulty levels you want (N5–N1 + Unlisted)
- **Level tracking** — books remember which levels were annotated; already up-to-date books are detected automatically on dialog open
- **Selective add/remove** — update individual levels without reprocessing the whole book
- **Viewer toggle** — switch between *all ruby*, *publisher only*, and *hidden* while reading
- Works in the **Calibre desktop viewer** and **Calibre browser content server** (Chrome, Firefox, Safari, mobile)

### 繁 — Convert Chinese S↔T (Chinese · EPUB · HTML · FB2 · TXT)
- **Simplified ↔ Traditional Chinese** conversion powered by [opencc-python-reimplemented](https://github.com/yichen0831/opencc-python-reimplemented) (bundled)
- **8 conversion variants** — Generic S↔T, Taiwan Traditional 正體 (`s2tw` / `s2twp` recommended), Hong Kong Traditional 港式繁體 (`s2hk`), and reverse T→S directions
- **Phrase-level variants** (`s2twp`, `tw2sp`) for accurate vocabulary conversion (e.g. 軟件→軟體)
- **Auto-detects script** from EPUB metadata and content sampling — pre-selects applicable books and flags books that don't need conversion
- **Metadata conversion** — optionally converts title and author fields in the same pass
- **Text nodes only** — tags, attributes, CSS, and scripts are never modified

### ↔ — Text Direction (Japanese · Chinese · Korean EPUBs)
- **Horizontal ↔ Vertical** text direction conversion in one click
- Updates CSS `writing-mode` across all stylesheets, OPF `page-progression-direction`, and inline styles
- **Tate-chu-yoko** — numbers and short Latin runs are wrapped in `text-combine-upright` so they render upright in vertical columns
- **Punctuation normalisation** — converts Western quotes to CJK corner brackets, ASCII periods to ideographic full stops, and tab characters to ideographic spaces
- **Toggle button repositioning** — the ruby viewer toggle moves to bottom-left for vertical text and bottom-right for horizontal text automatically
- Supports bulk conversion of multiple books at once

---

## Installation (new computer)

### Requirements
- [Calibre](https://calibre-ebook.com/download) 6.0 or later
- macOS, Windows, or Linux

### Step 1 — Download the plugin

Go to the [**Releases**](../../releases/latest) page and download **`FuriganaRuby.zip`**.

> Do **not** unzip it — Calibre loads it as-is.

### Step 2 — Install into Calibre

1. Open Calibre
2. **Preferences** → **Plugins** → **Load plugin from file**
3. Select the downloaded `FuriganaRuby.zip`
4. Click **Yes** when Calibre asks to add it
5. Restart Calibre

That's it — the Enhanced engine and all other dependencies are bundled inside the zip.

---

## Usage

### Toolbar button vs. dropdown menu

The **振り仮名** toolbar button has two parts:

- **Main button click** — runs the currently configured Tile Action (default: Furigana)
- **Dropdown arrow ▾** — always shows all three commands regardless of the Tile Action setting

To change which feature the main button launches: **Preferences → Plugins → FuriganaRuby → Customize plugin → Tile Action**.

---

### 振り仮名 — Furigana (Ruby)

#### Choosing a furigana engine

The **Edit Ruby…** dialog lets you choose between two engines:

| Engine | Accuracy | Setup |
|--------|----------|-------|
| **Enhanced** (default) | Good — handles common conjugation patterns | Built-in, no download |
| **High-accuracy** | Best — full morphological analysis | ~40 MB one-time download via the dialog |

The Enhanced engine is sufficient for most books. The High-accuracy engine (SudachiPy) is recommended for literary fiction, archaic vocabulary, or books where verb conjugations are consistently misread.

> **Why conjugation matters:** A naive engine maps each kanji to its most common reading and gets inflected forms wrong — e.g. 放たれる might be misread because it doesn't recognise the passive form of 放つ. The High-accuracy engine identifies the dictionary form of each word first, then derives the reading deterministically.

#### Adding furigana

1. Select one or more Japanese EPUB books in your library
2. Click the **振り仮名** main button, or dropdown ▾ → **Edit Ruby…**
3. Choose your engine (Enhanced or High-accuracy)
4. Tick the JLPT levels you want annotated:

   | Level | Example kanji |
   |-------|--------------|
   | N5 | 日・人・年・大・国 |
   | N4 | 家・花・魚・旅・運 |
   | N3 | 悲・祭・橋・商・泳 |
   | N2 | 握・偉・滑・褐・謙 |
   | N1 | 唖・崖・嫌・嗅・蔽 |

5. Click **Add Ruby** — processing takes a few seconds per book

**Quick presets:** None · N1 · N1–N2 · N1–N3 ★ · N1–N4 · All

#### Up-to-date detection

Books that have already been annotated with the exact same JLPT levels as your current selection are marked **Up to date** and their checkboxes are hidden automatically. Change the level selection and the dialog immediately re-evaluates which books need reprocessing.

#### Removing furigana

Open **Edit Ruby…** and untick levels (or all), then **Add Ruby**. Only auto-generated ruby (blue) is removed — publisher ruby is never touched.

#### Reading in the Calibre viewer

A floating toggle pill appears in the **bottom-left corner** (bottom-right for horizontal-text books):

| Icon | Label | Effect |
|------|-------|--------|
| 🈳 | すべて | Show all ruby (publisher + auto) |
| 📖 | 出版社 | Show publisher ruby only |
| 🈚 | 非表示 | Hide all ruby |

**To reveal the toggle:** move the mouse (or tap on mobile) — it fades to near-invisible when idle so it never obscures text.

**Keyboard shortcuts:** `R` · `F7` · `Cmd+Shift+F` (Mac) / `Ctrl+Shift+F` (Win/Linux)

#### Reading via the browser content server

The toggle works identically in any browser — open Calibre's content server at `http://<your-ip>:8080` and read from any device on your local network.

---

### 繁 — Chinese S↔T Conversion

1. Select one or more Chinese EPUB, HTML, FB2, or TXT books
2. Click the **振り仮名** main button (if Tile Action is set to Chinese S↔T), or dropdown ▾ → **Convert Chinese S↔T…**
3. The dialog detects each book's current script (Simplified / Traditional) and auto-checks books that need conversion. Books already in the target are unchecked and labelled accordingly.
4. Choose a direction and variant:

   | Direction | Variant | Use case |
   |-----------|---------|----------|
   | S → T | `s2twp` ★ | Taiwan Traditional — phrase-level vocabulary (recommended) |
   | S → T | `s2tw` | Taiwan Traditional — character-level only |
   | S → T | `s2hk` | Hong Kong Traditional 港式繁體 |
   | S → T | `s2t` | Generic Traditional |
   | T → S | *(fixed)* | Mainland China Simplified — always uses `t2s` |

5. **Metadata only** checkbox (on by default): books already in the target script receive only a title/author update; books not yet converted receive full content conversion. Title and author are always updated for all processed books.
6. Click **Apply** — a summary reports how many books were converted, skipped, or timed out.

> **Tip:** The dialog shows each book's detected script in a sub-label (`Simplified`, `Traditional`, or `⚠ mismatch` when the title script differs from the content). Use this to spot books that are already in the wrong script before applying.

---

### ↔ — Text Direction Conversion

1. Select one or more CJK EPUB books
2. Click the **振り仮名** main button (if Tile Action is set to Text Direction), or dropdown ▾ → **Text Direction…**
3. The dialog shows each book's current direction. For a single vertical book it pre-selects **V → H** automatically.
4. Choose target direction: **Horizontal** or **Vertical**
5. Click **Convert**

What the converter handles automatically:

- CSS `writing-mode` across all stylesheets and inline styles
- OPF `page-progression-direction` metadata
- **Tate-chu-yoko** — numbers and short Latin runs are wrapped in `text-combine-upright` so they render upright in vertical columns, and unwrapped cleanly when converting back
- **Punctuation normalisation** — Western quotes `"…"` `'…'` → CJK corner brackets `「…」` `『…』`; bare ASCII periods → ideographic full stops `。`; tab characters → ideographic spaces `　`
- Ruby toggle button repositioned automatically (bottom-left for vertical, bottom-right for horizontal)

---

## Visual design

| Colour | Meaning |
|--------|---------|
| **Black** ruby | Publisher-added (hand-verified, always trusted) |
| **Blue** ruby | Auto-generated by the plugin |

---

## Accuracy

Accuracy depends on which engine you use.

### Enhanced engine (built-in default)

| Content | Typical accuracy |
|---------|-----------------|
| Common vocabulary | ~95% |
| Conjugated verb forms | ~85% |
| Literary / archaic vocab | ~80% |
| Place names | ~80% |
| Character names (人名) | ~70% |
| Creative readings (当て字) | Low — publisher ruby wins |

### High-accuracy engine (SudachiPy)

| Content | Typical accuracy |
|---------|-----------------|
| Common vocabulary | ~98% |
| Conjugated verb forms | ~95% |
| Literary / archaic vocab | ~90% |
| Place names | ~85% |
| Character names (人名) | ~75% |
| Creative readings (当て字) | Low — publisher ruby wins |

> Character names and creative readings (当て字) are inherently unpredictable — no open-source engine can reliably guess author-invented or culturally specific readings. Publisher-supplied ruby always takes priority over auto-generated readings for those words.

---

## Changelog

### v1.7.0
**New: Viewer toggle (optional)**
- The in-viewer toggle button (🈳/📖/🈚) is now opt-in (default off). Enable it per-book run via the Options panel or as the auto-import default in Settings
- The toggle setting is saved immediately when you click **Save** in the Options panel — no need to process a book first
- Books with CSS but no toggle JS show **Toggle missing** in orange; running Add Ruby repairs them automatically

**New: Options panel in Ruby dialog**
- JLPT levels, Viewer toggle, and Furigana engine are consolidated into a single collapsible **Options** section
- Collapsed state shows a one-line summary: `N1–N3 · Toggle in Viewer off · Enhanced`
- **Customize** expands; **Save** commits all settings to prefs and collapses
- Quick-select presets appear at the top of the levels list
- Engine change now re-evaluates up-to-date books — books processed with a different engine reappear as processable

**New: Plugin-wide logging & diagnostics**
- A rolling log file (`furigana_ruby_log.txt`) is written automatically to Calibre's config directory — records plugin startup, processing results, settings saves, and SudachiPy downloads
- **Check for Updates** dialog now includes a bug-report section: **Open Diagnosis** (full report preview), **Copy Diagnosis** (copies to clipboard), **Open Log Folder** (reveals log file selected in Finder/Explorer)

**Bug fixes**
- Fixed: after processing completes, book checkboxes were sometimes left in a disabled-but-visible state where direct clicks did nothing but the header checkbox still worked
- Fixed: "Nothing to do" was incorrectly shown when the only needed action was injecting the viewer toggle JS into an already-annotated book
- Fixed: SudachiPy health check and daemon startup on environments where Python warnings are treated as errors (`dict_type` deprecation now silenced correctly)
- Fixed: SudachiPy subprocess encoding on Windows — all calls now use UTF-8 explicitly; Windows Python Launcher (`py`) tried first in discovery; console window no longer flashes

---

### v1.6.2
**Bug fixes**
- **Settings not rendering correctly after save** — the Settings dialog now correctly reads saved values on all Calibre install types (portable, non-default location, Windows custom path). Previously, settings were saved correctly but the dialog always showed defaults on reopen due to a hardcoded config path that didn't account for non-standard installs
- **SudachiPy re-download failing** — the Download/Re-download button now wipes the existing install directory before downloading fresh, preventing a corrupted or partial prior install from blocking the re-download. Added `--prefer-binary` flag to avoid build-tool failures on systems without compilers

---

### v1.6.1
**New: JLPT level tracking**
- The EPUB now stores which JLPT levels were used when annotating (`data-levels` in the CSS tag, alongside the existing engine ID)
- Books already annotated with the exact same levels as your current selection are marked **Up to date** and their checkboxes are hidden automatically on dialog open
- Two-line sub-info per book: line 1 shows language and publisher ruby count; line 2 (auto ruby books only) shows auto ruby count, levels used, and engine
- Changing the JLPT selection via Customize immediately re-evaluates all books — previously done books whose stored levels no longer match become checkable again
- The **Customize** link is disabled while processing runs and re-enabled on completion
- After processing, done-book checkboxes hide and **Add Ruby** disables automatically — no close-and-reopen needed

**Bug fixes**
- Individual book checkboxes can now be toggled independently — the header checkbox no longer interfered when some books were already up to date
- Book sub-info labels no longer wrap mid-line (e.g. "Japanese (日本語) ·" was splitting across lines)

---

### v1.6.0
**New: Pluggable furigana engine architecture**
- **Enhanced engine** (built-in, new default) — pre-processes conjugated verb forms before passing to pykakasi; fixes common passive/potential/causative misreadings without any download; replaces raw pykakasi as the baseline for all users
- **High-accuracy engine** (optional ~40 MB download) — powered by SudachiPy; full morphological analysis; identifies dictionary forms and conjugation types before reading lookup; consistently accurate on literary and inflected vocabulary
- Engine selection shown in the **Edit Ruby…** dialog with inline download, status, and version display
- Engine ID stored in EPUB so the dialog can detect books processed with an older or different engine

**UI improvements**
- JLPT panel is now collapsible (rebuilt on each toggle — avoids Qt visibility bugs on macOS)
- Full dialog scroll so expanding the JLPT panel never squeezes other content
- Long book titles now wrap to a second line instead of being cut off; Status column stays fully visible
- Non-Japanese books (Chinese, Korean) now appear in the S↔T dialog table (dimmed, no checkbox, "Not applicable") instead of being hidden from the list
- Menu order: Edit Ruby → Convert Chinese S↔T → Text Direction
- "Convert Layout" renamed to **Text Direction**

---

### v1.5.1
- Settings modal is now resizable and scrollable — matches the Preferences entry point
- Unchecking **Auto Add Ruby** in Settings now visually disables the annotation level checkboxes

---

### v1.5.0
**New: Tile Action — configurable main toolbar button**
- The main **振り仮名** button can now be set to open Furigana, Chinese S↔T, or Text Direction — configured under **Preferences → Plugins → FuriganaRuby → Customize plugin → Tile Action**
- Button icon and label update immediately when the setting changes

**S↔T dialog improvements**
- **Metadata-only mode** (on by default): books already in the target script get only their title and author updated, skipping a redundant full content pass; books not yet converted still receive full conversion
- Per-book script detection now shows title script separately from content script, with a `⚠` flag when they differ
- **Per-book timeout** — each book has a 5-minute processing limit; timed-out books are marked and reported in the summary without blocking the remaining queue
- Title and author are now always updated for all processed books regardless of the metadata-only setting

**Bug fix**
- Bundled dependencies no longer include `.so` / `.dylib` / `.pyd` binaries, fixing a crash on Intel Macs caused by arm64 binaries built on Apple Silicon

---

### v1.4.7
- Enlarged the result summary text area in all three dialogs for better readability on longer book lists

---

### v1.4.6
**Bug fix**
- Fixed **Keep original as ORIGINAL\_EPUB** not being saved in manual single-book operations (regression introduced in v1.4.0)

---

### v1.4.5
**New: Script classification cache**
- After S↔T conversion, the resulting script (`zh-Hant` / `zh-Hans`) is cached per book
- On subsequent dialog opens, ambiguous language tags (bare `zh` or `en`) are resolved using the cache — avoids a spurious "unknown" label on books already converted once

---

### v1.4.4
**New: dc:language persistence**
- S↔T conversion now writes `zh-Hant` or `zh-Hans` back to the `dc:language` tag in the EPUB OPF, so the correct script is reflected in Calibre's metadata and future script detection

---

### v1.4.3
**Bug fix**
- Fixed `deps_loader` failing to locate the plugin zip when running outside Calibre (e.g. from the standalone [calibre-monitor](https://github.com/tobethesidekick/calibre-monitor) script) — it now checks the standard per-platform Calibre preferences directory as a fallback

---

### v1.4.2
- Added **📖 Open in Viewer** button to the S↔T and orientation dialogs (visible when a single book is selected)
- Sub-info line in all dialogs now shows language and format

---

### v1.4.1
**Unified ruby dialog**
- **Edit Ruby…** now uses a single dialog for both single-book and bulk operations — the same interface handles any number of selected books
- Plugin renamed from "Furigana Ruby" to "振り仮名 Ruby & More" to reflect the expanded feature set

---

### v1.4.0
**New: Preferences panel — Auto Import & keep original**

Settings are now configured inside Calibre via **Preferences → Plugins → FuriganaRuby → Customize plugin**, so there is no need to edit config files manually.

**When Modifying Books**
- New **Keep original as ORIGINAL\_EPUB** option: before any modification (ruby annotation, Chinese S↔T conversion, layout conversion), the unmodified file is saved as the `ORIGINAL_EPUB` format in your Calibre library — visible in the book's format list and deletable individually
- Applies to all manual single-book operations that change the EPUB

**Auto Import** (requires [calibre-monitor](https://github.com/tobethesidekick/calibre-monitor) background script)
- **Watch folders** — view and edit the folders the background monitor watches, without leaving Calibre
- **Auto Chinese conversion** — enable Simplified ↔ Traditional conversion on import; choose direction (S→T or T→S) and variant; syncs to `monitor_config.json` automatically on OK
- **Auto add ruby** — enable furigana annotation on import for Japanese EPUBs; choose which JLPT levels (N1–N5 + Unlisted); syncs to `monitor_config.json` automatically on OK
- Monitor status is shown at the top of the panel (running / not running)

---

### v1.3.0
**New: Simplified ↔ Traditional Chinese conversion**
- New **繁 Convert Chinese S↔T…** toolbar menu command — converts EPUB, HTML, FB2, and TXT books between Simplified and Traditional Chinese in one click
- 8 OpenCC conversion variants; opencc-python-reimplemented bundled

---

### v1.2.0
**New: Vertical typography fixes for horizontal-origin EPUBs**
- Tate-chu-yoko wrapping for numbers and short Latin runs
- Punctuation normalisation (quotes, periods, tabs)

---

### v1.1.0
**New: EPUB Layout Converter**
- Added **↔ Text Direction…** in the toolbar menu — converts any CJK EPUB between vertical and horizontal text layout in one click

---

### v1.0.0
- Initial release: auto-generates furigana for Japanese EPUBs with JLPT-level filtering, publisher ruby preservation, and a 3-state viewer toggle (All / Publisher only / Off)

---

## Building from source

The source files live in this repository. The plugin zip is built by `setup_plugin.py`, which bundles pykakasi and its dependencies automatically.

```bash
# Prerequisites: Python 3.9+, internet connection (first run only)
git clone https://github.com/tobethesidekick/furigana-ruby.git
cd furigana-ruby

# Install build dependencies into a local cache
pip3 install pykakasi jaconv deprecated wrapt opencc-python-reimplemented --target deps_cache/

# Build FuriganaRuby.zip
python3 setup_plugin.py
# → outputs FuriganaRuby.zip (~5.8 MB)
```

Then install the zip into Calibre as described in the Installation section above.

> The High-accuracy (SudachiPy) engine is downloaded separately via the **Edit Ruby…** dialog — it is not bundled in the zip due to its size (~40 MB).

---

## Troubleshooting

**Plugin not visible in toolbar**
Right-click the Calibre toolbar → **Customize toolbar** → add **振り仮名** from the left panel.

**"No ruby found" on a processed book**
The book may not contain CJK text, or all kanji are common (N5/N4) and those levels were not selected. Try **Edit Ruby…** with *All* levels ticked.

**Toggle has no visible effect**
If a page has no auto-generated furigana (e.g. copyright/image pages), switching between *all* and *publisher* modes will look identical. Try a chapter page.

**Wrong readings on verb forms (e.g. passive, potential)**
This is a known limitation of the Enhanced engine for complex conjugations. Switch to the **High-accuracy engine** in the **Edit Ruby…** dialog — it uses full morphological analysis and handles conjugated forms correctly.

**Wrong readings on names**
No open-source engine can reliably guess character-specific name readings. Publisher-supplied ruby (if present) is always used instead of the auto reading for those words.

**Toggle button appears on the wrong side**
The button should be bottom-left for vertical text and bottom-right for horizontal text. If it's on the wrong side, the book was processed with an older version of the plugin. Fix: open **Edit Ruby…**, untick all levels → **Apply**, then re-tick your levels → **Apply**. The position is recalculated on re-add.

**After converting layout, toggle is still on the wrong side**
Running **↔ Text Direction…** updates the button position automatically. If you converted the EPUB by another tool outside Calibre, the position won't have been updated — fix it with a remove-then-re-add ruby cycle as above.

**Some numbers or Latin letters still appear sideways after converting to vertical**
This is expected for books converted with v1.1.0 or earlier. Re-run **↔ Text Direction…** with v1.2.0+ — the converter now wraps digits and Latin runs in `text-combine-upright` spans automatically.

**Periods appear as sideways dashes in vertical text**
The book was written for horizontal reading and uses ASCII `.` instead of the CJK ideographic full stop `。`. v1.2.0+ converts bare periods automatically during layout conversion. Re-run **↔ Text Direction…** to apply the fix.

---

## License

MIT
