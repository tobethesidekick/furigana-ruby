"""
config.py  v3 — per-JLPT-level checkboxes
"""

try:
    from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                  QCheckBox, QGroupBox, QComboBox, QFrame)
    from PyQt6.QtCore import Qt
except ImportError:
    from PyQt5.Qt import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                          QCheckBox, QGroupBox, QComboBox, QFrame, Qt)

from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/furigana_ruby')
prefs.defaults['annotate_levels']  = ['N1', 'N2', 'N3']   # default: N3+
prefs.defaults['default_mode']     = 'all'
prefs.defaults['show_toggle_btn']  = True
prefs.defaults['s2t_variant']      = 's2tw'   # default S→T variant
prefs.defaults['t2s_variant']      = 't2s'    # default T→S variant


class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)

        # ── JLPT Level selector ───────────────────────────────────
        jlpt_group = QGroupBox('Kanji Annotation Levels')
        jlpt_layout = QVBoxLayout()

        desc = QLabel(
            'Select which JLPT levels receive furigana.\n'
            'N5 = easiest (日、人、年…)   N1 = hardest   ✦ = recommended'
        )
        desc.setWordWrap(True)
        jlpt_layout.addWidget(desc)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine if hasattr(QFrame, 'Shape')
                           else QFrame.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken if hasattr(QFrame, 'Shadow')
                            else QFrame.Sunken)
        jlpt_layout.addWidget(line)

        current_levels = set(prefs['annotate_levels'])

        self._level_cbs = {}
        level_info = [
            ('N1', 'N1 — Rare / literary kanji (most obscure)', True),
            ('N2', 'N2 — Advanced kanji', True),
            ('N3', 'N3 — Intermediate kanji  ✦', True),
            ('N4', 'N4 — Basic kanji (学、週、料理…)', False),
            ('N5', 'N5 — Elementary kanji (日、人、山…)', False),
        ]

        for level, label_text, recommended in level_info:
            row = QHBoxLayout()
            cb = QCheckBox(label_text)
            cb.setChecked(level in current_levels)
            if recommended:
                cb.setStyleSheet('font-weight: bold;')
            self._level_cbs[level] = cb
            row.addWidget(cb)
            jlpt_layout.addLayout(row)

        # Quick-select buttons row
        btn_row = QHBoxLayout()
        btn_row.addWidget(QLabel('Quick select:'))

        presets = [
            ('N1 only',    {'N1'}),
            ('N1–N2',      {'N1','N2'}),
            ('N1–N3 ✦',   {'N1','N2','N3'}),
            ('N1–N4',      {'N1','N2','N3','N4'}),
            ('All levels', {'N1','N2','N3','N4','N5'}),
        ]

        try:
            from PyQt6.QtWidgets import QPushButton
        except ImportError:
            from PyQt5.Qt import QPushButton

        for label, levels in presets:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked, lvls=levels: self._apply_preset(lvls))
            btn_row.addWidget(btn)

        jlpt_layout.addLayout(btn_row)
        jlpt_group.setLayout(jlpt_layout)
        layout.addWidget(jlpt_group)

        # ── Viewer defaults ───────────────────────────────────────
        viewer_group = QGroupBox('Viewer Defaults')
        viewer_layout = QVBoxLayout()

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel('Default ruby display mode:'))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            'All ruby (publisher + auto)',
            'Publisher ruby only',
            'Hidden',
        ])
        mode_map = {'all': 0, 'publisher': 1, 'off': 2}
        self.mode_combo.setCurrentIndex(
            mode_map.get(prefs['default_mode'], 0)
        )
        mode_row.addWidget(self.mode_combo)
        viewer_layout.addLayout(mode_row)

        self.btn_cb = QCheckBox(
            'Show floating toggle button in viewer (bottom-right corner)'
        )
        self.btn_cb.setChecked(prefs['show_toggle_btn'])
        viewer_layout.addWidget(self.btn_cb)

        viewer_group.setLayout(viewer_layout)
        layout.addWidget(viewer_group)

        info = QLabel(
            '<i>Keyboard shortcut in viewer: <b>Cmd+Shift+R</b> (Mac) '
            '/ <b>Ctrl+Shift+R</b></i>'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Chinese conversion defaults ───────────────────────────
        chinese_group = QGroupBox('Chinese Conversion Defaults')
        chinese_layout = QVBoxLayout()

        from calibre_plugins.furigana_ruby.chinese_engine import VARIANTS_S2T, VARIANTS_T2S

        s2t_row = QHBoxLayout()
        s2t_row.addWidget(QLabel('Simplified → Traditional variant:'))
        self.s2t_combo = QComboBox()
        for variant, label, *_ in VARIANTS_S2T:
            self.s2t_combo.addItem(label, variant)
        cur_s2t = prefs['s2t_variant']
        for i, (v, *_) in enumerate(VARIANTS_S2T):
            if v == cur_s2t:
                self.s2t_combo.setCurrentIndex(i)
                break
        s2t_row.addWidget(self.s2t_combo)
        chinese_layout.addLayout(s2t_row)

        t2s_row = QHBoxLayout()
        t2s_row.addWidget(QLabel('Traditional → Simplified variant:'))
        self.t2s_combo = QComboBox()
        for variant, label, *_ in VARIANTS_T2S:
            self.t2s_combo.addItem(label, variant)
        cur_t2s = prefs['t2s_variant']
        for i, (v, *_) in enumerate(VARIANTS_T2S):
            if v == cur_t2s:
                self.t2s_combo.setCurrentIndex(i)
                break
        t2s_row.addWidget(self.t2s_combo)
        chinese_layout.addLayout(t2s_row)

        chinese_note = QLabel(
            '<small><i>s2tw / s2twp recommended for Taiwan ebooks. '
            'Phrase-level variants (s2twp, tw2sp) are slower but more accurate.</i></small>'
        )
        chinese_note.setWordWrap(True)
        chinese_layout.addWidget(chinese_note)

        chinese_group.setLayout(chinese_layout)
        layout.addWidget(chinese_group)

        layout.addStretch()

    def _apply_preset(self, levels):
        for level, cb in self._level_cbs.items():
            cb.setChecked(level in levels)

    def save_settings(self):
        selected = [lvl for lvl, cb in self._level_cbs.items() if cb.isChecked()]
        prefs['annotate_levels']  = selected
        modes = ['all', 'publisher', 'off']
        prefs['default_mode']     = modes[self.mode_combo.currentIndex()]
        prefs['show_toggle_btn']  = self.btn_cb.isChecked()
        prefs['s2t_variant']      = self.s2t_combo.currentData()
        prefs['t2s_variant']      = self.t2s_combo.currentData()

    def get_annotate_levels(self):
        """Return current set of selected levels."""
        return {lvl for lvl, cb in self._level_cbs.items() if cb.isChecked()}
