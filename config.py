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
    from PyQt6.QtCore import Qt
    PYQT6 = True
except ImportError:
    from PyQt5.Qt import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QGroupBox,
        QComboBox, QFrame, QRadioButton, QListWidget, QPushButton,
        QLineEdit, QFileDialog, QDialog, QDialogButtonBox, QTextBrowser,
        QSizePolicy, Qt,
    )
    PYQT6 = False

from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/furigana_ruby')
prefs.defaults['annotate_levels']       = ['N1', 'N2', 'N3']
prefs.defaults['default_mode']          = 'all'
prefs.defaults['show_toggle_btn']       = True
prefs.defaults['s2t_variant']           = 's2twp'
prefs.defaults['t2s_variant']           = 't2s'
prefs.defaults['keep_original']         = False
prefs.defaults['auto_chinese_enabled']  = False
prefs.defaults['auto_chinese_direction']= 's2t'
prefs.defaults['auto_ruby_enabled']     = False
prefs.defaults['auto_ruby_levels']      = ['N1', 'N2', 'N3']
prefs.defaults['monitor_config_path']   = ''


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

        chinese_sub = QVBoxLayout()
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

        imp_layout.addLayout(chinese_sub)

        self._chinese_sub_widgets = [chinese_fmt_lbl, self._rb_s2t, self._rb_t2s,
                                     self._variant_combo, self._t2s_static_lbl, self._var_lbl]
        self._chinese_cb.toggled.connect(self._toggle_chinese_sub)
        self._toggle_chinese_sub(chinese_enabled)

        _sep(imp_layout)

        # Auto Ruby
        self._ruby_cb = QCheckBox('Auto add ruby on import  (Japanese books only)')
        _bold(self._ruby_cb)
        ruby_enabled = pj.get('auto_ruby_enabled', mc.get('auto_ruby_enabled', False))
        self._ruby_cb.setChecked(ruby_enabled)
        imp_layout.addWidget(self._ruby_cb)

        ruby_sub = QVBoxLayout()
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

        imp_layout.addLayout(ruby_sub)

        self._ruby_sub_widgets = (
            [ruby_fmt_lbl, ruby_levels_lbl] +
            list(self._ruby_level_cbs.values())
        )
        self._ruby_cb.toggled.connect(self._toggle_ruby_sub)
        self._toggle_ruby_sub(ruby_enabled)

        imp_group.setLayout(imp_layout)
        outer.addWidget(imp_group)
        outer.addStretch()

    # ── Slots ─────────────────────────────────────────────────────

    def _toggle_chinese_sub(self, on):
        for w in self._chinese_sub_widgets:
            w.setEnabled(on)

    def _toggle_ruby_sub(self, on):
        for w in self._ruby_sub_widgets:
            w.setEnabled(on)

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
        keep_orig     = self._rb_keep.isChecked()
        chinese_on    = self._chinese_cb.isChecked()
        chinese_dir   = 's2t' if self._rb_s2t.isChecked() else 't2s'
        variant_val   = self._variant_combo.currentData() or ''
        ruby_on       = self._ruby_cb.isChecked()
        ruby_levels   = [l for l, cb in self._ruby_level_cbs.items() if cb.isChecked()]

        s2t_var = variant_val if chinese_dir == 's2t' else prefs.get('s2t_variant', 's2twp')

        # Save to JSONConfig (plugin reads this for manual operations)
        prefs['keep_original']          = keep_orig
        prefs['auto_chinese_enabled']   = chinese_on
        prefs['auto_chinese_direction'] = chinese_dir
        prefs['s2t_variant']            = s2t_var
        prefs['auto_ruby_enabled']      = ruby_on
        prefs['auto_ruby_levels']       = ruby_levels

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
