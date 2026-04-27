"""
action.py  v13
Unified ruby dialog:
  - One "Furigana (Ruby) Customization" dialog handles single and bulk book selection.
  - Level checkboxes at top; per-book sub-info (language, publisher count, auto count).
  - "Open in Viewer" shown dynamically only when exactly 1 eligible book is selected.
"""

import os
import tempfile

try:
    from PyQt6.QtWidgets import (QMenu, QProgressDialog, QApplication,
                                  QToolButton, QDialog, QVBoxLayout,
                                  QHBoxLayout, QCheckBox, QLabel,
                                  QGroupBox, QDialogButtonBox, QPushButton,
                                  QSizePolicy, QTextEdit, QTextBrowser,
                                  QComboBox, QRadioButton, QButtonGroup,
                                  QScrollArea, QWidget, QFrame)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QIcon, QAction, QPainter
    PYQT6 = True
except ImportError:
    from PyQt5.Qt import (QMenu, QProgressDialog, QApplication,
                           QToolButton, QDialog, QVBoxLayout,
                           QHBoxLayout, QCheckBox, QLabel,
                           QGroupBox, QDialogButtonBox, QPushButton,
                           QSizePolicy, QTextEdit, QTextBrowser,
                           QComboBox, QRadioButton, QButtonGroup,
                           QScrollArea, QWidget, QFrame, Qt, QThread,
                           pyqtSignal, QIcon, QAction, QPainter)
    PYQT6 = False

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, info_dialog, warning_dialog
from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/furigana_ruby')
prefs.defaults['annotate_levels']        = ['N1', 'N2', 'N3']
prefs.defaults['keep_original']          = False
prefs.defaults['auto_chinese_enabled']   = False
prefs.defaults['auto_chinese_direction'] = 's2t'
prefs.defaults['s2t_variant']            = 's2twp'
prefs.defaults['t2s_variant']            = 't2s'
prefs.defaults['auto_ruby_enabled']      = False
prefs.defaults['auto_ruby_levels']       = ['N1', 'N2', 'N3']

_ALL_LEVELS = {'N1', 'N2', 'N3', 'N4', 'N5', 'unlisted'}


# ── Chinese conversion worker ─────────────────────────────────────────────────

class ElidedLabel(QLabel):
    """
    A QLabel that elides text with '…' when it doesn't fit,
    and emits clicked() on mouse press so it can act as a
    clickable title alongside a QCheckBox.
    """
    clicked = pyqtSignal()

    def paintEvent(self, event):
        painter = QPainter(self)
        fm = self.fontMetrics()
        try:
            elide_mode = Qt.TextElideMode.ElideRight
            align      = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        except AttributeError:
            elide_mode = Qt.ElideRight
            align      = Qt.AlignLeft | Qt.AlignVCenter
        elided = fm.elidedText(self.text(), elide_mode, self.width())
        painter.drawText(self.rect(), align, elided)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class ChineseWorker(QThread):
    """
    Processes one book at a time (all its convertible formats).

    Signals
    -------
    book_started(book_id)              — fired just before a book begins
    book_finished(book_id, ok, msg)    — fired after all formats for a book complete
    finished(ok, results, traceback)   — fired when all books are done
        results = list of (book_id, fmt, tmp_path_or_None, error_or_None)
    """
    book_started  = pyqtSignal(int)             # book_id
    book_finished = pyqtSignal(int, bool, str)  # book_id, all_ok, summary_msg
    finished      = pyqtSignal(bool, list, str) # ok, results, traceback

    def __init__(self, tasks, variant):
        super().__init__()
        self.tasks   = tasks
        self.variant = variant

    def run(self):
        try:
            try:
                from calibre_plugins.furigana_ruby.chinese_engine import (
                    convert_epub_s2t, convert_txt_s2t,
                    convert_html_s2t, convert_fb2_s2t)
            except ImportError:
                from chinese_engine import (convert_epub_s2t, convert_txt_s2t,
                                            convert_html_s2t, convert_fb2_s2t)

            results = []

            for task in self.tasks:
                self.book_started.emit(task['book_id'])
                fmt_results = []   # (fmt, ok, error_str)

                # ── EPUB ──────────────────────────────────────
                if task['epub']:
                    tmp = tempfile.mktemp(suffix='.epub')
                    try:
                        convert_epub_s2t(task['epub'], tmp,
                                         variant=self.variant)
                        results.append((task['book_id'], 'EPUB', tmp, None))
                        fmt_results.append(('EPUB', True, ''))
                    except Exception as e:
                        try: os.unlink(tmp)
                        except: pass
                        results.append((task['book_id'], 'EPUB', None, str(e)))
                        fmt_results.append(('EPUB', False, str(e)))

                # ── HTML ──────────────────────────────────────
                if task.get('html'):
                    tmp = tempfile.mktemp(suffix='.html')
                    try:
                        convert_html_s2t(task['html'], tmp,
                                         variant=self.variant)
                        results.append((task['book_id'], 'HTML', tmp, None))
                        fmt_results.append(('HTML', True, ''))
                    except Exception as e:
                        try: os.unlink(tmp)
                        except: pass
                        results.append((task['book_id'], 'HTML', None, str(e)))
                        fmt_results.append(('HTML', False, str(e)))

                # ── FB2 ───────────────────────────────────────
                if task.get('fb2'):
                    tmp = tempfile.mktemp(suffix='.fb2')
                    try:
                        convert_fb2_s2t(task['fb2'], tmp,
                                        variant=self.variant)
                        results.append((task['book_id'], 'FB2', tmp, None))
                        fmt_results.append(('FB2', True, ''))
                    except Exception as e:
                        try: os.unlink(tmp)
                        except: pass
                        results.append((task['book_id'], 'FB2', None, str(e)))
                        fmt_results.append(('FB2', False, str(e)))

                # ── TXT ───────────────────────────────────────
                if task.get('txt'):
                    tmp = tempfile.mktemp(suffix='.txt')
                    try:
                        convert_txt_s2t(task['txt'], tmp,
                                        variant=self.variant)
                        results.append((task['book_id'], 'TXT', tmp, None))
                        fmt_results.append(('TXT', True, ''))
                    except Exception as e:
                        try: os.unlink(tmp)
                        except: pass
                        results.append((task['book_id'], 'TXT', None, str(e)))
                        fmt_results.append(('TXT', False, str(e)))

                # Summarise per-book result
                all_ok   = all(r[1] for r in fmt_results)
                ok_fmts  = [r[0] for r in fmt_results if r[1]]
                err_msgs = [f'{r[0]}: {r[2]}' for r in fmt_results if not r[1]]
                if all_ok:
                    msg = ', '.join(ok_fmts)
                else:
                    msg = '; '.join(err_msgs)
                self.book_finished.emit(task['book_id'], all_ok, msg)

            self.finished.emit(True, results, '')

        except Exception:
            import traceback
            self.finished.emit(False, [], traceback.format_exc())


# ── Workers ───────────────────────────────────────────────────────────────────

class OrientationWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(bool, int, int, bool, list, str)  # ok, css, html, opf, errs, msg

    def __init__(self, epub_path, output_path, target):
        super().__init__()
        self.epub_path   = epub_path
        self.output_path = output_path
        self.target      = target

    def run(self):
        try:
            from calibre_plugins.furigana_ruby.orientation_engine import (
                process_epub_orientation)
            css_n, html_n, opf_ok, errors = process_epub_orientation(
                self.epub_path, self.output_path, self.target,
                progress_callback=lambda c, t, n:
                    self.progress.emit(c, t, os.path.basename(n)),
            )
            self.finished.emit(True, css_n, html_n, opf_ok, errors, '')
        except Exception:
            import traceback
            self.finished.emit(False, 0, 0, False, [], traceback.format_exc())


class BulkOrientationWorker(QThread):
    """
    Converts layout orientation for multiple EPUBs sequentially.

    Signals
    -------
    book_started(book_id)
    book_finished(book_id, ok, msg)
    finished(ok, results, traceback)
        results = [(book_id, tmp_path_or_None, error_or_None)]
    """
    book_started  = pyqtSignal(int)
    book_finished = pyqtSignal(int, bool, str)
    finished      = pyqtSignal(bool, list, str)

    def __init__(self, tasks, target):
        super().__init__()
        self.tasks  = tasks   # list of {'book_id': int, 'epub': str}
        self.target = target  # 'vertical' | 'horizontal'

    def run(self):
        try:
            try:
                from calibre_plugins.furigana_ruby.orientation_engine import (
                    process_epub_orientation)
            except ImportError:
                from orientation_engine import process_epub_orientation

            results = []
            for task in self.tasks:
                self.book_started.emit(task['book_id'])
                tmp = tempfile.mktemp(suffix='.epub')
                try:
                    process_epub_orientation(task['epub'], tmp, self.target)
                    results.append((task['book_id'], tmp, None))
                    self.book_finished.emit(task['book_id'], True, '')
                except Exception as e:
                    try: os.unlink(tmp)
                    except: pass
                    results.append((task['book_id'], None, str(e)))
                    self.book_finished.emit(task['book_id'], False, str(e))

            self.finished.emit(True, results, '')

        except Exception:
            import traceback
            self.finished.emit(False, [], traceback.format_exc())


class FuriganaWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(bool, int, list, str)

    def __init__(self, epub_path, output_path, mode, annotate_levels,
                 remove_levels=None):
        super().__init__()
        self.epub_path       = epub_path
        self.output_path     = output_path
        self.mode            = mode
        self.annotate_levels = annotate_levels
        self.remove_levels   = remove_levels

    def run(self):
        try:
            from calibre_plugins.furigana_ruby.furigana_engine import process_epub_file
            processed, ruby_added, file_errors = process_epub_file(
                self.epub_path, self.output_path,
                mode=self.mode,
                annotate_levels=self.annotate_levels,
                remove_levels=self.remove_levels,
                progress_callback=lambda c, t, n:
                    self.progress.emit(c, t, os.path.basename(n)),
            )
            self.finished.emit(True, ruby_added, file_errors,
                               f'Processed {processed} files.')
        except Exception as e:
            import traceback
            self.finished.emit(False, 0, [], traceback.format_exc())


class BulkFuriganaWorker(QThread):
    """Process ruby add/remove for multiple EPUBs sequentially.

    tasks = [{'book_id': int, 'epub': str,
               'to_add': set, 'to_remove': set, 'current_levels': set}]
    finished result: [(book_id, tmp_path_or_None, ruby_delta, error_or_None)]
    """
    book_started  = pyqtSignal(int)
    book_finished = pyqtSignal(int, bool, int, str)
    finished      = pyqtSignal(bool, list, str)

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks

    def run(self):
        try:
            try:
                from calibre_plugins.furigana_ruby.furigana_engine import process_epub_file
            except ImportError:
                from furigana_engine import process_epub_file

            results = []
            for task in self.tasks:
                self.book_started.emit(task['book_id'])
                to_add    = task['to_add']
                to_remove = task['to_remove']
                current   = task['current_levels']
                epub      = task['epub']
                tmp_r = tmp_a = None
                try:
                    src        = epub
                    ruby_delta = 0
                    if to_remove:
                        rl    = None if to_remove >= current else to_remove
                        tmp_r = tempfile.mktemp(suffix='.epub')
                        _, cnt, _ = process_epub_file(epub, tmp_r, mode='remove',
                                                      remove_levels=rl)
                        ruby_delta += cnt
                        src = tmp_r
                    if to_add:
                        al    = None if to_add >= _ALL_LEVELS else to_add
                        tmp_a = tempfile.mktemp(suffix='.epub')
                        _, cnt, _ = process_epub_file(src, tmp_a, mode='add',
                                                      annotate_levels=al)
                        ruby_delta += cnt
                        if tmp_r:
                            try: os.unlink(tmp_r)
                            except: pass
                            tmp_r = None
                        final = tmp_a
                    else:
                        final = tmp_r
                    results.append((task['book_id'], final, ruby_delta, None))
                    self.book_finished.emit(task['book_id'], True, ruby_delta, '')
                except Exception as e:
                    for t in (tmp_r, tmp_a):
                        try:
                            if t: os.unlink(t)
                        except: pass
                    results.append((task['book_id'], None, 0, str(e)))
                    self.book_finished.emit(task['book_id'], False, 0, str(e))

            self.finished.emit(True, results, '')
        except Exception:
            import traceback
            self.finished.emit(False, [], traceback.format_exc())


# ── Main action ───────────────────────────────────────────────────────────────

class FuriganaAction(InterfaceAction):
    name = 'Furigana Ruby'
    action_spec = (
        '振り仮名 Ruby', None,
        'Add/remove furigana ruby annotations to Japanese EPUBs', None,
    )
    action_type = 'current'
    action_add_menu = True
    action_menu_clone_qaction = None
    popup_type = (QToolButton.ToolButtonPopupMode.MenuButtonPopup
                  if PYQT6 else 2)

    def genesis(self):
        # ── Icon ──────────────────────────────────────────────────
        try:
            import zipfile as _zf
            icon_data = None
            icon_path = os.path.join(os.path.dirname(__file__), 'images', 'icon.png')
            if os.path.exists(icon_path):
                with open(icon_path, 'rb') as f:
                    icon_data = f.read()
            else:
                from calibre.utils.config import config_dir
                pdir = os.path.join(config_dir, 'plugins')
                if os.path.isdir(pdir):
                    for fn in os.listdir(pdir):
                        if 'furigana' in fn.lower() and fn.endswith('.zip'):
                            with _zf.ZipFile(os.path.join(pdir, fn), 'r') as z:
                                if 'images/icon.png' in z.namelist():
                                    icon_data = z.read('images/icon.png')
                            break
            if icon_data:
                try:
                    from PyQt6.QtGui import QPixmap
                    from PyQt6.QtCore import QByteArray
                except ImportError:
                    from PyQt5.Qt import QPixmap, QByteArray
                ba = QByteArray(icon_data)
                pm = QPixmap()
                pm.loadFromData(ba)
                if not pm.isNull():
                    self.qaction.setIcon(QIcon(pm))
        except Exception:
            pass

        # ── Dropdown menu ──────────────────────────────────────────
        self.menu = QMenu(self.gui)
        self.qaction.setMenu(self.menu)
        self.qaction.triggered.connect(self.open_main_dialog)

        a1 = QAction('✦ Edit Ruby…', self.gui)
        a1.triggered.connect(self.open_main_dialog)
        self.menu.addAction(a1)

        a2 = QAction('↔ Convert Layout…', self.gui)
        a2.triggered.connect(self.open_orientation_dialog)
        self.menu.addAction(a2)

        a_zh = QAction('繁 Convert Chinese S↔T…', self.gui)
        a_zh.triggered.connect(self.open_chinese_dialog)
        self.menu.addAction(a_zh)

        self.menu.addSeparator()

        a_settings = QAction('⚙ Settings…', self.gui)
        a_settings.triggered.connect(self.open_settings)
        self.menu.addAction(a_settings)

        self.menu.addSeparator()

        a3 = QAction('ℹ About / Help', self.gui)
        a3.triggered.connect(self.show_about)
        self.menu.addAction(a3)

        a4 = QAction('🔄 Check for Updates…', self.gui)
        a4.triggered.connect(self.check_for_updates)
        self.menu.addAction(a4)

    # ── Helpers ───────────────────────────────────────────────────

    def _selected_ids(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        return [self.gui.library_view.model().id(r) for r in rows]

    def _epub_path(self, book_id):
        db = self.gui.current_db.new_api
        return (db.format_abspath(book_id, 'EPUB')
                if db.has_format(book_id, 'EPUB') else None)

    def _default_levels(self):
        return set(prefs.get('annotate_levels', ['N1', 'N2', 'N3']))

    def _ensure_deps(self):
        from calibre_plugins.furigana_ruby.deps_loader import ensure_deps, get_status
        ok = ensure_deps()
        if not ok:
            error_dialog(self.gui, 'Missing Dependencies',
                '<b>pykakasi could not be loaded.</b><br><br>'
                f'Status: {get_status()}<br><br>'
                'Please re-run <code>setup_plugin.py</code> to rebuild the plugin zip.',
                show=True)
        return ok

    def _scan_epub(self, path):
        """Return (auto_count, pub_count, file_count) for an EPUB."""
        import zipfile
        import re as _re
        auto_pat = _re.compile(r'<ruby[^>]+class=["\']auto["\'][^>]*>', _re.I)
        pub_pat  = _re.compile(r'<ruby(?![^>]+class=["\']auto["\'])[^>]*>', _re.I)
        auto_count = pub_count = file_count = 0
        with zipfile.ZipFile(path, 'r') as zf:
            for name in zf.namelist():
                if name.lower().endswith(('.xhtml', '.html', '.htm')):
                    try:
                        txt = zf.read(name).decode('utf-8', errors='ignore')
                        a  = len(auto_pat.findall(txt))
                        p2 = len(pub_pat.findall(txt))
                        auto_count += a
                        pub_count  += p2
                        if a or p2:
                            file_count += 1
                    except Exception:
                        pass
        return auto_count, pub_count, file_count

    def _get_annotated_levels(self, path):
        """Return set of JLPT levels currently annotated in the EPUB."""
        try:
            from calibre_plugins.furigana_ruby.furigana_engine import get_annotated_levels
        except ImportError:
            from furigana_engine import get_annotated_levels
        return get_annotated_levels(path)

    # ── Entry point ───────────────────────────────────────────────

    def open_main_dialog(self):
        ids = self._selected_ids()
        if not ids:
            warning_dialog(self.gui, 'No Book Selected',
                'Select one or more Japanese EPUB books first.', show=True)
            return
        self._show_ruby_dialog(ids)

    # ── Unified ruby dialog (single + bulk) ───────────────────────

    def _show_ruby_dialog(self, book_ids):
        if not self._ensure_deps():
            return

        try:
            from calibre_plugins.furigana_ruby.lang_detect import (
                detect_book_language, lang_display)
        except ImportError:
            from lang_detect import detect_book_language, lang_display

        db = self.gui.current_db.new_api

        # ── Scan all selected books ───────────────────────────────
        book_rows      = []
        excluded_count = 0

        for book_id in book_ids:
            title     = db.field_for('title', book_id) or f'Book {book_id}'
            epub_path = self._epub_path(book_id)
            if not epub_path:
                excluded_count += 1
                continue
            try:
                lang_info = detect_book_language(epub_path)
            except Exception:
                lang_info = {'lang_raw': '', 'is_japanese': False,
                             'is_chinese': False, 'is_korean': False}
            ruby_allowed = not (lang_info['is_chinese'] or lang_info['is_korean'])
            lang_label   = lang_display(lang_info) if lang_info['lang_raw'] else 'Unknown language'
            if ruby_allowed:
                try:
                    auto_count, pub_count, _ = self._scan_epub(epub_path)
                except Exception:
                    auto_count = pub_count = 0
                current_levels = self._get_annotated_levels(epub_path)
            else:
                auto_count = pub_count = 0
                current_levels = set()

            book_rows.append({
                'book_id':        book_id,
                'title':          title,
                'epub':           epub_path,
                'lang_info':      lang_info,
                'lang_label':     lang_label,
                'ruby_allowed':   ruby_allowed,
                'auto_count':     auto_count,
                'pub_count':      pub_count,
                'current_levels': current_levels,
            })

        eligible_rows = [r for r in book_rows if r['ruby_allowed']]

        def _selection_summary():
            n_eligible = len(eligible_rows)
            n_other    = len(book_rows) - n_eligible
            parts = []
            if n_eligible:
                parts.append(f'{n_eligible} Japanese EPUB(s)')
            if n_other:
                parts.append(f'{n_other} not applicable (non-Japanese)')
            if excluded_count:
                parts.append(f'{excluded_count} skipped (no EPUB)')
            return (f'Selection: {len(book_ids)} book(s) — '
                    + (' · '.join(parts) if parts else 'none applicable'))

        # ── Build dialog ──────────────────────────────────────────
        dlg = QDialog(self.gui)
        dlg.setWindowTitle('Furigana (Ruby) Customization')
        dlg.setMinimumWidth(700)
        dlg.setMinimumHeight(520)
        dlg.resize(720, 660)

        vl = QVBoxLayout()
        vl.setSpacing(6)
        dlg.setLayout(vl)

        # Description — line 1 fixed, line 2 depends on keep_original
        desc1 = QLabel(
            'Add/Update the Furigana (Ruby) to ebooks based on the selected JLPT '
            'levels. Publisher furigana is always preserved.')
        desc1.setWordWrap(True)
        vl.addWidget(desc1)

        if prefs['keep_original']:
            desc2_text = ('* A copy of the original file will be saved based on '
                          'your plugin Settings.')
        else:
            desc2_text = ('* Modified file will replace the original file based on '
                          'your plugin Settings.')
        desc2 = QLabel(desc2_text)
        desc2.setWordWrap(True)
        vl.addWidget(desc2)

        sep = QFrame()
        try:
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFrameShadow(QFrame.Shadow.Sunken)
        except AttributeError:
            sep.setFrameShape(QFrame.HLine)
            sep.setFrameShadow(QFrame.Sunken)
        vl.addWidget(sep)

        # ── JLPT collapsible panel ────────────────────────────────
        saved_levels        = set(prefs['annotate_levels'])
        level_cbs           = {}
        _pre_expand_levels  = [None]

        _LEVEL_ORDER = ['N1', 'N2', 'N3', 'N4', 'N5', 'unlisted']

        def _current_sel_text():
            checked = [l for l in _LEVEL_ORDER
                       if level_cbs.get(l, QCheckBox()).isChecked()]
            return 'Current Selection: ' + (', '.join(checked) if checked else 'None')

        # Collapsed view
        collapsed_container = QWidget()
        coll_vl = QVBoxLayout()
        coll_vl.setContentsMargins(0, 0, 0, 0)
        coll_vl.setSpacing(2)

        coll_hdr_hl = QHBoxLayout()
        coll_hdr_hl.setContentsMargins(0, 0, 0, 0)
        coll_hdr_hl.setSpacing(6)
        coll_title = QLabel('<b>JLPT Levels Configuration</b>')
        btn_customize = QPushButton('Customize')
        btn_customize.setFlat(True)
        _link_style = ('color: #0066cc; text-decoration: underline; '
                       'border: none; padding: 0;')
        btn_customize.setStyleSheet(_link_style)
        try:
            btn_customize.setCursor(Qt.CursorShape.PointingHandCursor)
        except AttributeError:
            btn_customize.setCursor(Qt.PointingHandCursor)
        coll_hdr_hl.addWidget(coll_title)
        coll_hdr_hl.addWidget(btn_customize)
        coll_hdr_hl.addStretch()

        current_sel_lbl = QLabel('')
        current_sel_lbl.setStyleSheet('color: #545454;')

        coll_vl.addLayout(coll_hdr_hl)
        coll_vl.addWidget(current_sel_lbl)
        collapsed_container.setLayout(coll_vl)
        vl.addWidget(collapsed_container)

        # Expanded panel (hidden by default)
        expanded_panel = QFrame()
        try:
            expanded_panel.setFrameShape(QFrame.Shape.StyledPanel)
            expanded_panel.setFrameShadow(QFrame.Shadow.Raised)
        except AttributeError:
            expanded_panel.setFrameShape(QFrame.StyledPanel)
            expanded_panel.setFrameShadow(QFrame.Raised)
        expanded_panel.setStyleSheet(
            'QFrame { border: 1px solid #b0b0b0; border-radius: 3px; }')
        exp_vl = QVBoxLayout()
        exp_vl.setContentsMargins(8, 6, 8, 6)
        exp_vl.setSpacing(4)

        exp_hdr_hl = QHBoxLayout()
        exp_hdr_hl.setContentsMargins(0, 0, 0, 0)
        exp_hdr_hl.addWidget(QLabel('<b>JLPT Levels Configuration</b>'))
        btn_save_levels = QPushButton('Save')
        btn_save_levels.setFlat(True)
        btn_save_levels.setStyleSheet(_link_style)
        try:
            btn_save_levels.setCursor(Qt.CursorShape.PointingHandCursor)
        except AttributeError:
            btn_save_levels.setCursor(Qt.PointingHandCursor)
        btn_x = QPushButton('✕')
        btn_x.setFlat(True)
        btn_x.setFixedSize(18, 18)
        btn_x.setStyleSheet('color: #545454; border: none; padding: 0; font-size: 12px;')
        try:
            btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        except AttributeError:
            btn_x.setCursor(Qt.PointingHandCursor)
        exp_hdr_hl.addWidget(btn_save_levels)
        exp_hdr_hl.addStretch()
        exp_hdr_hl.addWidget(btn_x)
        exp_vl.addLayout(exp_hdr_hl)

        for level, label, bold in [
            ('N1',       'N1  —  Rare literary kanji',              True),
            ('N2',       'N2  —  Advanced kanji',                   True),
            ('N3',       'N3  —  Intermediate kanji  ★',            True),
            ('N4',       'N4  —  Basic kanji  (学、週、料理…)',      False),
            ('N5',       'N5  —  Elementary kanji  (日、人、山…)',   False),
            ('unlisted', 'Unlisted  —  Kanji not in any JLPT list',  False),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(level in saved_levels)
            if bold:
                f = cb.font(); f.setBold(True); cb.setFont(f)
            level_cbs[level] = cb
            exp_vl.addWidget(cb)

        quick_hl = QHBoxLayout()
        quick_hl.addWidget(QLabel('Quick select:'))
        for qlabel, qlevels in [
            ('None',    set()),
            ('N1',      {'N1'}),
            ('N1–N2',   {'N1', 'N2'}),
            ('N1–N3 ★', {'N1', 'N2', 'N3'}),
            ('N1–N4',   {'N1', 'N2', 'N3', 'N4'}),
            ('N1–N5',   {'N1', 'N2', 'N3', 'N4', 'N5'}),
            ('All',     _ALL_LEVELS),
        ]:
            qbtn = QPushButton(qlabel)
            qbtn.setFixedHeight(26)
            qbtn.clicked.connect(
                lambda _, lvls=qlevels:
                    [cb.setChecked(lvl in lvls) for lvl, cb in level_cbs.items()])
            quick_hl.addWidget(qbtn)
        quick_hl.addStretch()
        exp_vl.addLayout(quick_hl)

        grp_note = QLabel('<small><i>Publisher ruby is never modified. '
                          'Changes only affect auto-generated (blue) ruby.</i></small>')
        grp_note.setWordWrap(True)
        exp_vl.addWidget(grp_note)
        expanded_panel.setLayout(exp_vl)
        expanded_panel.setVisible(False)
        vl.addWidget(expanded_panel)

        # Expand / collapse helpers
        def _expand():
            _pre_expand_levels[0] = {lvl for lvl, cb in level_cbs.items()
                                     if cb.isChecked()}
            collapsed_container.setVisible(False)
            expanded_panel.setVisible(True)

        def _collapse_save():
            prefs['annotate_levels'] = sorted(
                lvl for lvl, cb in level_cbs.items() if cb.isChecked())
            current_sel_lbl.setText(_current_sel_text())
            expanded_panel.setVisible(False)
            collapsed_container.setVisible(True)

        def _collapse_cancel():
            prev = _pre_expand_levels[0] or set()
            for lvl, cb in level_cbs.items():
                cb.setChecked(lvl in prev)
            expanded_panel.setVisible(False)
            collapsed_container.setVisible(True)

        btn_customize.clicked.connect(_expand)
        btn_save_levels.clicked.connect(_collapse_save)
        btn_x.clicked.connect(_collapse_cancel)

        # Initialise the collapsed label now that level_cbs is built
        current_sel_lbl.setText(_current_sel_text())

        # ── Book list header ──────────────────────────────────────
        hdr_widget = QWidget()
        hdr_widget.setObjectName('rubyHdr')
        hdr_widget.setStyleSheet(
            '#rubyHdr { background-color: #d4d4d4; '
            'border: 1px solid #b8b8b8; border-bottom: none; }')
        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(4, 3, 4, 3)
        hdr_layout.setSpacing(4)

        header_cb = QCheckBox()
        header_cb.setTristate(True)
        header_cb.setToolTip('Select / deselect all applicable books')
        hdr_cb_box = QWidget()
        hdr_cb_box.setFixedWidth(20)
        hdr_cb_inner = QHBoxLayout()
        hdr_cb_inner.setContentsMargins(0, 0, 0, 0)
        hdr_cb_inner.setSpacing(0)
        hdr_cb_inner.addStretch()
        hdr_cb_inner.addWidget(header_cb)
        hdr_cb_inner.addStretch()
        hdr_cb_box.setLayout(hdr_cb_inner)

        hdr_books_lbl  = QLabel('<b>Books</b>')
        hdr_status_lbl = QLabel('<b>Status</b>')
        hdr_status_lbl.setMinimumWidth(170)
        try:
            hdr_status_lbl.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        except AttributeError:
            hdr_status_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        hdr_layout.addWidget(hdr_cb_box)
        hdr_layout.addWidget(hdr_books_lbl, 3)
        hdr_layout.addWidget(hdr_status_lbl, 1)
        hdr_widget.setLayout(hdr_layout)

        # ── Scrollable book list ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea { border: 1px solid #b8b8b8; border-top: none; }')
        scroll.setMinimumHeight(5 * 58)
        sp_pol = QSizePolicy.Policy if PYQT6 else QSizePolicy
        scroll.setSizePolicy(sp_pol.Expanding, sp_pol.Expanding)

        table_container = QWidget()
        table_vl = QVBoxLayout()
        table_vl.setSpacing(0)
        table_vl.setContentsMargins(0, 0, 0, 0)
        table_vl.addWidget(hdr_widget)
        table_vl.addWidget(scroll)
        table_container.setLayout(table_vl)

        list_widget = QWidget()
        list_layout = QVBoxLayout()
        list_layout.setSpacing(3)
        list_layout.setContentsMargins(4, 4, 4, 4)
        list_widget.setLayout(list_layout)

        _SUB_STYLE = 'color: #545454; font-size: 11px;'
        _DIM_STYLE  = 'color: #959595;'

        checkboxes    = []
        status_labels = {}
        sub_labels    = {}
        sub_base_text = {}
        cb_map        = {}
        applicable_ids = set(r['book_id'] for r in eligible_rows)

        for row in book_rows:
            cb = QCheckBox()
            cb.setVisible(row['ruby_allowed'])
            cb.setChecked(row['ruby_allowed'])
            cb_box = QWidget()
            cb_box.setFixedWidth(20)
            cb_box_inner = QHBoxLayout()
            cb_box_inner.setContentsMargins(0, 0, 0, 0)
            cb_box_inner.setSpacing(0)
            cb_box_inner.addStretch()
            cb_box_inner.addWidget(cb)
            cb_box_inner.addStretch()
            cb_box.setLayout(cb_box_inner)

            title_lbl = ElidedLabel(row['title'])
            title_lbl.setToolTip(row['title'])
            title_lbl.setSizePolicy(sp_pol.Expanding, sp_pol.Preferred)
            if not row['ruby_allowed']:
                title_lbl.setStyleSheet(_DIM_STYLE)
            title_lbl.clicked.connect(
                lambda _=None, c=cb, bid=row['book_id']:
                    c.toggle() if bid in applicable_ids and c.isEnabled() else None)

            status_lbl = QLabel('' if row['ruby_allowed'] else 'Not applicable')
            try:
                status_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            except AttributeError:
                status_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            status_lbl.setMinimumWidth(170)
            if not row['ruby_allowed']:
                status_lbl.setStyleSheet('color: #959595;')

            if row['ruby_allowed']:
                sub_text = (f'{row["lang_label"]} · '
                            f'Publisher: {row["pub_count"]:,} · '
                            f'Auto: {row["auto_count"]:,}')
            else:
                sub_text = f'{row["lang_label"]} · EPUB'

            sub_lbl = QLabel(sub_text)
            sub_lbl.setStyleSheet(_SUB_STYLE if row['ruby_allowed'] else _DIM_STYLE)

            top_row = QHBoxLayout()
            top_row.setSpacing(4)
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.addWidget(cb_box)
            top_row.addWidget(title_lbl, 3)
            top_row.addWidget(status_lbl, 1)

            sub_row = QHBoxLayout()
            sub_row.setContentsMargins(24, 0, 0, 2)
            sub_row.addWidget(sub_lbl)
            sub_row.addStretch()

            container_layout = QVBoxLayout()
            container_layout.setSpacing(1)
            container_layout.setContentsMargins(4, 4, 4, 4)
            container_layout.addLayout(top_row)
            container_layout.addLayout(sub_row)

            container = QWidget()
            container.setLayout(container_layout)
            list_layout.addWidget(container)

            checkboxes.append(cb)
            cb_map[row['book_id']]        = cb
            status_labels[row['book_id']] = status_lbl
            sub_labels[row['book_id']]    = sub_lbl
            sub_base_text[row['book_id']] = sub_text

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        vl.addWidget(table_container)

        # Summary result panel
        result_te = QTextEdit()
        result_te.setReadOnly(True)
        result_te.setFixedHeight(70)
        result_te.setSizePolicy(sp_pol.Expanding, sp_pol.Fixed)
        result_te.setPlainText(_selection_summary())
        vl.addWidget(result_te)

        # ── Buttons ───────────────────────────────────────────────
        btn_row_hl = QHBoxLayout()

        btn_viewer = QPushButton('📖 Open in Viewer')
        btn_viewer.setMinimumWidth(150)
        btn_viewer.setVisible(len(eligible_rows) == 1)

        btn_apply = QPushButton('Add Ruby')
        btn_apply.setMinimumWidth(90)
        btn_close = QPushButton('Close')
        btn_close.setMinimumWidth(70)

        btn_row_hl.addWidget(btn_viewer)
        btn_row_hl.addStretch()
        btn_row_hl.addWidget(btn_close)
        btn_row_hl.addWidget(btn_apply)
        vl.addLayout(btn_row_hl)

        # ── Header checkbox logic ─────────────────────────────────
        def _eligible_cbs():
            return [cb_map[bid] for bid in applicable_ids if bid in cb_map]

        def _update_apply_state():
            any_checked = any(cb.isChecked() for cb in _eligible_cbs())
            btn_apply.setEnabled(any_checked)
            _update_header_cb()

        def _update_header_cb():
            ecbs = _eligible_cbs()
            header_cb.blockSignals(True)
            try:
                if not ecbs:
                    state = (Qt.CheckState.Unchecked if PYQT6 else Qt.Unchecked)
                else:
                    n = sum(1 for cb in ecbs if cb.isChecked())
                    if n == 0:
                        state = (Qt.CheckState.Unchecked if PYQT6 else Qt.Unchecked)
                    elif n == len(ecbs):
                        state = (Qt.CheckState.Checked if PYQT6 else Qt.Checked)
                    else:
                        state = (Qt.CheckState.PartiallyChecked
                                 if PYQT6 else Qt.PartiallyChecked)
                header_cb.setCheckState(state)
            except AttributeError:
                pass
            finally:
                header_cb.blockSignals(False)

        def _on_header_clicked():
            ecbs        = _eligible_cbs()
            all_checked = bool(ecbs) and all(cb.isChecked() for cb in ecbs)
            for cb in ecbs:
                cb.setChecked(not all_checked)
            _update_apply_state()

        def _lock_controls():
            header_cb.setEnabled(False)
            for cb in checkboxes:
                cb.setEnabled(False)
            for lvl_cb in level_cbs.values():
                lvl_cb.setEnabled(False)
            btn_apply.setEnabled(False)

        def _unlock_controls():
            header_cb.setEnabled(True)
            for cb in checkboxes:
                if cb.isVisible():
                    cb.setEnabled(True)
            for lvl_cb in level_cbs.values():
                lvl_cb.setEnabled(True)
            _update_apply_state()

        # ── Apply handler ─────────────────────────────────────────
        def _on_apply():
            checked_levels = {lvl for lvl, cb in level_cbs.items() if cb.isChecked()}

            tasks = []
            for row in book_rows:
                cb = cb_map[row['book_id']]
                if not (cb.isVisible() and cb.isChecked()):
                    continue
                to_add    = checked_levels - row['current_levels']
                to_remove = row['current_levels'] - checked_levels
                if to_add or to_remove:
                    tasks.append({
                        'book_id':        row['book_id'],
                        'epub':           row['epub'],
                        'to_add':         to_add,
                        'to_remove':      to_remove,
                        'current_levels': row['current_levels'],
                    })

            if not tasks:
                result_te.setPlainText(
                    '⚠ Nothing to do — selected books already match '
                    'the chosen levels.\n\n' + _selection_summary())
                return

            prefs['annotate_levels'] = sorted(checked_levels)

            _lock_controls()
            for row in book_rows:
                cb = cb_map[row['book_id']]
                if cb.isVisible() and cb.isChecked():
                    sl = status_labels[row['book_id']]
                    sl.setText('⏳ Processing…')
                    sl.setStyleSheet('color: #545454;')
            QApplication.processEvents()

            done    = [False]
            outcome = [None]

            worker = BulkFuriganaWorker(tasks)

            def on_book_started(book_id):
                sl = status_labels.get(book_id)
                if sl:
                    sl.setText('⏳ Processing…')
                    sl.setStyleSheet('color: #545454;')

            def on_book_finished(book_id, ok, ruby_delta, msg):
                sl = status_labels.get(book_id)
                if sl:
                    if ok:
                        delta_str = (f'+{ruby_delta:,}' if ruby_delta >= 0
                                     else str(ruby_delta))
                        sl.setText(f'✅ Done ({delta_str})')
                        sl.setStyleSheet('color: green;')
                    else:
                        sl.setText('⚠ Error')
                        sl.setStyleSheet('color: red;')
                        sl.setToolTip(msg)

            def on_done(ok, results, tb):
                done[0]    = True
                outcome[0] = (ok, results, tb)

            worker.book_started.connect(on_book_started)
            worker.book_finished.connect(on_book_finished)
            worker.finished.connect(on_done)
            worker.start()

            while not done[0]:
                QApplication.processEvents()
            worker.wait()

            ok2, results, tb = outcome[0]

            if not ok2:
                result_te.setPlainText(f'⚠ Unexpected error:\n{tb}')
                _unlock_controls()
                return

            saved       = 0
            save_errors = []
            task_map    = {t['book_id']: t for t in tasks}

            for book_id, tmp_path, ruby_delta, err in results:
                sl  = status_labels.get(book_id)
                row = next((r for r in book_rows if r['book_id'] == book_id), None)
                if err or not tmp_path:
                    save_errors.append(f'Book {book_id}: {err}')
                    if sl and not sl.text().startswith('⚠'):
                        sl.setText('⚠ Error')
                        sl.setStyleSheet('color: red;')
                    continue
                try:
                    if prefs['keep_original']:
                        existing = db.formats(book_id)
                        if 'ORIGINAL_EPUB' not in (f.upper() for f in existing):
                            orig = task_map[book_id]['epub']
                            db.add_format(book_id, 'ORIGINAL_EPUB', orig, replace=False)
                    db.add_format(book_id, 'EPUB', tmp_path, replace=True)
                    saved += 1
                    # Update in-memory state so re-apply works correctly
                    if row:
                        row['current_levels'] = checked_levels.copy()
                        sub_lbl = sub_labels.get(book_id)
                        if sub_lbl:
                            new_auto  = (row['auto_count'] + ruby_delta
                                         if ruby_delta >= 0 else max(0, row['auto_count'] + ruby_delta))
                            row['auto_count'] = new_auto
                            sub_lbl.setText(
                                f'{row["lang_label"]} · '
                                f'Publisher: {row["pub_count"]:,} · '
                                f'Auto: {new_auto:,}')
                except Exception as e:
                    save_errors.append(f'Book {book_id}: save failed: {e}')
                    if sl:
                        sl.setText('⚠ Save error')
                        sl.setStyleSheet('color: red;')
                        sl.setToolTip(str(e))
                finally:
                    try: os.unlink(tmp_path)
                    except: pass

            self.gui.library_view.model().refresh_ids(
                [r[0] for r in results])

            lines = [f'✅ Saved {saved} book(s)']
            if save_errors:
                lines.append(f'⚠ {len(save_errors)} error(s):')
                lines += [f'  {e}' for e in save_errors[:5]]
            lines += ['', _selection_summary()]
            result_te.setPlainText('\n'.join(lines))
            _unlock_controls()

        # ── Viewer button ─────────────────────────────────────────
        def _on_viewer():
            dlg.reject()
            self._open_in_viewer(eligible_rows[0]['book_id'])

        # Wire signals
        for cb in checkboxes:
            cb.stateChanged.connect(lambda _: _update_apply_state())
        header_cb.clicked.connect(_on_header_clicked)
        btn_apply.clicked.connect(_on_apply)
        btn_viewer.clicked.connect(_on_viewer)
        btn_close.clicked.connect(dlg.reject)

        if not eligible_rows:
            btn_apply.setEnabled(False)
            btn_apply.setToolTip('No Japanese EPUB books in selection.')
            header_cb.setEnabled(False)

        _update_apply_state()

        dlg.exec() if PYQT6 else dlg.exec_()

    # ── Single-book runner (returns result string) ────────────────

    def _run_epub(self, book_id, epub_path, mode, annotate_levels,
                  display_levels, remove_levels=None):
        """
        Run add or remove on one EPUB with a progress dialog.
        Returns a result message string.  No separate Done dialog.
        """
        try:
            wm = Qt.WindowModality.WindowModal
        except AttributeError:
            wm = Qt.WindowModal

        db    = self.gui.current_db.new_api
        title = db.field_for('title', book_id) or f'Book {book_id}'
        tmp   = tempfile.mktemp(suffix='.epub')

        prog = QProgressDialog(
            f'Processing: {title}', 'Cancel', 0, 100, self.gui)
        prog.setWindowTitle('Adding Ruby…' if mode == 'add' else 'Removing Ruby…')
        prog.setWindowModality(wm)
        prog.setMinimumDuration(0)
        prog.setMinimumWidth(460)
        prog.setValue(0)
        prog.show()
        prog.raise_()
        prog.activateWindow()
        QApplication.processEvents()   # paint before heavy work starts

        done = [False]; err = [None]; ruby_n = [0]; ferrs = [[]]

        worker = FuriganaWorker(epub_path, tmp, mode, annotate_levels,
                                remove_levels=remove_levels)

        def on_prog(c, t, n, _p=prog):
            if not _p.wasCanceled():
                _p.setValue(int(c / max(t, 1) * 100))
                _p.setLabelText(f'Processing: {n}')

        def on_done(ok, rn, fe, _msg):
            done[0] = True
            if not ok:
                err[0] = _msg
            ruby_n[0] = rn
            ferrs[0] = fe

        worker.progress.connect(on_prog)
        worker.finished.connect(on_done)
        worker.start()

        while not done[0]:
            QApplication.processEvents()
            if prog.wasCanceled():
                worker.terminate()
                worker.wait()
                try: os.unlink(tmp)
                except: pass
                prog.close()
                return '⚠ Cancelled.'

        worker.wait()
        prog.close()

        if err[0]:
            return f'⚠ Error:\n{err[0]}'

        try:
            if mode == 'add' and prefs['keep_original']:
                try:
                    existing = db.formats(book_id)
                    if 'ORIGINAL_EPUB' not in (f.upper() for f in existing):
                        db.add_format(book_id, 'ORIGINAL_EPUB', epub_path, replace=False)
                except Exception:
                    pass
            db.add_format(book_id, 'EPUB', tmp, replace=True)
        except Exception as e:
            try: os.unlink(tmp)
            except: pass
            return f'⚠ Could not save EPUB: {e}'
        finally:
            try: os.unlink(tmp)
            except: pass

        lvl_s = ', '.join(
            l for l in ['N1','N2','N3','N4','N5','unlisted']
            if l in display_levels
        ) if display_levels else ''

        if mode == 'add':
            if ruby_n[0] == 0:
                return '⚠ 0 annotations added — pykakasi may have failed.'
            msg = f'✅ Added {ruby_n[0]:,} annotations'
            if lvl_s:
                msg += f'  (Levels: {lvl_s})'
            if ferrs[0]:
                msg += f'\n⚠ {len(ferrs[0])} file(s) had errors.'
            return msg
        else:
            removed = -ruby_n[0]
            msg = f'✓ Removed {removed:,} annotations'
            if lvl_s:
                msg += f'  (Levels: {lvl_s})'
            if ferrs[0]:
                msg += f'\n⚠ {len(ferrs[0])} file(s) had errors.'
            return msg

    # ── Open in viewer ────────────────────────────────────────────

    def _open_in_viewer(self, book_id):
        try:
            self.gui.library_view.select_rows([book_id], using_ids=True)
        except Exception:
            pass
        for attempt in [
            lambda: self.gui.iactions['View'].view_format_by_id(book_id, 'EPUB'),
            lambda: self.gui.iactions['View'].view_book(book_id),
            lambda: self.gui.iactions['View'].triggered(),
        ]:
            try:
                attempt()
                return
            except Exception:
                continue
        warning_dialog(self.gui, 'Open in Viewer',
            'Could not open the viewer automatically.\n'
            'Please double-click the book in the library to open it.',
            show=True)

    # ── Orientation conversion ────────────────────────────────────

    def open_orientation_dialog(self):
        ids = self._selected_ids()
        if not ids:
            warning_dialog(self.gui, 'No Book Selected',
                'Select one or more EPUB books first.', show=True)
            return
        if len(ids) == 1:
            self._show_orientation_dialog(ids[0])
        else:
            self._show_bulk_orientation_dialog(ids)

    def _show_orientation_dialog(self, book_id):
        path = self._epub_path(book_id)
        if not path:
            warning_dialog(self.gui, 'No EPUB',
                'No EPUB format found for this book.', show=True)
            return

        try:
            from calibre_plugins.furigana_ruby.orientation_engine import detect_orientation
        except ImportError:
            from orientation_engine import detect_orientation

        db      = self.gui.current_db.new_api
        title   = db.field_for('title', book_id) or f'Book {book_id}'
        current = detect_orientation(path)   # 'vertical' | 'horizontal' | 'unknown'
        target  = 'horizontal' if current == 'vertical' else 'vertical'

        # ── Dialog ────────────────────────────────────────────────
        dlg = QDialog(self.gui)
        dlg.setWindowTitle('Convert Layout')
        dlg.setMinimumWidth(560)
        dlg.setMinimumHeight(320)
        dlg.resize(580, 340)

        vl = QVBoxLayout()
        vl.setSpacing(12)
        dlg.setLayout(vl)

        te = QTextEdit()
        te.setReadOnly(True)
        sp = QSizePolicy.Policy if PYQT6 else QSizePolicy
        te.setSizePolicy(sp.Expanding, sp.Expanding)
        vl.addWidget(te)

        if current == 'vertical':
            status_text = (
                f'📖  "{title}"\n\n'
                f'Current layout:   Vertical (right-to-left columns)\n\n'
                f'Clicking Convert will:\n'
                f'  • Change writing-mode to horizontal in all CSS files\n'
                f'  • Update the OPF spine direction to left-to-right\n'
                f'  • Fix any inline vertical styles in the HTML\n\n'
                f'Publisher and auto ruby annotations are preserved.'
            )
            btn_label = '↔  Convert to Horizontal'
        elif current == 'horizontal':
            status_text = (
                f'📖  "{title}"\n\n'
                f'Current layout:   Horizontal (left-to-right)\n\n'
                f'Clicking Convert will:\n'
                f'  • Add writing-mode: vertical-rl to all CSS files\n'
                f'  • Update the OPF spine direction to right-to-left\n'
                f'  • Fix any inline horizontal styles in the HTML\n\n'
                f'Publisher and auto ruby annotations are preserved.'
            )
            btn_label = '↔  Convert to Vertical'
        else:
            status_text = (
                f'📖  "{title}"\n\n'
                f'Current layout:   Unknown\n\n'
                f'The orientation could not be detected from the OPF or CSS.\n'
                f'You can still attempt a conversion — choose a target below.'
            )
            btn_label = '↔  Convert to Vertical'

        te.setPlainText(status_text)

        # ── Button row ────────────────────────────────────────────
        btn_row     = QHBoxLayout()
        btn_convert = QPushButton(btn_label)
        btn_viewer  = QPushButton('📖 Open in Viewer')
        btn_close   = QPushButton('Close')
        btn_convert.setMinimumWidth(200)
        btn_viewer.setMinimumWidth(130)
        btn_close.setMinimumWidth(70)
        btn_row.addWidget(btn_convert)
        btn_row.addStretch()
        btn_row.addWidget(btn_viewer)
        btn_row.addWidget(btn_close)
        vl.addLayout(btn_row)

        # ── Convert handler ───────────────────────────────────────
        def on_convert():
            btn_convert.setEnabled(False)

            try:
                wm = Qt.WindowModality.WindowModal
            except AttributeError:
                wm = Qt.WindowModal

            tmp = tempfile.mktemp(suffix='.epub')
            prog = QProgressDialog(
                f'Converting: {title}', 'Cancel', 0, 100, self.gui)
            prog.setWindowTitle(
                'Converting to Horizontal…' if target == 'horizontal'
                else 'Converting to Vertical…')
            prog.setWindowModality(wm)
            prog.setMinimumDuration(0)
            prog.setMinimumWidth(460)
            prog.setValue(0)
            prog.show()
            prog.raise_()
            prog.activateWindow()
            QApplication.processEvents()   # paint before heavy work starts

            done = [False]
            result = [None]

            worker = OrientationWorker(path, tmp, target)

            def on_prog(c, t, n):
                if not prog.wasCanceled():
                    prog.setValue(int(c / max(t, 1) * 100))
                    prog.setLabelText(f'Processing: {n}')

            def on_done(ok, css_n, html_n, opf_ok, errs, tb):
                done[0]   = True
                result[0] = (ok, css_n, html_n, opf_ok, errs, tb)

            worker.progress.connect(on_prog)
            worker.finished.connect(on_done)
            worker.start()

            while not done[0]:
                QApplication.processEvents()
                if prog.wasCanceled():
                    worker.terminate()
                    worker.wait()
                    try:
                        os.unlink(tmp)
                    except Exception:
                        pass
                    prog.close()
                    btn_convert.setEnabled(True)
                    te.setPlainText('⚠ Cancelled.')
                    return

            worker.wait()
            prog.close()

            ok, css_n, html_n, opf_ok, errs, tb = result[0]

            if not ok:
                te.setPlainText(f'⚠ Conversion failed:\n\n{tb}')
                btn_convert.setEnabled(True)
                return

            try:
                _db = self.gui.current_db.new_api
                if prefs['keep_original']:
                    try:
                        existing = _db.formats(book_id)
                        if 'ORIGINAL_EPUB' not in (f.upper() for f in existing):
                            _db.add_format(book_id, 'ORIGINAL_EPUB', path, replace=False)
                    except Exception:
                        pass
                _db.add_format(book_id, 'EPUB', tmp, replace=True)
            except Exception as e:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
                te.setPlainText(f'⚠ Could not save EPUB: {e}')
                btn_convert.setEnabled(True)
                return
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

            self.gui.library_view.model().refresh_ids([book_id])

            direction_label = ('Horizontal' if target == 'horizontal'
                               else 'Vertical')
            msg = (
                f'✅  Converted to {direction_label} — "{title}"\n\n'
                f'  CSS files modified:         {css_n}\n'
                f'  HTML files (inline styles): {html_n}\n'
                f'  OPF spine updated:          {"Yes" if opf_ok else "No change needed"}\n'
            )
            if errs:
                msg += f'\n⚠ {len(errs)} file(s) had errors (skipped).'
            te.setPlainText(msg)
            # Disable convert button — book is already converted
            btn_convert.setEnabled(False)

        def on_viewer():
            dlg.reject()
            self._open_in_viewer(book_id)

        btn_convert.clicked.connect(on_convert)
        btn_viewer.clicked.connect(on_viewer)
        btn_close.clicked.connect(dlg.reject)

        dlg.exec() if PYQT6 else dlg.exec_()

    # ── Bulk orientation conversion ───────────────────────────────

    def _show_bulk_orientation_dialog(self, book_ids):
        try:
            from calibre_plugins.furigana_ruby.orientation_engine import detect_orientation
        except ImportError:
            from orientation_engine import detect_orientation

        db = self.gui.current_db.new_api

        # ── Scan books ────────────────────────────────────────────
        book_rows      = []
        excluded_count = 0   # books without EPUB

        for book_id in book_ids:
            title = db.field_for('title', book_id) or f'Book {book_id}'
            epub_path = (db.format_abspath(book_id, 'EPUB')
                         if db.has_format(book_id, 'EPUB') else None)
            if not epub_path:
                excluded_count += 1
                continue
            try:
                orientation = detect_orientation(epub_path)
            except Exception:
                orientation = 'unknown'
            book_rows.append({'book_id': book_id, 'title': title,
                              'epub': epub_path, 'orientation': orientation})

        def _orient_label(o):
            return {'vertical': 'Vertical', 'horizontal': 'Horizontal'}.get(o, 'Unknown')

        def _selection_summary():
            parts = [f'{len(book_rows)} EPUB book(s)']
            if excluded_count:
                parts.append(f'{excluded_count} skipped (no EPUB)')
            return f'Selection: {len(book_ids)} book(s) — {" · ".join(parts)}'

        # ── Build dialog ──────────────────────────────────────────
        dlg = QDialog(self.gui)
        dlg.setWindowTitle('Convert Layout — Bulk')
        dlg.setMinimumWidth(680)
        dlg.resize(700, 520)

        vl = QVBoxLayout()
        vl.setSpacing(8)
        dlg.setLayout(vl)

        # Direction
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel('<b>Direction:</b>'))
        rb_h2v = QRadioButton('Horizontal → Vertical')
        rb_v2h = QRadioButton('Vertical → Horizontal')
        rb_h2v.setChecked(True)
        dir_row.addWidget(rb_h2v)
        dir_row.addWidget(rb_v2h)
        dir_row.addStretch()
        vl.addLayout(dir_row)

        # ── Header row ────────────────────────────────────────────
        hdr_widget = QWidget()
        hdr_widget.setObjectName('orientHdr')
        hdr_widget.setStyleSheet(
            '#orientHdr { background-color: #d4d4d4; '
            'border: 1px solid #b8b8b8; border-bottom: none; }')
        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(4, 3, 4, 3)
        hdr_layout.setSpacing(4)

        header_cb = QCheckBox()
        header_cb.setTristate(True)
        header_cb.setToolTip('Select / deselect all applicable books')

        hdr_cb_box = QWidget()
        hdr_cb_box.setFixedWidth(20)
        hdr_cb_inner = QHBoxLayout()
        hdr_cb_inner.setContentsMargins(0, 0, 0, 0)
        hdr_cb_inner.setSpacing(0)
        hdr_cb_inner.addStretch()
        hdr_cb_inner.addWidget(header_cb)
        hdr_cb_inner.addStretch()
        hdr_cb_box.setLayout(hdr_cb_inner)

        hdr_books_lbl  = QLabel('<b>Books</b>')
        hdr_status_lbl = QLabel('<b>Status</b>')
        hdr_status_lbl.setMinimumWidth(170)
        try:
            hdr_status_lbl.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        except AttributeError:
            hdr_status_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        hdr_layout.addWidget(hdr_cb_box)
        hdr_layout.addWidget(hdr_books_lbl, 3)
        hdr_layout.addWidget(hdr_status_lbl, 1)
        hdr_widget.setLayout(hdr_layout)

        # ── Scrollable book list ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea { border: 1px solid #b8b8b8; border-top: none; }')
        sp = QSizePolicy.Policy if PYQT6 else QSizePolicy
        scroll.setSizePolicy(sp.Expanding, sp.Expanding)

        table_container = QWidget()
        table_vl = QVBoxLayout()
        table_vl.setSpacing(0)
        table_vl.setContentsMargins(0, 0, 0, 0)
        table_vl.addWidget(hdr_widget)
        table_vl.addWidget(scroll)
        table_container.setLayout(table_vl)

        list_widget  = QWidget()
        list_layout  = QVBoxLayout()
        list_layout.setSpacing(3)
        list_layout.setContentsMargins(4, 4, 4, 4)
        list_widget.setLayout(list_layout)

        checkboxes    = []
        status_labels = {}
        title_labels  = {}
        sub_labels    = {}
        sub_base_text = {}
        cb_map        = {}
        applicable_ids = set()   # book_ids currently applicable; avoids isVisible quirks

        _SUB_STYLE = 'color: #545454; font-size: 11px;'
        sp_row = QSizePolicy.Policy if PYQT6 else QSizePolicy

        for row in book_rows:
            cb = QCheckBox()
            cb_box = QWidget()
            cb_box.setFixedWidth(20)
            cb_box_inner = QHBoxLayout()
            cb_box_inner.setContentsMargins(0, 0, 0, 0)
            cb_box_inner.setSpacing(0)
            cb_box_inner.addStretch()
            cb_box_inner.addWidget(cb)
            cb_box_inner.addStretch()
            cb_box.setLayout(cb_box_inner)

            title_lbl = ElidedLabel(row['title'])
            title_lbl.setToolTip(row['title'])
            title_lbl.setSizePolicy(sp_row.Expanding, sp_row.Preferred)
            title_lbl.clicked.connect(
                lambda _=None, c=cb, bid=row['book_id']:
                    c.toggle() if bid in applicable_ids and c.isEnabled() else None)

            status_lbl = QLabel('')
            try:
                status_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            except AttributeError:
                status_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            status_lbl.setMinimumWidth(170)

            _base = _orient_label(row['orientation'])
            sub_lbl = QLabel(_base)
            sub_lbl.setStyleSheet(_SUB_STYLE)

            top_row = QHBoxLayout()
            top_row.setSpacing(4)
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.addWidget(cb_box)
            top_row.addWidget(title_lbl, 3)
            top_row.addWidget(status_lbl, 1)

            sub_row = QHBoxLayout()
            sub_row.setContentsMargins(24, 0, 0, 2)
            sub_row.addWidget(sub_lbl)
            sub_row.addStretch()

            container_layout = QVBoxLayout()
            container_layout.setSpacing(1)
            container_layout.setContentsMargins(4, 4, 4, 4)
            container_layout.addLayout(top_row)
            container_layout.addLayout(sub_row)

            container = QWidget()
            container.setLayout(container_layout)
            list_layout.addWidget(container)

            checkboxes.append(cb)
            cb_map[row['book_id']]        = cb
            status_labels[row['book_id']] = status_lbl
            title_labels[row['book_id']]  = title_lbl
            sub_labels[row['book_id']]    = sub_lbl
            sub_base_text[row['book_id']] = _base

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        vl.addWidget(table_container)

        # Summary panel
        sp2 = QSizePolicy.Policy if PYQT6 else QSizePolicy
        result_te = QTextEdit()
        result_te.setReadOnly(True)
        result_te.setFixedHeight(80)
        result_te.setSizePolicy(sp2.Expanding, sp2.Fixed)
        result_te.setPlainText(_selection_summary())
        vl.addWidget(result_te)

        # Buttons
        try:
            std   = QDialogButtonBox.StandardButton
            bb    = QDialogButtonBox(std.Ok | std.Close)
        except AttributeError:
            bb    = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        ok_btn = bb.button(
            QDialogButtonBox.StandardButton.Ok if PYQT6 else QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setText('Apply')
        bb.accepted.connect(lambda: _on_apply())
        bb.rejected.connect(dlg.reject)
        vl.addWidget(bb)

        # ── Logic helpers ─────────────────────────────────────────

        def _is_applicable(orientation, going_h2v):
            if orientation == 'unknown':
                return True
            return orientation != ('vertical' if going_h2v else 'horizontal')

        def _already_status(orientation, going_h2v):
            if going_h2v and orientation == 'vertical':
                return 'Already Vertical'
            if not going_h2v and orientation == 'horizontal':
                return 'Already Horizontal'
            return ''

        def _update_apply_state():
            any_checked = any(
                cb.isChecked()
                for cb, row in zip(checkboxes, book_rows)
                if row['book_id'] in applicable_ids)
            if ok_btn:
                ok_btn.setEnabled(any_checked)
                ok_btn.setToolTip(
                    '' if any_checked else
                    'No books selected. Books already in the target layout are disabled.')
            _update_header_cb()

        def _update_header_cb():
            applicable_cbs = [cb for cb, row in zip(checkboxes, book_rows)
                               if row['book_id'] in applicable_ids]
            header_cb.blockSignals(True)
            try:
                if not applicable_cbs:
                    state = (Qt.CheckState.Unchecked if PYQT6 else Qt.Unchecked)
                else:
                    n = sum(1 for cb in applicable_cbs if cb.isChecked())
                    if n == 0:
                        state = (Qt.CheckState.Unchecked if PYQT6 else Qt.Unchecked)
                    elif n == len(applicable_cbs):
                        state = (Qt.CheckState.Checked if PYQT6 else Qt.Checked)
                    else:
                        state = (Qt.CheckState.PartiallyChecked
                                 if PYQT6 else Qt.PartiallyChecked)
                header_cb.setCheckState(state)
            except AttributeError:
                pass
            finally:
                header_cb.blockSignals(False)

        def _on_header_clicked():
            applicable_cbs = [cb for cb, row in zip(checkboxes, book_rows)
                               if row['book_id'] in applicable_ids]
            all_checked = (bool(applicable_cbs) and
                           all(cb.isChecked() for cb in applicable_cbs))
            for cb in applicable_cbs:
                cb.setChecked(not all_checked)
            _update_apply_state()

        def _apply_row_style(row, applicable, going_h2v, preserve_status=False):
            bid    = row['book_id']
            cb     = cb_map[bid]
            sl     = sub_labels[bid]
            lbl    = status_labels[bid]
            base   = sub_base_text[bid]
            reason = _already_status(row['orientation'], going_h2v)

            cb.setVisible(applicable)
            sl.setText(base)
            sl.setStyleSheet(_SUB_STYLE)

            if applicable:
                if not preserve_status:
                    lbl.setText('')
                    lbl.setStyleSheet('')
            else:
                if not preserve_status or not (
                        lbl.text().startswith('✅') or lbl.text().startswith('⚠')):
                    lbl.setText(reason)
                    lbl.setStyleSheet('color: #595959;')

        def _refresh_checks():
            going_h2v = rb_h2v.isChecked()
            applicable_ids.clear()
            for cb, row in zip(checkboxes, book_rows):
                applicable = _is_applicable(row['orientation'], going_h2v)
                if applicable:
                    applicable_ids.add(row['book_id'])
                cb.setVisible(applicable)
                cb.setEnabled(applicable)
                cb.setChecked(applicable)
                _apply_row_style(row, applicable, going_h2v, preserve_status=False)
            _update_apply_state()

        def _restore_cb_enabled():
            going_h2v = rb_h2v.isChecked()
            applicable_ids.clear()
            for cb, row in zip(checkboxes, book_rows):
                applicable = _is_applicable(row['orientation'], going_h2v)
                if applicable:
                    applicable_ids.add(row['book_id'])
                cb.setVisible(applicable)
                cb.setEnabled(applicable)
                _apply_row_style(row, applicable, going_h2v, preserve_status=True)
            _update_apply_state()

        def _lock_controls():
            rb_h2v.setEnabled(False)
            rb_v2h.setEnabled(False)
            header_cb.setEnabled(False)
            for cb in checkboxes:
                cb.setEnabled(False)

        def _unlock_controls():
            rb_h2v.setEnabled(True)
            rb_v2h.setEnabled(True)
            header_cb.setEnabled(True)
            _restore_cb_enabled()

        # ── Apply handler ─────────────────────────────────────────

        def _on_apply():
            tasks = [row for cb, row in zip(checkboxes, book_rows)
                     if cb.isChecked()]
            if not tasks:
                return

            going_h2v = rb_h2v.isChecked()
            target    = 'vertical' if going_h2v else 'horizontal'
            direction = 'H→V' if going_h2v else 'V→H'

            _lock_controls()
            if ok_btn:
                ok_btn.setEnabled(False)
            QApplication.processEvents()

            for row in tasks:
                lbl = status_labels[row['book_id']]
                lbl.setText('⏳ Converting…')
                lbl.setStyleSheet('color: #545454;')

            done    = [False]
            outcome = [None]

            worker = BulkOrientationWorker(tasks, target)

            def on_book_started(book_id):
                lbl = status_labels.get(book_id)
                if lbl:
                    lbl.setText('⏳ Converting…')
                    lbl.setStyleSheet('color: #545454;')

            def on_book_finished(book_id, ok, msg):
                lbl = status_labels.get(book_id)
                if lbl:
                    if ok:
                        lbl.setText('✅ Done')
                        lbl.setStyleSheet('color: green;')
                    else:
                        lbl.setText('⚠ Error')
                        lbl.setStyleSheet('color: red;')
                        lbl.setToolTip(msg)

            def on_done(ok, results, tb):
                done[0]    = True
                outcome[0] = (ok, results, tb)

            worker.book_started.connect(on_book_started)
            worker.book_finished.connect(on_book_finished)
            worker.finished.connect(on_done)
            worker.start()

            while not done[0]:
                QApplication.processEvents()
            worker.wait()

            ok2, results, tb = outcome[0]

            if not ok2:
                result_te.setPlainText(f'⚠ Unexpected error:\n{tb}')
                result_te.setVisible(True)
                _unlock_controls()
                return

            # Save back to Calibre
            saved       = 0
            save_errors = []
            for book_id, tmp_path, err in results:
                lbl = status_labels.get(book_id)
                if err or not tmp_path:
                    save_errors.append(f'Book {book_id}: {err}')
                    if lbl and lbl.text() != '⚠ Error':
                        lbl.setText('⚠ Conv. error')
                        lbl.setStyleSheet('color: red;')
                    continue
                try:
                    if prefs['keep_original']:
                        orig = next((r['epub'] for r in book_rows if r['book_id'] == book_id), None)
                        if orig:
                            try:
                                existing = db.formats(book_id)
                                if 'ORIGINAL_EPUB' not in (f.upper() for f in existing):
                                    db.add_format(book_id, 'ORIGINAL_EPUB', orig, replace=False)
                            except Exception:
                                pass
                    db.add_format(book_id, 'EPUB', tmp_path, replace=True)
                    saved += 1
                except Exception as e:
                    save_errors.append(f'Book {book_id}: save failed: {e}')
                    if lbl:
                        lbl.setText('⚠ Save error')
                        lbl.setStyleSheet('color: red;')
                        lbl.setToolTip(str(e))
                finally:
                    try: os.unlink(tmp_path)
                    except: pass

            self.gui.library_view.model().refresh_ids(
                list({r[0] for r in results}))

            # Update orientation in memory → prevent redundant re-conversion
            converted_ids = {r[0] for r in results if not r[2]}
            for row in book_rows:
                if row['book_id'] in converted_ids:
                    row['orientation'] = target
                    new_label = _orient_label(target)
                    sub_base_text[row['book_id']] = new_label
                    sub_labels[row['book_id']].setText(new_label)

            lines = [
                f'✅ Converted {saved} book(s)  [{direction}]'
            ]
            if save_errors:
                lines.append(f'⚠ {len(save_errors)} error(s):')
                lines += [f'  {e}' for e in save_errors[:5]]
            lines += ['', _selection_summary()]

            result_te.setVisible(True)
            result_te.setPlainText('\n'.join(lines))
            _unlock_controls()

        # Wire signals
        rb_h2v.toggled.connect(lambda _: _refresh_checks())
        for cb in checkboxes:
            cb.stateChanged.connect(lambda _: _update_apply_state())
        header_cb.clicked.connect(_on_header_clicked)

        if not book_rows:
            _lock_controls()
            if ok_btn:
                ok_btn.setEnabled(False)
                ok_btn.setToolTip('No EPUB books in selection.')

        _refresh_checks()

        dlg.exec() if PYQT6 else dlg.exec_()

    # ── Chinese S↔T conversion ────────────────────────────────────

    def open_chinese_dialog(self):
        ids = self._selected_ids()
        if not ids:
            warning_dialog(self.gui, 'No Book Selected',
                'Select one or more Chinese EPUB/TXT books first.', show=True)
            return
        self._show_chinese_dialog(ids)

    def _show_chinese_dialog(self, book_ids):
        try:
            from calibre_plugins.furigana_ruby.lang_detect import (
                detect_book_language, lang_display,
                detect_script_from_epub, detect_script_from_text)
            from calibre_plugins.furigana_ruby.chinese_engine import VARIANTS_S2T
        except ImportError:
            from lang_detect import (detect_book_language, lang_display,
                                     detect_script_from_epub, detect_script_from_text)
            from chinese_engine import VARIANTS_S2T

        db = self.gui.current_db.new_api

        # ── Scan selected books ───────────────────────────────────
        book_rows = []
        excluded_counts = {}   # language label → count of books not listed

        for book_id in book_ids:
            title     = db.field_for('title', book_id) or f'Book {book_id}'
            epub_path = (db.format_abspath(book_id, 'EPUB')
                         if db.has_format(book_id, 'EPUB') else None)
            html_path = (db.format_abspath(book_id, 'HTML')
                         if db.has_format(book_id, 'HTML') else None)
            fb2_path  = (db.format_abspath(book_id, 'FB2')
                         if db.has_format(book_id, 'FB2')  else None)
            txt_path  = (db.format_abspath(book_id, 'TXT')
                         if db.has_format(book_id, 'TXT')  else None)
            if not epub_path and not html_path and not fb2_path and not txt_path:
                excluded_counts['no supported format'] = (
                    excluded_counts.get('no supported format', 0) + 1)
                continue

            if epub_path:
                lang_info = detect_book_language(epub_path)
            else:
                lang_info = {'lang_raw': '', 'is_japanese': False,
                             'is_chinese': False, 'is_korean': False,
                             'is_simplified': False, 'is_traditional': False}
                # Sample from the best available non-EPUB format
                sample_path = html_path or fb2_path or txt_path
                if sample_path:
                    try:
                        with open(sample_path, 'r',
                                  encoding='utf-8', errors='ignore') as f:
                            sample = f.read(4000)
                        has_kana = any(0x3040 <= ord(c) <= 0x30FF for c in sample)
                        has_han  = any(0x4E00 <= ord(c) <= 0x9FFF for c in sample)
                        if has_han and not has_kana:
                            lang_info['is_chinese'] = True
                    except Exception:
                        pass

            # If Chinese but script not specified in metadata, detect from content
            if (lang_info['is_chinese']
                    and not lang_info['is_simplified']
                    and not lang_info['is_traditional']):
                if epub_path:
                    script = detect_script_from_epub(epub_path)
                else:
                    sample_path = html_path or fb2_path or txt_path
                    try:
                        with open(sample_path, 'r',
                                  encoding='utf-8', errors='ignore') as f:
                            script = detect_script_from_text(f.read(6000))
                    except Exception:
                        script = 'unknown'
                if script == 'simplified':
                    lang_info['is_simplified'] = True
                elif script == 'traditional':
                    lang_info['is_traditional'] = True

            # Japanese and Korean: excluded from the list but counted for the summary
            if lang_info['is_japanese']:
                excluded_counts['Japanese'] = excluded_counts.get('Japanese', 0) + 1
                continue
            if lang_info['is_korean']:
                excluded_counts['Korean'] = excluded_counts.get('Korean', 0) + 1
                continue

            book_rows.append({'book_id': book_id, 'title': title,
                               'epub': epub_path, 'html': html_path,
                               'fb2': fb2_path,  'txt': txt_path,
                               'lang_info': lang_info})

        total_selected = len(book_ids)
        n_chinese      = len(book_rows)

        def _selection_summary():
            """One-line breakdown of the full selection for the summary panel."""
            parts = []
            if n_chinese:
                parts.append(f'{n_chinese} Chinese')
            for lang, count in excluded_counts.items():
                if lang != 'no supported format':
                    parts.append(f'{count} {lang}')
            if excluded_counts.get('no supported format', 0):
                parts.append(
                    f"{excluded_counts['no supported format']} without supported format")
            breakdown = ' · '.join(parts) if parts else 'none'
            lines = [f'Selection: {total_selected} book(s) — {breakdown}']
            excluded_non_chinese = {k: v for k, v in excluded_counts.items()
                                    if k != 'no EPUB/TXT'}
            if excluded_non_chinese:
                exc_str = '  and  '.join(
                    f'{v} {k}' for k, v in excluded_non_chinese.items())
                lines.append(
                    f'{exc_str} book(s) not listed — Chinese conversion only.')
            return '\n'.join(lines)

        if not book_rows:
            # All selected books are non-Chinese — show dialog anyway so the
            # summary explains why nothing is listed
            summary_only = True
        else:
            summary_only = False

        # ── Build dialog ──────────────────────────────────────────
        dlg = QDialog(self.gui)
        dlg.setWindowTitle('Convert Chinese S↔T')
        dlg.setMinimumWidth(680)
        dlg.resize(700, 520)

        vl = QVBoxLayout()
        vl.setSpacing(8)
        dlg.setLayout(vl)

        # Direction
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel('<b>Direction:</b>'))
        rb_s2t = QRadioButton('Simplified → Traditional  (S→T)')
        rb_t2s = QRadioButton('Traditional → Simplified  (T→S)')
        rb_s2t.setChecked(True)
        dir_row.addWidget(rb_s2t)
        dir_row.addWidget(rb_t2s)
        dir_row.addStretch()
        vl.addLayout(dir_row)

        # Variant (S→T only — T→S always uses standard Mainland Simplified)
        var_row = QHBoxLayout()
        var_lbl = QLabel('Variant:')
        var_row.addWidget(var_lbl)
        var_combo = QComboBox()
        var_combo.setMinimumWidth(300)
        t2s_static_lbl = QLabel('Mainland China Simplified (standard)')
        t2s_static_lbl.setStyleSheet('color: #545454;')
        var_row.addWidget(var_combo)
        var_row.addWidget(t2s_static_lbl)
        var_row.addStretch()
        vl.addLayout(var_row)

        var_desc_lbl = QLabel('')
        var_desc_lbl.setWordWrap(True)
        var_desc_lbl.setStyleSheet('color: #545454; font-size: 11px; padding-left: 60px;')
        vl.addWidget(var_desc_lbl)

        # Metadata checkbox
        meta_cb = QCheckBox('Also update title and author metadata')
        meta_cb.setChecked(True)
        vl.addWidget(meta_cb)

        # Book list header — styled like a table header row.
        # Use object-name selector so child widgets don't inherit the border.
        hdr_widget = QWidget()
        hdr_widget.setObjectName('bookListHeader')
        hdr_widget.setStyleSheet(
            '#bookListHeader { background-color: #d4d4d4; '
            'border: 1px solid #b8b8b8; border-bottom: none; }')
        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(4, 3, 4, 3)
        hdr_layout.setSpacing(4)

        header_cb = QCheckBox()
        header_cb.setTristate(True)
        header_cb.setToolTip('Select / deselect all applicable books')

        # Fixed-width wrapper — centered so checkbox aligns with row checkboxes
        hdr_cb_box = QWidget()
        hdr_cb_box.setFixedWidth(20)
        hdr_cb_inner = QHBoxLayout()
        hdr_cb_inner.setContentsMargins(0, 0, 0, 0)
        hdr_cb_inner.setSpacing(0)
        hdr_cb_inner.addStretch()
        hdr_cb_inner.addWidget(header_cb)
        hdr_cb_inner.addStretch()
        hdr_cb_box.setLayout(hdr_cb_inner)

        hdr_books_lbl = QLabel('<b>Books</b>')
        hdr_status_lbl = QLabel('<b>Status</b>')
        hdr_status_lbl.setMinimumWidth(170)
        try:
            hdr_status_lbl.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        except AttributeError:
            hdr_status_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        hdr_layout.addWidget(hdr_cb_box)
        hdr_layout.addWidget(hdr_books_lbl, 3)
        hdr_layout.addWidget(hdr_status_lbl, 1)
        hdr_widget.setLayout(hdr_layout)

        # Scrollable book list — border joins flush with header bottom
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea { border: 1px solid #b8b8b8; border-top: none; }')
        sp = QSizePolicy.Policy if PYQT6 else QSizePolicy
        scroll.setSizePolicy(sp.Expanding, sp.Expanding)

        # Wrap header + scroll in a zero-spacing container so they sit flush
        table_container = QWidget()
        table_vl = QVBoxLayout()
        table_vl.setSpacing(0)
        table_vl.setContentsMargins(0, 0, 0, 0)
        table_vl.addWidget(hdr_widget)
        table_vl.addWidget(scroll)
        table_container.setLayout(table_vl)

        list_widget = QWidget()
        list_layout = QVBoxLayout()
        list_layout.setSpacing(3)
        list_layout.setContentsMargins(4, 4, 4, 4)
        list_widget.setLayout(list_layout)

        checkboxes    = []   # parallel to book_rows
        status_labels = {}   # book_id → QLabel
        title_labels  = {}   # book_id → ElidedLabel
        sub_labels    = {}   # book_id → QLabel  (language · formats [· reason])
        sub_base_text = {}   # book_id → plain "lang  ·  fmts" (no reason suffix)
        cb_map        = {}   # book_id → QCheckBox (for _apply_row_style)
        applicable_ids = set()   # book_ids currently applicable; avoids isVisible quirks

        _SUB_STYLE = 'color: #545454; font-size: 11px;'

        def _script_label(li):
            """Return a human-readable script label for the language column."""
            if li.get('is_simplified'):
                return 'Simplified (简体)'
            if li.get('is_traditional'):
                return 'Traditional (繁體)'
            if li.get('is_chinese'):
                return 'Chinese (中文)'
            return lang_display(li)

        sp_row = QSizePolicy.Policy if PYQT6 else QSizePolicy

        for row in book_rows:
            li   = row['lang_info']
            lang = _script_label(li)
            fmts = '  '.join(f for f, p in [('EPUB', row['epub']),
                                              ('HTML', row['html']),
                                              ('FB2',  row['fb2']),
                                              ('TXT',  row['txt'])] if p)

            # ── Checkbox in fixed-width wrapper so alignment holds when hidden
            cb = QCheckBox()
            cb_box = QWidget()
            cb_box.setFixedWidth(20)
            cb_box_inner = QHBoxLayout()
            cb_box_inner.setContentsMargins(0, 0, 0, 0)
            cb_box_inner.setSpacing(0)
            cb_box_inner.addStretch()
            cb_box_inner.addWidget(cb)
            cb_box_inner.addStretch()
            cb_box.setLayout(cb_box_inner)

            # ── Title (eliding, clickable — toggles the checkbox)
            title_lbl = ElidedLabel(row['title'])
            title_lbl.setToolTip(row['title'])
            title_lbl.setSizePolicy(sp_row.Expanding, sp_row.Preferred)
            title_lbl.clicked.connect(
                lambda _=None, c=cb, bid=row['book_id']:
                    c.toggle() if bid in applicable_ids and c.isEnabled() else None)

            # ── Status (right column, left-aligned to match header)
            status_lbl = QLabel('')
            try:
                status_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            except AttributeError:
                status_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            status_lbl.setMinimumWidth(170)

            # ── Sub-label: language · formats  (reason appended when disabled)
            _base = f'{lang}  ·  {fmts}'
            sub_lbl = QLabel(_base)
            sub_lbl.setStyleSheet(_SUB_STYLE)

            # ── Top row: [cb_box][title ×3] [status ×1]
            top_row = QHBoxLayout()
            top_row.setSpacing(4)
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.addWidget(cb_box)
            top_row.addWidget(title_lbl, 3)
            top_row.addWidget(status_lbl, 1)

            # ── Sub row: indented 24 px to align under title
            sub_row = QHBoxLayout()
            sub_row.setContentsMargins(24, 0, 0, 2)
            sub_row.addWidget(sub_lbl)
            sub_row.addStretch()

            # ── Container
            container_layout = QVBoxLayout()
            container_layout.setSpacing(1)
            container_layout.setContentsMargins(4, 4, 4, 4)
            container_layout.addLayout(top_row)
            container_layout.addLayout(sub_row)

            container = QWidget()
            container.setLayout(container_layout)
            list_layout.addWidget(container)

            checkboxes.append(cb)
            cb_map[row['book_id']]        = cb
            status_labels[row['book_id']] = status_lbl
            title_labels[row['book_id']]  = title_lbl
            sub_labels[row['book_id']]    = sub_lbl
            sub_base_text[row['book_id']] = _base

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        vl.addWidget(table_container)

        # Summary panel — visible from open, updated after Apply
        sp2 = QSizePolicy.Policy if PYQT6 else QSizePolicy
        result_te = QTextEdit()
        result_te.setReadOnly(True)
        result_te.setFixedHeight(80)
        result_te.setSizePolicy(sp2.Expanding, sp2.Fixed)
        result_te.setPlainText(_selection_summary())
        vl.addWidget(result_te)

        # Buttons
        try:
            std = QDialogButtonBox.StandardButton
            bb  = QDialogButtonBox(std.Ok | std.Close)
        except AttributeError:
            bb  = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        ok_btn = bb.button(
            QDialogButtonBox.StandardButton.Ok if PYQT6 else QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setText('Apply')
        close_btn = bb.button(
            QDialogButtonBox.StandardButton.Close if PYQT6
            else QDialogButtonBox.Close)
        bb.accepted.connect(lambda: _on_apply())
        bb.rejected.connect(dlg.reject)
        vl.addWidget(bb)

        # ── Logic helpers ─────────────────────────────────────────

        def _is_applicable(lang_info, going_s2t):
            """
            True if this book (already known to be Chinese or unknown) can be
            meaningfully converted in the given direction.
            - Simplified  → S→T only
            - Traditional → T→S only
            - Unknown Chinese (bare zh) or no metadata → both directions
            """
            li = lang_info
            if not li['is_chinese']:
                return True   # unknown metadata — show as applicable, let user decide
            if going_s2t:
                return li['is_simplified'] or not li['is_traditional']
            else:
                return li['is_traditional'] or not li['is_simplified']

        def _update_apply_state():
            """Enable Apply iff at least one applicable book is checked."""
            any_checked = any(
                cb.isChecked()
                for cb, row in zip(checkboxes, book_rows)
                if row['book_id'] in applicable_ids)
            if ok_btn:
                ok_btn.setEnabled(any_checked)
                if not any_checked:
                    ok_btn.setToolTip(
                        'No books are selected. Books already in the target '
                        'variant are disabled.')
                else:
                    ok_btn.setToolTip('')
            _update_header_cb()

        def _already_status(lang_info, going_s2t):
            """Return a status label for rows that don't need conversion."""
            li = lang_info
            if going_s2t and li.get('is_traditional'):
                return 'Already Traditional'
            if not going_s2t and li.get('is_simplified'):
                return 'Already Simplified'
            return ''

        def _update_header_cb():
            """Sync header tri-state checkbox to current row selection state."""
            applicable_cbs = [cb for cb, row in zip(checkboxes, book_rows)
                               if row['book_id'] in applicable_ids]
            header_cb.blockSignals(True)
            try:
                if not applicable_cbs:
                    state = (Qt.CheckState.Unchecked if PYQT6 else Qt.Unchecked)
                else:
                    n_checked = sum(1 for cb in applicable_cbs if cb.isChecked())
                    if n_checked == 0:
                        state = (Qt.CheckState.Unchecked if PYQT6 else Qt.Unchecked)
                    elif n_checked == len(applicable_cbs):
                        state = (Qt.CheckState.Checked if PYQT6 else Qt.Checked)
                    else:
                        state = (Qt.CheckState.PartiallyChecked
                                 if PYQT6 else Qt.PartiallyChecked)
                header_cb.setCheckState(state)
            except AttributeError:
                pass
            finally:
                header_cb.blockSignals(False)

        def _on_header_clicked():
            """All checked → uncheck all; otherwise → check all applicable."""
            applicable_cbs = [cb for cb, row in zip(checkboxes, book_rows)
                               if row['book_id'] in applicable_ids]
            all_checked = (bool(applicable_cbs) and
                           all(cb.isChecked() for cb in applicable_cbs))
            for cb in applicable_cbs:
                cb.setChecked(not all_checked)
            _update_apply_state()

        def _apply_row_style(row, applicable, going_s2t, preserve_status=False):
            """Update visual style for a single book row."""
            bid    = row['book_id']
            cb     = cb_map[bid]
            tl     = title_labels[bid]
            sl     = sub_labels[bid]
            lbl    = status_labels[bid]
            base   = sub_base_text[bid]
            reason = _already_status(row['lang_info'], going_s2t)

            tl.setStyleSheet('')   # title always black

            # Show checkbox only for applicable rows; wrapper keeps alignment
            cb.setVisible(applicable)

            # Sub-label always shows plain "lang · formats" — no reason suffix
            sl.setText(base)
            sl.setStyleSheet(_SUB_STYLE)

            if applicable:
                if not preserve_status:
                    lbl.setText('')
                    lbl.setStyleSheet('')
            else:
                # Right-side status column shows why no checkbox is present
                if not preserve_status or not (
                        lbl.text().startswith('✅') or lbl.text().startswith('⚠')):
                    lbl.setText(reason)
                    lbl.setStyleSheet('color: #595959;')

        def _refresh_checks():
            """Re-evaluate enabled/checked/visible state for all rows. Resets status labels."""
            going_s2t = rb_s2t.isChecked()
            applicable_ids.clear()
            for cb, row in zip(checkboxes, book_rows):
                applicable = _is_applicable(row['lang_info'], going_s2t)
                if applicable:
                    applicable_ids.add(row['book_id'])
                cb.setVisible(applicable)
                cb.setEnabled(applicable)
                cb.setChecked(applicable)
                _apply_row_style(row, applicable, going_s2t, preserve_status=False)
            _update_apply_state()

        def _restore_cb_enabled():
            """Re-enable applicable checkboxes after processing; preserve result
            status labels (✅ / ⚠) but update 'already' labels on newly disabled rows."""
            going_s2t = rb_s2t.isChecked()
            applicable_ids.clear()
            for cb, row in zip(checkboxes, book_rows):
                applicable = _is_applicable(row['lang_info'], going_s2t)
                if applicable:
                    applicable_ids.add(row['book_id'])
                cb.setVisible(applicable)
                cb.setEnabled(applicable)
                _apply_row_style(row, applicable, going_s2t, preserve_status=True)
            _update_apply_state()

        def _update_var_desc():
            idx = var_combo.currentIndex()
            if 0 <= idx < len(VARIANTS_S2T):
                var_desc_lbl.setText(VARIANTS_S2T[idx][3])
            else:
                var_desc_lbl.setText('')

        def _refresh_variants():
            going_s2t = rb_s2t.isChecked()
            var_lbl.setVisible(going_s2t)
            var_combo.setVisible(going_s2t)
            t2s_static_lbl.setVisible(not going_s2t)
            var_desc_lbl.setVisible(going_s2t)
            if going_s2t:
                var_combo.blockSignals(True)
                var_combo.clear()
                saved = prefs['s2t_variant']
                for v, label, _dir, _desc in VARIANTS_S2T:
                    var_combo.addItem(label, v)
                for i, (v, *_) in enumerate(VARIANTS_S2T):
                    if v == saved:
                        var_combo.setCurrentIndex(i)
                        break
                var_combo.blockSignals(False)
                _update_var_desc()
            _refresh_checks()

        def _lock_controls():
            """Disable everything during processing."""
            rb_s2t.setEnabled(False)
            rb_t2s.setEnabled(False)
            var_combo.setEnabled(False)
            meta_cb.setEnabled(False)
            header_cb.setEnabled(False)
            for cb in checkboxes:
                cb.setEnabled(False)

        def _unlock_controls():
            """Re-enable top controls; checkboxes restored by _restore_cb_enabled."""
            rb_s2t.setEnabled(True)
            rb_t2s.setEnabled(True)
            var_combo.setEnabled(True)
            meta_cb.setEnabled(True)
            header_cb.setEnabled(True)
            _restore_cb_enabled()

        # Wire up signals
        rb_s2t.toggled.connect(lambda _: _refresh_variants())
        var_combo.currentIndexChanged.connect(lambda _: _update_var_desc())
        for cb in checkboxes:
            cb.stateChanged.connect(lambda _: _update_apply_state())
        header_cb.clicked.connect(_on_header_clicked)

        # Initial populate
        _refresh_variants()

        if summary_only:
            # No Chinese books — disable everything except Close
            _lock_controls()
            if ok_btn:
                ok_btn.setEnabled(False)
                ok_btn.setToolTip('No Chinese books in selection.')

        # ── Apply handler ─────────────────────────────────────────

        def _on_apply():
            tasks = [row for cb, row in zip(checkboxes, book_rows)
                     if cb.isChecked()]
            if not tasks:
                return

            going_s2t = rb_s2t.isChecked()
            variant   = var_combo.currentData() if going_s2t else 't2s'
            direction = 'S→T' if going_s2t else 'T→S'
            if not variant:
                return

            _lock_controls()
            if ok_btn:
                ok_btn.setEnabled(False)
            result_te.setVisible(False)
            QApplication.processEvents()

            # Reset status labels for the books being processed
            for row in tasks:
                lbl = status_labels[row['book_id']]
                lbl.setText('')
                lbl.setStyleSheet('')

            done    = [False]
            outcome = [None]

            worker = ChineseWorker(tasks, variant)

            def on_book_started(book_id):
                lbl = status_labels.get(book_id)
                if lbl:
                    lbl.setText('⏳ Converting…')
                    lbl.setStyleSheet('color: #545454;')

            def on_book_finished(book_id, ok, msg):
                lbl = status_labels.get(book_id)
                if lbl:
                    if ok:
                        lbl.setText('✅ Done')
                        lbl.setStyleSheet('color: green;')
                    else:
                        lbl.setText('⚠ Error')
                        lbl.setStyleSheet('color: red;')
                        lbl.setToolTip(msg)

            def on_done(ok, results, tb):
                done[0]    = True
                outcome[0] = (ok, results, tb)

            worker.book_started.connect(on_book_started)
            worker.book_finished.connect(on_book_finished)
            worker.finished.connect(on_done)
            worker.start()

            while not done[0]:
                QApplication.processEvents()

            worker.wait()

            ok2, results, tb = outcome[0]

            if not ok2:
                result_te.setPlainText(f'⚠ Unexpected error:\n{tb}')
                result_te.setVisible(True)
                _unlock_controls()
                _update_apply_state()
                return

            # Save converted files back to Calibre
            saved       = 0
            save_errors = []
            for book_id, fmt, tmp_path, err in results:
                lbl = status_labels.get(book_id)
                if err or not tmp_path:
                    save_errors.append(f'{fmt} ({book_id}): {err}')
                    if lbl and lbl.text() != '⚠ Error':
                        lbl.setText('⚠ Conv. error')
                        lbl.setStyleSheet('color: red;')
                    continue
                try:
                    if prefs['keep_original']:
                        orig = next(
                            (t.get(fmt.lower()) for t in tasks if t['book_id'] == book_id),
                            None,
                        )
                        if orig:
                            orig_fmt = f'ORIGINAL_{fmt}'
                            try:
                                existing = db.formats(book_id)
                                if orig_fmt.upper() not in (f.upper() for f in existing):
                                    db.add_format(book_id, orig_fmt, orig, replace=False)
                            except Exception:
                                pass
                    db.add_format(book_id, fmt, tmp_path, replace=True)
                    saved += 1
                except Exception as e:
                    save_errors.append(f'{fmt} ({book_id}): save failed: {e}')
                    if lbl:
                        lbl.setText('⚠ Save error')
                        lbl.setStyleSheet('color: red;')
                        lbl.setToolTip(str(e))
                finally:
                    try: os.unlink(tmp_path)
                    except: pass

            # Update metadata (title + authors) if requested
            meta_updated = 0
            meta_errors  = []
            if meta_cb.isChecked():
                try:
                    try:
                        from calibre_plugins.furigana_ruby.chinese_engine import _get_converter
                    except ImportError:
                        from chinese_engine import _get_converter
                    converter     = _get_converter(variant)
                    seen_book_ids = set()
                    for book_id, _, tmp_path, err in results:
                        if err or book_id in seen_book_ids:
                            continue
                        seen_book_ids.add(book_id)
                        try:
                            title     = db.field_for('title', book_id) or ''
                            new_title = converter.convert(title)
                            if new_title != title:
                                db.set_field('title', {book_id: new_title})

                            authors     = list(db.field_for('authors', book_id) or [])
                            new_authors = [converter.convert(a) for a in authors]
                            if new_authors != authors:
                                db.set_field('authors', {book_id: new_authors})

                            meta_updated += 1
                        except Exception as e:
                            meta_errors.append(f'Book {book_id}: {e}')
                except Exception as e:
                    meta_errors.append(f'Converter unavailable: {e}')

            self.gui.library_view.model().refresh_ids(
                list({r[0] for r in results}))

            # Summary
            lines = [
                f'✅ Converted {saved} format(s) across {len(tasks)} book(s)'
                f'  [{direction} / {variant}]'
            ]
            if meta_updated:
                lines.append(f'   Updated metadata for {meta_updated} book(s)')
            if save_errors:
                lines.append(f'⚠ {len(save_errors)} save error(s):')
                lines += [f'  {e}' for e in save_errors[:5]]
            if meta_errors:
                lines.append(f'⚠ {len(meta_errors)} metadata error(s):')
                lines += [f'  {e}' for e in meta_errors[:3]]
            lines += ['', _selection_summary()]

            result_te.setVisible(True)
            result_te.setPlainText('\n'.join(lines))

            # Update lang_info in memory for successfully converted books so
            # _restore_cb_enabled (called by _unlock_controls) correctly
            # disables them for the same direction on the next Apply.
            converted_ids = {r[0] for r in results if not r[3]}
            for row in book_rows:
                if row['book_id'] in converted_ids:
                    if going_s2t:
                        row['lang_info']['is_simplified'] = False
                        row['lang_info']['is_traditional'] = True
                    else:
                        row['lang_info']['is_traditional'] = False
                        row['lang_info']['is_simplified'] = True
                    # Rebuild sub_base_text and update widget directly
                    new_lang = _script_label(row['lang_info'])
                    fmts = '  '.join(f for f, p in [
                        ('EPUB', row['epub']), ('HTML', row['html']),
                        ('FB2',  row['fb2']),  ('TXT',  row['txt'])] if p)
                    new_base = f'{new_lang}  ·  {fmts}'
                    sub_base_text[row['book_id']] = new_base
                    sub_labels[row['book_id']].setText(new_base)

            _unlock_controls()
            _update_apply_state()

        dlg.exec() if PYQT6 else dlg.exec_()

    # ── Settings ──────────────────────────────────────────────────

    def open_settings(self):
        try:
            from calibre_plugins.furigana_ruby.config import ConfigWidget
        except ImportError:
            from config import ConfigWidget

        dlg = QDialog(self.gui)
        dlg.setWindowTitle('FuriganaRuby — Preferences')
        dlg.setMinimumWidth(500)
        vl = QVBoxLayout(dlg)
        widget = ConfigWidget()
        vl.addWidget(widget)
        bb = QDialogButtonBox(
            (QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            if PYQT6 else (QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        vl.addWidget(bb)
        if (dlg.exec() if PYQT6 else dlg.exec_()):
            widget.save_settings()

    # ── About ─────────────────────────────────────────────────────

    def show_about(self):
        from calibre_plugins.furigana_ruby import FuriganaPluginBase
        ver = '.'.join(str(x) for x in FuriganaPluginBase.version)

        html = (
            f'<h3>振り仮名 Ruby & More Plugin <span style="font-size:small;color:grey;">v{ver}</span></h3>'
            '<p>A Calibre plugin for East Asian ebooks. Select one or more books, '
            'click the <b>振り仮名</b> toolbar button, and choose a command.</p>'
            '<hr/>'

            '<p><b>振り仮名 &mdash; Edit Ruby&hellip;</b>'
            '&nbsp;&nbsp;<span style="color:#545454;font-size:small;">Japanese EPUBs</span></p>'
            '<p style="margin:0 0 0 12px;color:#333;">'
            'Adds or removes furigana (reading aids) above kanji, filtered by JLPT level '
            '(N5 &rarr; N1). Publisher-supplied ruby is never overwritten. '
            'Auto-generated ruby appears in <span style="color:#4a72c4">blue</span>; '
            'use the in-viewer toggle (&#x1F233; / &#x1F4D6; / &#x1F21A;) to switch between '
            'all, publisher-only, or hidden.</p>'
            '<hr/>'

            '<p><b>繁 &mdash; Convert Chinese S&harr;T&hellip;</b>'
            '&nbsp;&nbsp;<span style="color:#545454;font-size:small;">Chinese &middot; EPUB &middot; HTML &middot; FB2 &middot; TXT</span></p>'
            '<p style="margin:0 0 0 12px;color:#333;">'
            'Converts between Simplified and Traditional Chinese. '
            'Supports 8 OpenCC variants including Taiwan (正體), Hong Kong (港式繁體), '
            'and phrase-level vocabulary conversion. '
            'Text nodes only &mdash; tags, CSS, and scripts are never modified.</p>'
            '<hr/>'

            '<p><b>&harr; &mdash; Convert Layout&hellip;</b>'
            '&nbsp;&nbsp;<span style="color:#545454;font-size:small;">Japanese &middot; Chinese &middot; Korean EPUBs</span></p>'
            '<p style="margin:0 0 0 12px;color:#333;">'
            'Switches the text direction between horizontal (左&rarr;右) and vertical (縦書き). '
            'Updates CSS writing-mode, OPF page-progression-direction, '
            'and repositions the ruby toggle button to match.</p>'
            '<hr/>'

            '<p><b>&#128269; &mdash; Auto-Import Watch Folders</b>'
            '&nbsp;&nbsp;<span style="color:#545454;font-size:small;">companion script &middot; macOS</span></p>'
            '<p style="margin:0 0 0 12px;color:#333;">'
            'The <a href="https://github.com/tobethesidekick/calibre-monitor">Calibre Monitor</a> '
            'companion script watches folders for new ebook files and imports them automatically, '
            'applying Chinese conversion and furigana annotation on the way in. '
            'Because it runs as a macOS background service (LaunchAgent), it works '
            '<b>even while Calibre is closed</b> &mdash; ideal for iCloud Drive folders '
            'shared across devices. Settings are configured in this plugin\'s Preferences panel '
            'and read by the monitor at startup.</p>'
        )

        dlg = QDialog(self.gui)
        dlg.setWindowTitle('振り仮名 Ruby & More Plugin')
        dlg.setMinimumWidth(420)
        dlg.resize(460, 340)

        vl = QVBoxLayout()
        vl.setContentsMargins(12, 12, 12, 8)
        vl.setSpacing(8)
        dlg.setLayout(vl)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)
        browser.setFrameShape(QFrame.Shape.NoFrame if PYQT6 else QFrame.NoFrame)
        vl.addWidget(browser)

        try:
            std = QDialogButtonBox.StandardButton
            bb  = QDialogButtonBox(std.Ok)
        except AttributeError:
            bb  = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(dlg.accept)
        vl.addWidget(bb)

        dlg.exec() if PYQT6 else dlg.exec_()

    # ── Update check ──────────────────────────────────────────────

    def check_for_updates(self):
        """
        Query the GitHub releases API and compare with the installed version.
        Shows a dialog with a download link if a newer release exists.
        Uses only Python stdlib — no extra dependencies.
        """
        import json
        from urllib.request import urlopen, Request
        from urllib.error   import URLError
        from calibre_plugins.furigana_ruby import FuriganaPluginBase

        local     = FuriganaPluginBase.version           # e.g. (1, 2, 0)
        local_str = '.'.join(str(x) for x in local)
        api_url   = ('https://api.github.com/repos/'
                     'tobethesidekick/furigana-ruby/releases/latest')
        releases_url = ('https://github.com/tobethesidekick/'
                        'furigana-ruby/releases/latest')

        try:
            req  = Request(api_url,
                           headers={'User-Agent': 'FuriganaRuby-Calibre-Plugin'})
            resp = urlopen(req, timeout=10)
            data = json.loads(resp.read().decode('utf-8'))

            tag       = data.get('tag_name', '').lstrip('v')   # "1.2.0"
            parts     = [int(x) for x in tag.split('.') if x.isdigit()]
            remote    = tuple(parts[:3])
            remote_str = '.'.join(str(x) for x in remote)
            html_url  = data.get('html_url', releases_url)

            if remote > local:
                info_dialog(
                    self.gui, 'Update Available',
                    f'<h3>🎉 Update available: v{remote_str}</h3>'
                    f'Installed version: v{local_str}<br><br>'
                    f'<a href="{html_url}">Download v{remote_str} from GitHub</a><br><br>'
                    f'<small>Download <b>FuriganaRuby.zip</b>, then install via<br>'
                    f'Calibre → Preferences → Plugins → Load plugin from file.</small>',
                    show=True)
            else:
                info_dialog(
                    self.gui, 'Up to Date',
                    f'<h3>✓ You are up to date</h3>'
                    f'Installed: v{local_str}<br><br>'
                    f'<a href="{releases_url}">View releases on GitHub</a>',
                    show=True)

        except URLError as e:
            info_dialog(
                self.gui, 'Update Check Failed',
                f'<b>Could not reach GitHub.</b><br><br>'
                f'{e}<br><br>'
                f'Check your internet connection or visit<br>'
                f'<a href="{releases_url}">GitHub releases</a> manually.',
                show=True)
        except Exception as e:
            info_dialog(
                self.gui, 'Update Check Failed',
                f'<b>Unexpected error:</b><br>{e}<br><br>'
                f'<a href="{releases_url}">GitHub releases</a>',
                show=True)
