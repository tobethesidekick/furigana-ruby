"""
config.py  v4 — settings dialog matching plugin UI screenshot
"""

import os
import json
import subprocess
from pathlib import Path

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QGroupBox,
        QComboBox, QFrame, QRadioButton, QListWidget, QPushButton,
        QLineEdit, QFileDialog, QDialog, QDialogButtonBox, QTextBrowser,
        QSizePolicy,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    PYQT6 = True
except ImportError:
    from PyQt5.Qt import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QGroupBox,
        QComboBox, QFrame, QRadioButton, QListWidget, QPushButton,
        QLineEdit, QFileDialog, QDialog, QDialogButtonBox, QTextBrowser,
        QSizePolicy, Qt, QThread, pyqtSignal,
    )
    PYQT6 = False

from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/furigana_ruby')
prefs.defaults['annotate_levels']       = ['N1', 'N2', 'N3']
prefs.defaults['default_mode']          = 'all'
prefs.defaults['show_toggle_btn']       = True
prefs.defaults['s2t_variant']           = 's2twp'
prefs.defaults['t2s_variant']           = 't2s'
prefs.defaults['tile_action']           = 'ruby'
prefs.defaults['keep_original']         = False
prefs.defaults['auto_chinese_enabled']  = False
prefs.defaults['auto_chinese_direction']= 's2t'
prefs.defaults['auto_ruby_enabled']     = False
prefs.defaults['auto_ruby_levels']      = ['N1', 'N2', 'N3']
prefs.defaults['monitor_config_path']   = ''
prefs.defaults['manual_engine']         = 'enhanced'
prefs.defaults['auto_engine']           = 'enhanced'
prefs.defaults['include_viewer_toggle'] = False


JLPT_LEVELS = [
    ('N1',       'N1 — Rare / literary kanji',          True),
    ('N2',       'N2 — Advanced kanji',                 True),
    ('N3',       'N3 — Intermediate kanji  ★',          True),
    ('N4',       'N4 — Basic kanji  (学、週、料理…)',   False),
    ('N5',       'N5 — Elementary kanji  (日、人、山…)', False),
    ('unlisted', 'Unlisted — Kanji not in any JLPT list', False),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_raw_plugin_json():
    """Read plugin prefs directly from the JSON file, bypassing JSONConfig caching."""
    import sys
    # Prefer Calibre's own config_dir — correct for portable installs, non-standard
    # locations, and all platforms. Fall back to hardcoded paths only when running
    # outside Calibre (e.g. standalone tests).
    try:
        from calibre.utils.config import config_dir
        p = Path(config_dir) / 'plugins' / 'furigana_ruby.json'
    except ImportError:
        if sys.platform == 'darwin':
            p = Path.home() / 'Library/Preferences/calibre/plugins/furigana_ruby.json'
        elif sys.platform.startswith('linux'):
            p = Path.home() / '.config/calibre/plugins/furigana_ruby.json'
        else:
            p = Path.home() / 'AppData/Roaming/calibre/plugins/furigana_ruby.json'
    try:
        if p.exists():
            with open(p, encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _find_monitor_config():
    """Return path to monitor_config.json, or '' if not found."""
    stored = prefs.get('monitor_config_path', '')
    if stored and os.path.isfile(stored):
        return stored
    candidates = [
        Path.home() / 'Documents/ScriptForCalibre/CalibreMonitor/monitor_config.json',
        Path.home() / 'Documents/CalibreMonitor/monitor_config.json',
        Path.home() / 'Documents/ClaudeProjects/calibre-monitor/monitor_config.json',
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ''


def _load_monitor_config(path):
    if path and os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_monitor_config(path, data):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _is_monitor_running():
    try:
        r = subprocess.run(['pgrep', '-f', 'calibre_monitor.py'],
                           capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def _sep(parent_layout):
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine if PYQT6 else QFrame.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken if PYQT6 else QFrame.Sunken)
    parent_layout.addWidget(line)


# ── ConfigWidget ──────────────────────────────────────────────────────────────

class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._monitor_path = _find_monitor_config()
        mc = _load_monitor_config(self._monitor_path)
        pj = _load_raw_plugin_json()   # authoritative current values

        outer = QVBoxLayout()
        outer.setContentsMargins(8, 8, 8, 8)
        self.setLayout(outer)

        # ── Tile Action ───────────────────────────────────────────
        tile_group = QGroupBox('Tile Action')
        tile_layout = QVBoxLayout()
        tile_layout.setSpacing(6)

        tile_note = QLabel('Choose what happens when you click the main toolbar button.')
        tile_note.setWordWrap(True)
        tile_layout.addWidget(tile_note)

        _sep(tile_layout)

        self._rb_tile_ruby  = QRadioButton('Furigana (Ruby)')
        self._rb_tile_zh    = QRadioButton('Chinese S↔T Conversion')
        self._rb_tile_dir   = QRadioButton('Text Direction')
        tile_action = pj.get('tile_action', 'ruby')
        self._rb_tile_ruby.setChecked(tile_action == 'ruby')
        self._rb_tile_zh.setChecked(tile_action == 'chinese')
        self._rb_tile_dir.setChecked(tile_action == 'direction')
        tile_layout.addWidget(self._rb_tile_ruby)
        tile_layout.addWidget(self._rb_tile_zh)
        tile_layout.addWidget(self._rb_tile_dir)

        tile_group.setLayout(tile_layout)
        outer.addWidget(tile_group)

        # ── When Modifying Books ──────────────────────────────────
        mod_group = QGroupBox('When Modifying Books')
        mod_layout = QVBoxLayout()
        mod_layout.setSpacing(6)

        note = QLabel('Applies to all operations: ruby, Chinese S↔T, text direction, and auto-import.')
        note.setWordWrap(True)
        mod_layout.addWidget(note)

        _sep(mod_layout)

        self._rb_replace = QRadioButton('Replace original (saves space, no recovery)')
        self._rb_keep    = QRadioButton('Keep original as ORIGINAL_EPUB (doubles storage, recoverable via Calibre)')
        keep_orig = pj.get('keep_original', mc.get('keep_original', False))
        self._rb_replace.setChecked(not keep_orig)
        self._rb_keep.setChecked(keep_orig)
        mod_layout.addWidget(self._rb_replace)
        mod_layout.addWidget(self._rb_keep)

        orig_note = QLabel('<small><i>ORIGINAL_EPUB copies appear in the book\'s format list and can be deleted individually.</i></small>')
        orig_note.setWordWrap(True)
        orig_note.setContentsMargins(20, 0, 0, 0)   # align with label, past radio button
        mod_layout.addWidget(orig_note)

        mod_group.setLayout(mod_layout)
        outer.addWidget(mod_group)

        # ── Auto Import ───────────────────────────────────────────
        imp_group = QGroupBox('Auto Import')
        imp_layout = QVBoxLayout()
        imp_layout.setSpacing(6)

        # Status row
        status_row = QHBoxLayout()
        running = _is_monitor_running()
        if running:
            status_lbl = QLabel('<b>Folder monitoring is enabled — watchdog is working</b>')
        else:
            status_lbl = QLabel('Folder monitoring is not running')
        status_row.addWidget(status_lbl)
        status_row.addStretch()
        instr_btn = QPushButton('Show Instruction')
        instr_btn.setFlat(True)
        instr_btn.setStyleSheet('QPushButton { color: #0066cc; border: none; text-decoration: underline; }')
        instr_btn.setCursor(Qt.CursorShape.PointingHandCursor if PYQT6 else Qt.PointingHandCursor)
        instr_btn.clicked.connect(self._show_instruction)
        status_row.addWidget(instr_btn)
        imp_layout.addLayout(status_row)

        _sep(imp_layout)

        # Watch Folders
        wf_lbl = QLabel('<b>Watch Folders</b>')
        imp_layout.addWidget(wf_lbl)

        self._folder_list = QListWidget()
        self._folder_list.setMaximumHeight(80)
        watch_folders = pj.get('watch_folders', mc.get('watch_folders', []))
        for folder in watch_folders:
            self._folder_list.addItem(folder)
        imp_layout.addWidget(self._folder_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton('Add Folder…')
        add_btn.clicked.connect(self._add_folder)
        rem_btn = QPushButton('Remove Selected')
        rem_btn.clicked.connect(self._remove_folder)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)
        btn_row.addStretch()
        imp_layout.addLayout(btn_row)

        if not self._monitor_path:
            no_cfg_lbl = QLabel(
                '<small><i>monitor_config.json not found — watch folder changes will not be saved. '
                'Click "Show Instruction" to set up the monitor script.</i></small>'
            )
            no_cfg_lbl.setWordWrap(True)
            no_cfg_lbl.setStyleSheet('color: #888;')
            imp_layout.addWidget(no_cfg_lbl)

        # Done folder
        done_row = QHBoxLayout()
        done_row.addWidget(QLabel('Move original file after import to subfolder:'))
        self._done_edit = QLineEdit(mc.get('done_folder', '_imported'))
        self._done_edit.setMaximumWidth(150)
        done_row.addWidget(self._done_edit)
        done_row.addWidget(QLabel('(blank = leave in place)'))
        done_row.addStretch()
        imp_layout.addLayout(done_row)

        _sep(imp_layout)

        # Auto Chinese
        self._chinese_cb = QCheckBox('Auto Chinese conversion on import')
        _bold(self._chinese_cb)
        chinese_enabled = pj.get('auto_chinese_enabled',
                          pj.get('auto_s2t_enabled',
                          mc.get('auto_chinese_enabled', False)))
        self._chinese_cb.setChecked(chinese_enabled)
        imp_layout.addWidget(self._chinese_cb)

        chinese_sub_container = QWidget()
        chinese_sub_container.setStyleSheet(
            'QRadioButton:disabled { color: #aaaaaa; }'
            ' QLabel:disabled { color: #aaaaaa; }'
            ' QComboBox:disabled { color: #aaaaaa; }'
        )
        chinese_sub = QVBoxLayout(chinese_sub_container)
        chinese_sub.setContentsMargins(20, 0, 0, 4)
        chinese_sub.setSpacing(4)

        chinese_fmt_lbl = QLabel('<small>Supported formats: EPUB, HTML, TXT, FB2</small>')
        chinese_sub.addWidget(chinese_fmt_lbl)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel('Direction:'))
        self._rb_s2t = QRadioButton('Simplified → Traditional')
        self._rb_t2s = QRadioButton('Traditional → Simplified')
        direction = pj.get('auto_chinese_direction',
                   pj.get('auto_s2t_direction',
                   mc.get('auto_chinese_direction', 's2t')))
        self._rb_s2t.setChecked(direction == 's2t')
        self._rb_t2s.setChecked(direction != 's2t')
        dir_row.addWidget(self._rb_s2t)
        dir_row.addWidget(self._rb_t2s)
        dir_row.addStretch()
        chinese_sub.addLayout(dir_row)

        var_row = QHBoxLayout()
        self._var_lbl = QLabel('Variant:')
        var_row.addWidget(self._var_lbl)
        self._variant_combo = QComboBox()
        self._t2s_static_lbl = QLabel('Mainland China Simplified (standard)')
        self._t2s_static_lbl.setStyleSheet('color: #545454;')
        self._s2t_variant_saved = pj.get('s2t_variant',
                                  pj.get('auto_s2t_variant',
                                  mc.get('s2t_variant', 's2twp')))
        self._rb_s2t.toggled.connect(self._refresh_variants)
        self._refresh_variants()
        var_row.addWidget(self._variant_combo)
        var_row.addWidget(self._t2s_static_lbl)
        var_row.addStretch()
        chinese_sub.addLayout(var_row)

        imp_layout.addWidget(chinese_sub_container)

        self._chinese_sub_container = chinese_sub_container
        self._chinese_cb.toggled.connect(self._toggle_chinese_sub)
        self._toggle_chinese_sub(chinese_enabled)

        _sep(imp_layout)

        # Auto Ruby
        self._ruby_cb = QCheckBox('Auto add ruby on import  (Japanese books only)')
        _bold(self._ruby_cb)
        ruby_enabled = pj.get('auto_ruby_enabled', mc.get('auto_ruby_enabled', False))
        self._ruby_cb.setChecked(ruby_enabled)
        imp_layout.addWidget(self._ruby_cb)

        ruby_sub_container = QWidget()
        ruby_sub_container.setStyleSheet(
            'QCheckBox:disabled { color: #aaaaaa; }'
            ' QLabel:disabled { color: #aaaaaa; }'
            ' QRadioButton:disabled { color: #aaaaaa; }'
        )
        ruby_sub = QVBoxLayout(ruby_sub_container)
        ruby_sub.setContentsMargins(20, 0, 0, 4)
        ruby_sub.setSpacing(3)

        ruby_fmt_lbl = QLabel('<small>Supported formats: EPUB only</small>')
        ruby_sub.addWidget(ruby_fmt_lbl)

        ruby_levels_lbl = QLabel('Annotation levels:')
        ruby_sub.addWidget(ruby_levels_lbl)

        saved_ruby_levels = set(pj.get('auto_ruby_levels',
                             mc.get('auto_ruby_levels', ['N1', 'N2', 'N3'])))
        self._ruby_level_cbs = {}
        for level, label, bold in JLPT_LEVELS:
            cb = QCheckBox(label)
            if bold:
                _bold(cb)
            cb.setChecked(level in saved_ruby_levels)
            self._ruby_level_cbs[level] = cb
            ruby_sub.addWidget(cb)

        _sep(ruby_sub)

        # Viewer toggle (between levels and engine, same indent as engine)
        auto_toggle_hdr = QLabel('<b>Viewer toggle</b>')
        ruby_sub.addWidget(auto_toggle_hdr)

        toggle_note = QLabel(
            'Cycles through: All selected levels · Publisher only · None')
        toggle_note.setWordWrap(True)
        toggle_note.setStyleSheet('color: #555;')
        ruby_sub.addWidget(toggle_note)

        self._viewer_toggle_cb = QCheckBox('Include toggle button in Calibre Viewer')
        viewer_toggle_saved = pj.get('include_viewer_toggle', False)
        self._viewer_toggle_cb.setChecked(viewer_toggle_saved)
        ruby_sub.addWidget(self._viewer_toggle_cb)

        _sep(ruby_sub)

        # Auto import engine (inside ruby sub so it disables with the checkbox)
        auto_eng_hdr = QLabel('<b>Furigana engine</b>')
        ruby_sub.addWidget(auto_eng_hdr)

        self._rb_auto_enhanced = QRadioButton('Enhanced (built-in)')
        self._rb_auto_high     = QRadioButton('High-accuracy (SudachiPy)')
        auto_engine_pref = pj.get('auto_engine', 'enhanced')
        self._rb_auto_enhanced.setChecked(auto_engine_pref != 'high_accuracy')
        self._rb_auto_high.setChecked(auto_engine_pref == 'high_accuracy')
        ruby_sub.addWidget(self._rb_auto_enhanced)

        try:
            from calibre_plugins.furigana_ruby.engines.sudachi import (
                get_status as _s_get_status, SudachiStatus)
        except ImportError:
            from engines.sudachi import (
                get_status as _s_get_status, SudachiStatus)

        self._cfg_sudachi_status = [None]
        self._cfg_sudachi_ver    = [None]

        def _cfg_refresh_sudachi():
            s, v = _s_get_status()
            self._cfg_sudachi_status[0] = s
            self._cfg_sudachi_ver[0]    = v
            return s, v

        _cfg_refresh_sudachi()

        self._cfg_eng_status_lbl = QLabel()
        self._cfg_eng_status_lbl.setStyleSheet('color: #666; font-size: 11px;')
        self._cfg_eng_dl_btn = QPushButton()
        self._cfg_eng_dl_btn.setMaximumWidth(160)

        high_eng_row = QHBoxLayout()
        high_eng_row.setContentsMargins(0, 0, 0, 0)
        high_eng_row.setSpacing(8)
        high_eng_row.addWidget(self._rb_auto_high)
        high_eng_row.addWidget(self._cfg_eng_status_lbl)
        high_eng_row.addWidget(self._cfg_eng_dl_btn)
        high_eng_row.addStretch()
        ruby_sub.addLayout(high_eng_row)

        self._cfg_eng_remove_btn = QPushButton('Remove SudachiPy…')
        self._cfg_eng_remove_btn.setFlat(True)
        self._cfg_eng_remove_btn.setStyleSheet(
            'QPushButton { color: #cc3300; border: none; '
            'text-decoration: underline; font-size: 11px; }'
            'QPushButton:hover { color: #990000; }')
        try:
            self._cfg_eng_remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        except AttributeError:
            self._cfg_eng_remove_btn.setCursor(Qt.PointingHandCursor)
        remove_eng_row = QHBoxLayout()
        remove_eng_row.setContentsMargins(0, 0, 0, 0)
        remove_eng_row.addWidget(self._cfg_eng_remove_btn)
        remove_eng_row.addStretch()
        ruby_sub.addLayout(remove_eng_row)

        self._cfg_dl_thread = [None]

        def _cfg_update_engine_ui():
            s = self._cfg_sudachi_status[0]
            v = self._cfg_sudachi_ver[0]
            installed = s in (SudachiStatus.READY, SudachiStatus.BROKEN,
                              SudachiStatus.CALIBRE_UPDATED)
            if s == SudachiStatus.READY:
                self._cfg_eng_status_lbl.setText(
                    f'SudachiPy {v} · ready' if v else 'ready')
                self._cfg_eng_dl_btn.setText('Re-download')
            elif s == SudachiStatus.CALIBRE_UPDATED:
                self._cfg_eng_status_lbl.setText('Unavailable — Calibre updated')
                self._cfg_eng_dl_btn.setText('Re-download to restore')
            elif s == SudachiStatus.BROKEN:
                self._cfg_eng_status_lbl.setText('Unavailable')
                self._cfg_eng_dl_btn.setText('Re-download')
            else:
                self._cfg_eng_status_lbl.setText('Not downloaded (~40 MB)')
                self._cfg_eng_dl_btn.setText('Download')
            self._cfg_eng_remove_btn.setVisible(installed)

        _cfg_update_engine_ui()

        class _CfgDownloadThread(QThread):
            done = pyqtSignal(bool, str)
            def run(self_t):
                try:
                    try:
                        from calibre_plugins.furigana_ruby.engines.sudachi import install
                    except ImportError:
                        from engines.sudachi import install
                    install()
                    self_t.done.emit(True, '')
                except Exception as e:
                    self_t.done.emit(False, str(e))

        def _cfg_on_download():
            self._cfg_eng_dl_btn.setEnabled(False)
            self._cfg_eng_status_lbl.setText('Downloading… (may take a minute)')
            t = _CfgDownloadThread()
            self._cfg_dl_thread[0] = t

            def _on_done(ok, err):
                _cfg_refresh_sudachi()
                self._cfg_eng_dl_btn.setEnabled(True)
                if ok:
                    _cfg_update_engine_ui()
                else:
                    # Show full error (up to 200 chars) so the user can see what went wrong
                    self._cfg_eng_status_lbl.setText(f'Download failed: {err[:200]}')
            t.done.connect(_on_done)
            t.start()

        self._cfg_eng_dl_btn.clicked.connect(_cfg_on_download)

        def _cfg_on_remove():
            dlg_r = QDialog(self)
            dlg_r.setWindowTitle('Remove SudachiPy?')
            dlg_r.setMinimumWidth(400)
            v_r = QVBoxLayout(dlg_r)
            v_r.addWidget(QLabel(
                'This will delete the SudachiPy engine (~40 MB).\n'
                'Both manual and auto-import engine settings will revert\n'
                'to Enhanced (built-in).'))
            v_r.addSpacing(8)
            rb_confirm = QRadioButton('Remove SudachiPy and revert to Enhanced')
            rb_keep    = QRadioButton('Keep SudachiPy')
            rb_keep.setChecked(True)
            v_r.addWidget(rb_confirm)
            v_r.addWidget(rb_keep)
            v_r.addSpacing(8)
            bb_r = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
                if PYQT6 else
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb_r.accepted.connect(dlg_r.accept)
            bb_r.rejected.connect(dlg_r.reject)
            v_r.addWidget(bb_r)
            accepted = (dlg_r.exec() if PYQT6 else dlg_r.exec_())
            ok_code  = (QDialog.DialogCode.Accepted if PYQT6 else QDialog.Accepted)
            if accepted != ok_code or not rb_confirm.isChecked():
                return
            try:
                from calibre_plugins.furigana_ruby.engines.sudachi import remove
            except ImportError:
                from engines.sudachi import remove
            remove()
            prefs['auto_engine']   = 'enhanced'
            prefs['manual_engine'] = 'enhanced'
            self._rb_auto_enhanced.setChecked(True)
            _cfg_refresh_sudachi()
            _cfg_update_engine_ui()

        self._cfg_eng_remove_btn.clicked.connect(_cfg_on_remove)

        def _cfg_on_diagnostics_UNUSED():
            self._cfg_diag_btn.setEnabled(False)
            self._cfg_diag_btn.setText('Running…')
            try:
                from calibre_plugins.furigana_ruby.engines.sudachi import (
                    generate_diagnostics)
            except ImportError:
                from engines.sudachi import generate_diagnostics
            try:
                report = generate_diagnostics()
            except Exception as e:
                report = f'Error generating diagnostics:\n{e}'
            finally:
                self._cfg_diag_btn.setEnabled(True)
                self._cfg_diag_btn.setText('📋 Diagnostics…')

            dlg_d = QDialog(self)
            dlg_d.setWindowTitle('SudachiPy Diagnostics')
            dlg_d.setMinimumWidth(560)
            dlg_d.resize(600, 420)
            v_d = QVBoxLayout(dlg_d)

            info_lbl = QLabel(
                'Copy this report and attach it to your bug ticket.')
            info_lbl.setWordWrap(True)
            v_d.addWidget(info_lbl)

            tb = QTextBrowser()
            tb.setPlainText(report)
            tb.setFont(
                tb.font().__class__(
                    'Courier' if not PYQT6 else 'Courier New', 10))
            v_d.addWidget(tb)

            copy_btn = QPushButton('Copy to Clipboard')

            def _do_copy():
                try:
                    from PyQt6.QtWidgets import QApplication
                except ImportError:
                    from PyQt5.Qt import QApplication
                QApplication.clipboard().setText(report)
                copy_btn.setText('✓ Copied!')

            copy_btn.clicked.connect(_do_copy)
            bb_d = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Close if PYQT6
                else QDialogButtonBox.Close)
            bb_d.rejected.connect(dlg_d.reject)

            btn_row_d = QHBoxLayout()
            btn_row_d.addWidget(copy_btn)
            btn_row_d.addStretch()
            btn_row_d.addWidget(bb_d)
            v_d.addLayout(btn_row_d)

            dlg_d.exec() if PYQT6 else dlg_d.exec_()

        # (Diagnostics moved to About dialog)

        imp_layout.addWidget(ruby_sub_container)

        self._ruby_sub_container = ruby_sub_container
        self._ruby_cb.toggled.connect(self._toggle_ruby_sub)
        self._toggle_ruby_sub(ruby_enabled)

        imp_group.setLayout(imp_layout)
        outer.addWidget(imp_group)
        outer.addStretch()

    # ── Slots ─────────────────────────────────────────────────────

    def _toggle_chinese_sub(self, on):
        self._chinese_sub_container.setEnabled(on)

    def _toggle_ruby_sub(self, on):
        self._ruby_sub_container.setEnabled(on)

    def _refresh_variants(self):
        going_s2t = self._rb_s2t.isChecked()
        self._variant_combo.setVisible(going_s2t)
        self._t2s_static_lbl.setVisible(not going_s2t)

        if going_s2t:
            try:
                from calibre_plugins.furigana_ruby.chinese_engine import VARIANTS_S2T
            except ImportError:
                from chinese_engine import VARIANTS_S2T
            self._variant_combo.clear()
            sel = 0
            for i, (v, label, *_) in enumerate(VARIANTS_S2T):
                self._variant_combo.addItem(label, v)
                if v == self._s2t_variant_saved:
                    sel = i
            self._variant_combo.setCurrentIndex(sel)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Watch Folder')
        if folder:
            self._folder_list.addItem(folder)

    def _remove_folder(self):
        for item in self._folder_list.selectedItems():
            self._folder_list.takeItem(self._folder_list.row(item))

    def _show_instruction(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('Auto Import — Setup Instructions')
        dlg.setMinimumWidth(520)
        dlg.resize(540, 380)
        layout = QVBoxLayout()
        dlg.setLayout(layout)

        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setHtml('''
<h3>Setting up automatic folder monitoring</h3>
<p>Auto-import uses a background Python script (<code>calibre_monitor.py</code>)
that watches your folders for new ebook files and imports them automatically.</p>

<h4>1 — Install dependencies</h4>
<pre>pip3 install watchdog</pre>

<h4>2 — Create your config file</h4>
<p>Copy <code>monitor_config.example.json</code> → <code>monitor_config.json</code>
and fill in your Calibre library path, calibredb path, and plugin_source path.</p>

<h4>3 — Test it</h4>
<pre>python3 /path/to/calibre_monitor.py</pre>
<p>Drop a file into the watch folder — you should see log output and a macOS notification.</p>

<h4>4 — Run at login (macOS Launch Agent)</h4>
<p>See the <b>README.md</b> in the <code>calibre-monitor</code> folder for the
full Launch Agent plist template.</p>

<h4>After setup</h4>
<p>Restart the monitor after saving any changes here so it picks up the new settings.</p>
''')
        layout.addWidget(tb)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close if PYQT6 else QDialogButtonBox.Close
        )
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        dlg.exec() if PYQT6 else dlg.exec_()

    # ── Save ──────────────────────────────────────────────────────

    def save_settings(self):
        tile_action = 'ruby' if self._rb_tile_ruby.isChecked() else \
                      'chinese' if self._rb_tile_zh.isChecked() else 'direction'
        keep_orig     = self._rb_keep.isChecked()
        chinese_on    = self._chinese_cb.isChecked()
        chinese_dir   = 's2t' if self._rb_s2t.isChecked() else 't2s'
        variant_val   = self._variant_combo.currentData() or ''
        ruby_on         = self._ruby_cb.isChecked()
        ruby_levels     = [l for l, cb in self._ruby_level_cbs.items() if cb.isChecked()]
        viewer_toggle   = self._viewer_toggle_cb.isChecked()

        s2t_var = variant_val if chinese_dir == 's2t' else prefs.get('s2t_variant', 's2twp')

        auto_engine = ('high_accuracy' if self._rb_auto_high.isChecked()
                       else 'enhanced')

        # Save to JSONConfig (plugin reads this for manual operations)
        prefs['tile_action']              = tile_action
        prefs['keep_original']            = keep_orig
        prefs['auto_chinese_enabled']     = chinese_on
        prefs['auto_chinese_direction']   = chinese_dir
        prefs['s2t_variant']              = s2t_var
        prefs['auto_ruby_enabled']        = ruby_on
        prefs['auto_ruby_levels']         = ruby_levels
        prefs['include_viewer_toggle']    = viewer_toggle
        prefs['auto_engine']              = auto_engine

        # Sync to monitor_config.json so the monitor script picks up changes
        if self._monitor_path:
            mc = _load_monitor_config(self._monitor_path) or {}
            mc['watch_folders']          = [
                self._folder_list.item(i).text()
                for i in range(self._folder_list.count())
            ]
            mc['done_folder']            = self._done_edit.text().strip()
            mc['keep_original']          = keep_orig
            mc['auto_chinese_enabled']   = chinese_on
            mc['auto_chinese_direction'] = chinese_dir
            mc['s2t_variant']            = s2t_var
            mc['auto_ruby_enabled']      = ruby_on
            mc['auto_ruby_levels']       = ruby_levels
            _save_monitor_config(self._monitor_path, mc)

        try:
            from calibre_plugins.furigana_ruby.plugin_logger import logger as _lg
        except ImportError:
            from plugin_logger import logger as _lg
        _lg.info(
            f'Settings saved — tile={tile_action} keep_orig={keep_orig} '
            f'ruby={ruby_on} levels={ruby_levels} toggle={viewer_toggle} '
            f'engine={auto_engine} chinese={chinese_on}')


# ── Utilities ─────────────────────────────────────────────────────────────────

def _bold(widget):
    f = widget.font()
    f.setBold(True)
    widget.setFont(f)


def _pref_or_mc(key, mc, default):
    """Read from JSONConfig first, fall back to monitor_config dict, then default."""
    stored = prefs.get(key)
    if stored is not None and stored != prefs.defaults.get(key):
        return stored
    return mc.get(key, default)
