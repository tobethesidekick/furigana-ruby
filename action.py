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
    from PyQt6.QtGui import (QIcon, QAction, QPainter, QPixmap,
                              QColor, QFont, QBrush, QPen, QPainterPath)
    from PyQt6.QtCore import QRect, QRectF, QSize
    PYQT6 = True
except ImportError:
    from PyQt5.Qt import (QMenu, QProgressDialog, QApplication,
                           QToolButton, QDialog, QVBoxLayout,
                           QHBoxLayout, QCheckBox, QLabel,
                           QGroupBox, QDialogButtonBox, QPushButton,
                           QSizePolicy, QTextEdit, QTextBrowser,
                           QComboBox, QRadioButton, QButtonGroup,
                           QScrollArea, QWidget, QFrame, Qt, QThread,
                           pyqtSignal, QIcon, QAction, QPainter,
                           QPixmap, QColor, QFont, QBrush,
                           QPen, QPainterPath, QRect, QRectF)
    PYQT6 = False

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, info_dialog, warning_dialog
from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/furigana_ruby')
_script_cache = JSONConfig('plugins/furigana_ruby_script')
prefs.defaults['annotate_levels']        = ['N1', 'N2', 'N3']
prefs.defaults['tile_action']            = 'ruby'
prefs.defaults['keep_original']          = False
prefs.defaults['auto_chinese_enabled']   = False
prefs.defaults['auto_chinese_direction'] = 's2t'
prefs.defaults['s2t_variant']            = 's2twp'
prefs.defaults['t2s_variant']            = 't2s'
prefs.defaults['auto_ruby_enabled']      = False
prefs.defaults['auto_ruby_levels']       = ['N1', 'N2', 'N3']
prefs.defaults['manual_engine']          = 'enhanced'
prefs.defaults['auto_engine']            = 'enhanced'
prefs.defaults['include_viewer_toggle']  = False

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


class WrappingClickableLabel(QLabel):
    """
    A word-wrapping QLabel with a clicked() signal so long book titles
    wrap to a second line instead of being elided, while still toggling
    the adjacent checkbox on click.

    minimumSizeHint() is overridden to return a near-zero width so the
    label never forces the row layout wider than the scroll viewport
    (which would push the Status column off-screen).
    """
    clicked = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)

    def minimumSizeHint(self):
        fm = self.fontMetrics()
        return QSize(0, fm.height())

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

    def __init__(self, tasks, variant, target_lang=None):
        super().__init__()
        self.tasks       = tasks
        self.variant     = variant
        self.target_lang = target_lang

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
                                         variant=self.variant,
                                         target_lang=self.target_lang)
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
                 remove_levels=None, engine=None):
        super().__init__()
        self.epub_path       = epub_path
        self.output_path     = output_path
        self.mode            = mode
        self.annotate_levels = annotate_levels
        self.remove_levels   = remove_levels
        self.engine          = engine

    def run(self):
        try:
            from calibre_plugins.furigana_ruby.furigana_engine import process_epub_file
            processed, ruby_added, file_errors = process_epub_file(
                self.epub_path, self.output_path,
                mode=self.mode,
                annotate_levels=self.annotate_levels,
                remove_levels=self.remove_levels,
                engine=self.engine,
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

    def __init__(self, tasks, engine=None, include_toggle=True):
        super().__init__()
        self.tasks          = tasks
        self.engine         = engine
        self.include_toggle = include_toggle

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
                                                      annotate_levels=al,
                                                      engine=self.engine,
                                                      metadata_levels=task.get('final_levels'),
                                                      include_toggle=self.include_toggle)
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
        try:
            try:
                from calibre_plugins.furigana_ruby.plugin_logger import logger as _lg
            except ImportError:
                from plugin_logger import logger as _lg
            try:
                from calibre_plugins.furigana_ruby import FuriganaPluginBase
                _ver = '.'.join(str(x) for x in FuriganaPluginBase.version)
            except Exception:
                _ver = '?'
            import sys as _sys
            _lg.info(f'Plugin loaded — v{_ver} on {_sys.platform}')
        except Exception:
            pass  # logging must never crash genesis()

        # ── Dropdown menu ──────────────────────────────────────────
        self.menu = QMenu(self.gui)
        self.qaction.setMenu(self.menu)
        self.qaction.triggered.connect(self.open_main_dialog)

        a1 = QAction('✦ Edit Ruby…', self.gui)
        a1.triggered.connect(self.open_ruby_dialog)
        self.menu.addAction(a1)

        a_zh = QAction('繁 Convert Chinese S↔T…', self.gui)
        a_zh.triggered.connect(self.open_chinese_dialog)
        self.menu.addAction(a_zh)

        a2 = QAction('↔ Text Direction…', self.gui)
        a2.triggered.connect(self.open_orientation_dialog)
        self.menu.addAction(a2)

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

        self._apply_tile_action()

    # ── Tile icon helpers ─────────────────────────────────────────

    def _make_tile_pixmap(self, lines, font_size=18):
        """Generate a 64×64 QPixmap: blue rounded rect + white centred text."""
        size = 64
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing if PYQT6
                        else QPainter.Antialiasing)
        p.setBrush(QBrush(QColor('#2b4ea8')))
        p.setPen(QColor(0, 0, 0, 0))
        p.drawRoundedRect(QRectF(1, 1, 62, 62), 9, 9)
        p.setPen(QColor('#ffffff'))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(font_size)
        p.setFont(font)
        align = (Qt.AlignmentFlag.AlignCenter if PYQT6 else Qt.AlignCenter)
        line_h = font_size + 4
        y = (size - len(lines) * line_h) // 2
        for line in lines:
            p.drawText(QRect(0, y, size, line_h), align, line)
            y += line_h
        p.end()
        return pm

    def _make_direction_pixmap(self):
        """Two-document icon (H-lines ↔ V-lines) with curved arrows."""
        size = 64
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        AA = QPainter.RenderHint.Antialiasing if PYQT6 else QPainter.Antialiasing
        p.setRenderHint(AA)

        # Blue background with 5px border visible on all sides
        p.setBrush(QBrush(QColor('#2b4ea8')))
        p.setPen(QColor(0, 0, 0, 0))
        p.drawRoundedRect(QRectF(1, 1, 62, 62), 9, 9)

        # White document boxes — inset so blue border shows
        # H-box: (5,5,22,22) → spans to (27,27); V-box: (37,37,22,22) → spans to (59,59)
        # 5px blue border all edges, 10px gap between boxes for arrows
        p.setBrush(QBrush(QColor('#ffffff')))
        p.drawRoundedRect(QRectF(5, 5, 22, 22), 3, 3)   # H-text (top-left)
        p.drawRoundedRect(QRectF(37, 37, 22, 22), 3, 3)  # V-text (bottom-right)

        # Dark horizontal bars in H-text box; short bar at bottom (LTR last line)
        bar = QColor('#1a1a1a')
        p.setBrush(QBrush(bar))
        p.setPen(QColor(0, 0, 0, 0))
        for y, w in [(9, 16), (13, 16), (17, 16), (21, 11)]:
            p.drawRect(QRect(8, y, w, 3))

        # Dark vertical bars in V-text box; short bar on left (RTL last column)
        for x, h in [(40, 11), (44, 16), (48, 16), (52, 16)]:
            p.drawRect(QRect(x, 40, 3, h))

        # White curved arrows — short, spanning only the gap between boxes
        NoBrush = Qt.BrushStyle.NoBrush if PYQT6 else Qt.NoBrush
        RoundCap = Qt.PenCapStyle.RoundCap if PYQT6 else Qt.RoundCap
        RoundJoin = Qt.PenJoinStyle.RoundJoin if PYQT6 else Qt.RoundJoin
        pen = QPen(QColor('#ffffff'))
        pen.setWidth(3)
        pen.setCapStyle(RoundCap)
        pen.setJoinStyle(RoundJoin)
        p.setPen(pen)
        p.setBrush(NoBrush)

        # Arrow 1: H-box right edge → V-box top (straight down at end)
        path1 = QPainterPath()
        path1.moveTo(28, 11)
        path1.cubicTo(40, 11, 48, 24, 48, 36)
        p.drawPath(path1)
        p.drawLine(48, 36, 52, 32)
        p.drawLine(48, 36, 44, 32)

        # Arrow 2: V-box left edge → H-box bottom (straight up at end)
        path2 = QPainterPath()
        path2.moveTo(36, 53)
        path2.cubicTo(24, 53, 16, 42, 16, 28)
        p.drawPath(path2)
        p.drawLine(16, 28, 12, 32)
        p.drawLine(16, 28, 20, 32)

        p.end()
        return pm

    def _apply_tile_action(self, action=None):
        """Set toolbar icon and label to match tile_action. Pass action directly to bypass pref cache."""
        if action is None:
            action = prefs['tile_action']
        self._tile_action = action
        if action == 'chinese':
            pm = self._make_tile_pixmap(['简-繁'], font_size=20)
            self.qaction.setIcon(QIcon(pm))
            self.qaction.setText('简-繁')
        elif action == 'direction':
            pm = self._make_direction_pixmap()
            self.qaction.setIcon(QIcon(pm))
            self.qaction.setText('Text Direction')
        else:
            # Load original icon.png for ruby (default)
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
                        from PyQt6.QtCore import QByteArray
                    except ImportError:
                        from PyQt5.Qt import QByteArray
                    ba = QByteArray(icon_data)
                    pm = QPixmap()
                    pm.loadFromData(ba)
                    if not pm.isNull():
                        self.qaction.setIcon(QIcon(pm))
            except Exception:
                pass
            self.qaction.setText('振り仮名 Ruby')

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

    def _get_engine_id(self, path):
        """Return the engine ID stored in the EPUB, or None for old EPUBs."""
        try:
            from calibre_plugins.furigana_ruby.furigana_engine import get_engine_id
        except ImportError:
            from furigana_engine import get_engine_id
        return get_engine_id(path)

    def _get_stored_levels(self, path):
        """Return the JLPT levels stored in the EPUB CSS tag, or None for old EPUBs."""
        try:
            from calibre_plugins.furigana_ruby.furigana_engine import get_stored_levels
        except ImportError:
            from furigana_engine import get_stored_levels
        return get_stored_levels(path)

    def _epub_has_toggle(self, path):
        """Return True if the EPUB contains the viewer-toggle script tag."""
        try:
            import zipfile
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if name.lower().endswith(('.html', '.xhtml', '.htm')):
                        if b'furigana-ruby-js' in z.read(name):
                            return True
        except Exception:
            pass
        return False

    # ── Entry point ───────────────────────────────────────────────

    def open_main_dialog(self):
        ids = self._selected_ids()
        if not ids:
            warning_dialog(self.gui, 'No Book Selected',
                'Select one or more books first.', show=True)
            return
        action = getattr(self, '_tile_action', prefs['tile_action'])
        if action == 'chinese':
            self._show_chinese_dialog(ids)
        elif action == 'direction':
            self._show_orientation_dialog(ids)
        else:
            self._show_ruby_dialog(ids)

    def open_ruby_dialog(self):
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
                current_levels   = self._get_annotated_levels(epub_path)
                stored_engine_id = self._get_engine_id(epub_path) if auto_count else None
                stored_levels    = self._get_stored_levels(epub_path)
                has_toggle       = self._epub_has_toggle(epub_path) if auto_count else False
            else:
                auto_count = pub_count = 0
                current_levels   = set()
                stored_engine_id = None
                stored_levels    = None
                has_toggle       = False

            book_rows.append({
                'book_id':          book_id,
                'title':            title,
                'epub':             epub_path,
                'lang_info':        lang_info,
                'lang_label':       lang_label,
                'ruby_allowed':     ruby_allowed,
                'auto_count':       auto_count,
                'pub_count':        pub_count,
                'current_levels':   current_levels,
                'stored_engine_id': stored_engine_id,
                'stored_levels':    stored_levels,
                'has_toggle':       has_toggle,
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
        dlg.setMinimumHeight(400)
        dlg.resize(720, 620)

        vl = QVBoxLayout()
        vl.setSpacing(6)
        dlg.setLayout(vl)

        # All content except the button row goes into a single scroll area —
        # same pattern as the Settings modal. This way expanding the JLPT panel
        # scrolls the whole dialog instead of squeezing sibling widgets.
        main_widget = QWidget()
        main_vl = QVBoxLayout(main_widget)
        main_vl.setContentsMargins(0, 0, 0, 0)
        main_vl.setSpacing(6)
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setWidget(main_widget)
        try:
            main_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            main_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        except AttributeError:
            main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            main_scroll.setFrameShape(QFrame.NoFrame)
        vl.addWidget(main_scroll)

        # Description — line 1 fixed, line 2 depends on keep_original
        desc1 = QLabel(
            'Add/Update the Furigana (Ruby) to ebooks based on the selected JLPT levels.<br>'
            'Publisher furigana is always preserved.')
        desc1.setWordWrap(True)
        main_vl.addWidget(desc1)

        if prefs['keep_original']:
            desc2_text = ('* A copy of the original file will be saved based on '
                          'your plugin Settings.')
        else:
            desc2_text = ('* Modified file will replace the original file based on '
                          'your plugin Settings.')
        desc2 = QLabel(desc2_text)
        desc2.setWordWrap(True)
        main_vl.addWidget(desc2)

        sep = QFrame()
        try:
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFrameShadow(QFrame.Shadow.Sunken)
        except AttributeError:
            sep.setFrameShape(QFrame.HLine)
            sep.setFrameShadow(QFrame.Sunken)
        main_vl.addWidget(sep)

        # ── Options panel (JLPT + Toggle + Engine) ───────────────
        # _incl_toggle: mutable cell so closures (_fmt_sub_text, _refresh_checks)
        # can read the current state after the checkbox is toggled.
        _incl_toggle = [bool(prefs.get('include_viewer_toggle', False))]

        # level_checked is the persistent source of truth for checkbox state.
        # level_cbs is rebuilt fresh each time the expanded view is shown,
        # and cleared when collapsed. This avoids ALL Qt visibility issues:
        # no hide/show/setMaximumHeight — we simply replace the panel content.
        saved_levels       = set(prefs['annotate_levels'])
        level_checked      = {l: (l in saved_levels)
                              for l in ['N1', 'N2', 'N3', 'N4', 'N5', 'unlisted']}
        level_cbs          = {}   # populated only while expanded
        _pre_expand_levels = [None]
        _cust_btn_ref      = [None]   # reference to collapsed Customize button

        _LEVEL_ORDER = ['N1', 'N2', 'N3', 'N4', 'N5', 'unlisted']

        def _current_sel_text():
            checked = [l for l in _LEVEL_ORDER if level_checked.get(l, False)]
            return 'Current Selection: ' + (', '.join(checked) if checked else 'None')

        def _fmt_levels_short():
            """Format selected levels as 'N1–N3', 'N1, N3', 'All', or 'None'."""
            checked = [l for l in _LEVEL_ORDER if level_checked.get(l, False)]
            if not checked:
                return 'None'
            if checked == _LEVEL_ORDER:
                return 'All'
            # Check if consecutive from N1
            _lvl_map = {'N1': 0, 'N2': 1, 'N3': 2, 'N4': 3, 'N5': 4, 'unlisted': 5}
            idxs = [_lvl_map[l] for l in checked]
            if idxs == list(range(len(idxs))):  # consecutive from N1
                return f'{checked[0]}–{checked[-1]}'
            return ', '.join(checked)

        def _fmt_opts_summary():
            lvl_part = _fmt_levels_short()
            tog_part = 'Toggle in Viewer on' if _incl_toggle[0] else 'Toggle in Viewer off'
            eng_pref = prefs['manual_engine']
            eng_part = 'High-accuracy' if eng_pref == 'high_accuracy' else 'Enhanced'
            return f'{lvl_part}  ·  {tog_part}  ·  {eng_part}'

        def _sync_from_cbs():
            for l, cb in level_cbs.items():
                level_checked[l] = cb.isChecked()

        _link_style = ('color: #0066cc; text-decoration: underline; '
                       'border: none; padding: 0;')

        # ── Options header: [▶] Options  ·····  [Customize / Save] ──
        _opts_expanded = [False]

        opts_hdr_widget = QWidget()
        opts_hdr_hl = QHBoxLayout(opts_hdr_widget)
        opts_hdr_hl.setContentsMargins(0, 0, 0, 0)
        opts_hdr_hl.setSpacing(6)

        opts_arrow_btn = QPushButton('▶')
        opts_arrow_btn.setFlat(True)
        opts_arrow_btn.setFixedSize(18, 18)
        opts_arrow_btn.setStyleSheet('border: none; padding: 0; font-size: 10px; color: #444;')
        try:
            opts_arrow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        except AttributeError:
            opts_arrow_btn.setCursor(Qt.PointingHandCursor)

        opts_title_lbl = QLabel('<b>Options</b>')

        # Customize/Save link — changes label depending on state
        opts_action_btn = QPushButton('Customize')
        opts_action_btn.setFlat(True)
        opts_action_btn.setStyleSheet(_link_style)
        try:
            opts_action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        except AttributeError:
            opts_action_btn.setCursor(Qt.PointingHandCursor)

        opts_hdr_hl.addWidget(opts_arrow_btn)
        opts_hdr_hl.addWidget(opts_title_lbl)
        opts_hdr_hl.addWidget(opts_action_btn)
        opts_hdr_hl.addStretch()
        main_vl.addWidget(opts_hdr_widget)

        # Summary line — shown when collapsed, indented to align with "Options" text
        opts_summary_lbl = QLabel(_fmt_opts_summary())
        opts_summary_lbl.setStyleSheet('color: #555; font-size: 12px; padding-left: 24px;')
        main_vl.addWidget(opts_summary_lbl)

        def _update_opts_summary():
            opts_summary_lbl.setText(_fmt_opts_summary())

        # ── Options content (indented 24px to align with "Options" text) ──
        opts_content = QWidget()
        opts_content_vl = QVBoxLayout(opts_content)
        opts_content_vl.setContentsMargins(24, 4, 0, 0)
        opts_content_vl.setSpacing(6)
        opts_content.setVisible(False)
        main_vl.addWidget(opts_content)

        def _save_opts():
            """Commit Options settings to prefs and collapse the panel."""
            _sync_from_cbs()
            prefs['annotate_levels']       = sorted(
                l for l, v in level_checked.items() if v)
            prefs['include_viewer_toggle'] = _incl_toggle[0]
            # engine already saved immediately on radio change
            _update_opts_summary()
            _toggle_opts_panel()
            _refresh_checks_ruby(preserve_status=False)

        def _toggle_opts_panel():
            expanded = not _opts_expanded[0]
            _opts_expanded[0] = expanded
            if expanded:
                _build_expanded()   # populate JLPT checkboxes fresh
            else:
                _build_collapsed()  # clear JLPT checkboxes
            opts_content.setVisible(expanded)
            opts_summary_lbl.setVisible(not expanded)
            opts_arrow_btn.setText('▼' if expanded else '▶')
            opts_action_btn.setText('Save' if expanded else 'Customize')

        opts_arrow_btn.clicked.connect(_toggle_opts_panel)
        opts_title_lbl.mousePressEvent = lambda _: _toggle_opts_panel()
        opts_action_btn.clicked.connect(
            lambda: (_save_opts() if _opts_expanded[0] else _toggle_opts_panel()))

        # ── JLPT panel (inside opts_content) ─────────────────────
        # Single container always in opts_content_vl. We rebuild its content on
        # each toggle instead of hiding widgets — the only approach that works
        # reliably in Calibre's PyQt6 on macOS.
        jlpt_panel = QWidget()
        jlpt_vl    = QVBoxLayout()
        jlpt_vl.setContentsMargins(0, 0, 0, 0)
        jlpt_vl.setSpacing(0)
        jlpt_panel.setLayout(jlpt_vl)
        opts_content_vl.addWidget(jlpt_panel)

        def _clear_jlpt():
            """Remove and hide all content in jlpt_vl, then schedule deletion.

            hide() is critical: takeAt() removes from the layout but the widget
            remains a child of jlpt_panel and will still render unless explicitly
            hidden. deleteLater() is deferred; without hide() the old widget
            overlaps the new content until the next event loop tick.
            """
            while jlpt_vl.count():
                item = jlpt_vl.takeAt(0)
                w = item.widget()
                if w:
                    w.hide()        # suppress rendering immediately
                    w.deleteLater() # destroy on next event-loop tick

        def _build_collapsed():
            """Rebuild JLPT panel in collapsed state (summary only, no controls)."""
            level_cbs.clear()
            _clear_jlpt()
            _cust_btn_ref[0] = None
            # Nothing to show here — opts_content is hidden when collapsed,
            # so the summary line on the Options header is the only visible state.

        def _build_expanded():
            """Rebuild JLPT panel in expanded state: quick-select at top, then checkboxes."""
            _pre_expand_levels[0] = {l for l, v in level_checked.items() if v}
            _cust_btn_ref[0] = None
            _clear_jlpt()

            wrap = QWidget()
            wvl  = QVBoxLayout(wrap)
            wvl.setContentsMargins(0, 0, 0, 0)
            wvl.setSpacing(3)

            # Section label
            lbl = QLabel('<b>JLPT Levels</b>')
            wvl.addWidget(lbl)

            # Quick-select at the TOP (above checkboxes)
            quick_hl = QHBoxLayout()
            quick_hl.setSpacing(4)
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
                qbtn.setFixedHeight(24)
                qbtn.clicked.connect(
                    lambda _, lvls=qlevels:
                        [cb.setChecked(lvl in lvls) for lvl, cb in level_cbs.items()])
                quick_hl.addWidget(qbtn)
            quick_hl.addStretch()
            wvl.addLayout(quick_hl)

            # Level checkboxes
            level_cbs.clear()
            for level, label, bold in [
                ('N1',       'N1  —  Rare literary kanji',              True),
                ('N2',       'N2  —  Advanced kanji',                   True),
                ('N3',       'N3  —  Intermediate kanji  ★',            True),
                ('N4',       'N4  —  Basic kanji  (学、週、料理…)',      False),
                ('N5',       'N5  —  Elementary kanji  (日、人、山…)',   False),
                ('unlisted', 'Unlisted  —  Kanji not in any JLPT list',  False),
            ]:
                cb = QCheckBox(label)
                cb.setChecked(level_checked.get(level, False))
                if bold:
                    f = cb.font(); f.setBold(True); cb.setFont(f)
                level_cbs[level] = cb
                wvl.addWidget(cb)

            jlpt_vl.addWidget(wrap)

        _build_collapsed()

        # ── Viewer toggle (inside opts_content, between JLPT and engine) ──
        def _make_sep_in(parent_vl):
            ln = QFrame()
            try:
                ln.setFrameShape(QFrame.Shape.HLine)
                ln.setFrameShadow(QFrame.Shadow.Sunken)
            except AttributeError:
                ln.setFrameShape(QFrame.HLine)
                ln.setFrameShadow(QFrame.Sunken)
            parent_vl.addWidget(ln)

        _make_sep_in(opts_content_vl)

        toggle_sec_lbl = QLabel('<b>Viewer toggle</b>')
        opts_content_vl.addWidget(toggle_sec_lbl)

        toggle_note_lbl = QLabel(
            'Cycles through: All selected levels · Publisher only · None')
        toggle_note_lbl.setWordWrap(True)
        toggle_note_lbl.setStyleSheet('color: #555; font-size: 12px;')
        opts_content_vl.addWidget(toggle_note_lbl)

        incl_toggle_cb = QCheckBox('Include toggle button in Calibre Viewer')
        incl_toggle_cb.setChecked(_incl_toggle[0])
        opts_content_vl.addWidget(incl_toggle_cb)

        def _on_toggle_changed(state):
            _incl_toggle[0] = bool(state)
            _update_opts_summary()
            _refresh_checks_ruby(preserve_status=False)

        incl_toggle_cb.stateChanged.connect(_on_toggle_changed)

        # ── Furigana engine (inside opts_content) ─────────────────
        _make_sep_in(opts_content_vl)

        eng_lbl = QLabel('<b>Furigana engine</b>')
        opts_content_vl.addWidget(eng_lbl)

        eng_container = QWidget()
        eng_vl = QVBoxLayout(eng_container)
        eng_vl.setContentsMargins(0, 0, 0, 0)
        eng_vl.setSpacing(4)

        rb_enhanced = QRadioButton('Enhanced (built-in)')
        rb_high     = QRadioButton('High-accuracy (SudachiPy)')
        current_engine_pref = prefs['manual_engine']
        rb_enhanced.setChecked(current_engine_pref != 'high_accuracy')
        rb_high.setChecked(current_engine_pref == 'high_accuracy')

        eng_vl.addWidget(rb_enhanced)

        # High-accuracy row: radio + dynamic status/button
        high_row = QHBoxLayout()
        high_row.setContentsMargins(0, 0, 0, 0)
        high_row.setSpacing(8)
        high_row.addWidget(rb_high)

        try:
            from calibre_plugins.furigana_ruby.engines.sudachi import (
                get_status, SudachiStatus, get_version)
        except ImportError:
            from engines.sudachi import get_status, SudachiStatus, get_version

        _sudachi_status = [None]   # mutable cell updated after download
        _sudachi_ver    = [None]

        def _refresh_sudachi_status():
            status, ver = get_status()
            _sudachi_status[0] = status
            _sudachi_ver[0]    = ver
            return status, ver

        status, ver = _refresh_sudachi_status()

        eng_status_lbl = QLabel()
        eng_status_lbl.setStyleSheet('color: #666; font-size: 11px;')
        eng_dl_btn = QPushButton()
        eng_dl_btn.setMaximumWidth(160)

        _download_thread = [None]

        def _update_engine_ui():
            s = _sudachi_status[0]
            v = _sudachi_ver[0]
            if s == SudachiStatus.READY:
                eng_status_lbl.setText(f'SudachiPy {v} · ready' if v else 'ready')
                eng_dl_btn.setText('Re-download')
                eng_dl_btn.setVisible(True)
                eng_warn_lbl.setVisible(rb_high.isChecked())
            elif s == SudachiStatus.CALIBRE_UPDATED:
                eng_status_lbl.setText('Unavailable — Calibre updated')
                eng_dl_btn.setText('Re-download to restore')
                eng_dl_btn.setVisible(True)
                eng_warn_lbl.setVisible(False)
            elif s == SudachiStatus.BROKEN:
                eng_status_lbl.setText('Unavailable')
                eng_dl_btn.setText('Re-download')
                eng_dl_btn.setVisible(True)
                eng_warn_lbl.setVisible(False)
            else:  # NOT_DOWNLOADED
                eng_status_lbl.setText('Not downloaded (~40 MB)')
                eng_dl_btn.setText('Download')
                eng_dl_btn.setVisible(True)
                eng_warn_lbl.setVisible(False)

        high_row.addWidget(eng_status_lbl)
        high_row.addWidget(eng_dl_btn)
        high_row.addStretch()
        eng_vl.addLayout(high_row)

        eng_warn_lbl = QLabel('⚠ First annotation adds ~2–3 s to load the engine')
        eng_warn_lbl.setStyleSheet('color: #b85c00; font-size: 11px; padding-left: 20px;')
        eng_vl.addWidget(eng_warn_lbl)

        opts_content_vl.addWidget(eng_container)
        _update_engine_ui()

        # Save engine pref when radio changes
        def _on_engine_changed():
            prefs['manual_engine'] = (
                'high_accuracy' if rb_high.isChecked() else 'enhanced')
            _update_opts_summary()
            _update_engine_ui()
            # Re-evaluate up-to-date status — engine change may re-enable books
            _refresh_checks_ruby(preserve_status=False)

        rb_enhanced.toggled.connect(_on_engine_changed)
        rb_high.toggled.connect(_on_engine_changed)

        # Download thread
        class _DownloadThread(QThread):
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

        def _on_download():
            eng_dl_btn.setEnabled(False)
            eng_status_lbl.setText('Downloading… (may take a minute)')
            t = _DownloadThread()
            _download_thread[0] = t

            def _on_done(ok, err):
                _refresh_sudachi_status()
                eng_dl_btn.setEnabled(True)
                if ok:
                    _update_engine_ui()
                else:
                    eng_status_lbl.setText(f'Download failed: {err[:60]}')
                    eng_dl_btn.setVisible(True)
            t.done.connect(_on_done)
            t.start()

        eng_dl_btn.clicked.connect(_on_download)

        # Separator between Options panel and book list
        bk_sep = QFrame()
        try:
            bk_sep.setFrameShape(QFrame.Shape.HLine)
            bk_sep.setFrameShadow(QFrame.Shadow.Sunken)
        except AttributeError:
            bk_sep.setFrameShape(QFrame.HLine)
            bk_sep.setFrameShadow(QFrame.Sunken)
        main_vl.addWidget(bk_sep)

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
        _top_align  = Qt.AlignmentFlag.AlignTop if PYQT6 else Qt.AlignTop

        _ENG_SHORT = {
            'standard':      'Standard',
            'enhanced':      'Enhanced',
            'high_accuracy': 'High-accuracy',
        }
        _LVL_ORDER = ['N1', 'N2', 'N3', 'N4', 'N5', 'unlisted']

        def _fmt_sub_text(row):
            if not row['ruby_allowed']:
                return f'{row["lang_label"]} · EPUB'
            line1 = f'{row["lang_label"]} · Publisher: {row["pub_count"]:,}'
            if not row['auto_count']:
                return line1
            parts2 = [f'Auto: {row["auto_count"]:,}']
            stored = row.get('stored_levels')
            # Pre-v1.6.1 books carry no data-levels stamp — fall back to levels
            # detected from content so old and new books read consistently.
            display_levels = stored if stored is not None else row.get('current_levels')
            if display_levels:
                lvl_str = ', '.join(l for l in _LVL_ORDER if l in display_levels)
                if lvl_str:
                    parts2.append(lvl_str)
            eid = row.get('stored_engine_id')
            if eid:
                parts2.append(f'Engine: {_ENG_SHORT.get(eid, eid)}')
            # Toggle info: show only when JS is actually in the file, or when
            # the user wants it but it is missing (so they can see the gap).
            has_js = row.get('has_toggle', False)
            if has_js:
                parts2.append('Toggle: ✓')
            elif _incl_toggle[0]:
                parts2.append('Toggle: missing')
            return line1 + '\n' + ' · '.join(parts2)

        checkboxes    = []
        status_labels = {}
        sub_labels    = {}
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

            title_lbl = WrappingClickableLabel(row['title'])
            title_lbl.setToolTip(row['title'])
            title_lbl.setSizePolicy(sp_pol.Expanding, sp_pol.Preferred)
            if not row['ruby_allowed']:
                title_lbl.setStyleSheet(_DIM_STYLE)
            title_lbl.clicked.connect(
                lambda _=None, c=cb:
                    c.toggle() if c.isVisible() and c.isEnabled() else None)

            status_lbl = QLabel('' if row['ruby_allowed'] else 'Not applicable')
            try:
                status_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            except AttributeError:
                status_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            status_lbl.setMinimumWidth(170)
            if not row['ruby_allowed']:
                status_lbl.setStyleSheet('color: #959595;')

            sub_text = _fmt_sub_text(row)
            sub_lbl = QLabel(sub_text)
            sub_lbl.setSizePolicy(sp_pol.Expanding, sp_pol.Preferred)
            sub_lbl.setStyleSheet(_SUB_STYLE if row['ruby_allowed'] else _DIM_STYLE)

            top_row = QHBoxLayout()
            top_row.setSpacing(4)
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.addWidget(cb_box, 0, _top_align)
            top_row.addWidget(title_lbl, 3)
            top_row.addWidget(status_lbl, 1, _top_align)

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

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        main_vl.addWidget(table_container)

        # Summary result panel — auto-height, grows with content.
        # Uses QTextEdit in read-only mode; document height is connected to
        # the widget so it expands to fit rather than showing a scrollbar.
        result_te = QTextEdit()
        result_te.setReadOnly(True)
        result_te.setMinimumHeight(40)
        result_te.setMaximumHeight(200)
        result_te.setSizePolicy(sp_pol.Preferred, sp_pol.Minimum)
        result_te.document().contentsChanged.connect(
            lambda: result_te.setFixedHeight(
                min(200, max(40, int(result_te.document().size().height()) + 12))
            )
        )
        result_te.setPlainText(_selection_summary())
        main_vl.addWidget(result_te)

        # ── Buttons ───────────────────────────────────────────────
        btn_row_hl = QHBoxLayout()

        btn_viewer = QPushButton('📖 Open in Viewer')
        btn_viewer.setMinimumWidth(150)
        btn_viewer.setVisible(len(book_ids) == 1)

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
        # Track which applicable books are hidden as "up to date" explicitly,
        # instead of relying on cb.isVisible() which returns False for all child
        # widgets before dlg.exec() is called (Qt isVisible quirk — same reason
        # the S↔T dialog uses an explicit applicable_ids set, not isVisible).
        _up_to_date_bids = set()

        def _eligible_cbs():
            # Applicable books that are NOT hidden as "up to date"
            return [cb_map[bid] for bid in applicable_ids
                    if bid in cb_map and bid not in _up_to_date_bids]

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
            if _cust_btn_ref[0]:
                _cust_btn_ref[0].setEnabled(False)

        def _unlock_controls():
            header_cb.setEnabled(True)
            # Re-enable ALL book checkboxes that were disabled by _lock_controls —
            # mirror the same set it disables, not a filtered subset.
            # Visibility (setVisible) already controls which books are actionable;
            # leaving a checkbox disabled-but-visible causes it to appear interactive
            # while silently ignoring clicks (only the header setChecked() bypasses it).
            for cb in checkboxes:
                cb.setEnabled(True)
            for lvl_cb in level_cbs.values():
                lvl_cb.setEnabled(True)
            if _cust_btn_ref[0]:
                _cust_btn_ref[0].setEnabled(True)
            _update_apply_state()

        # ── Single source of truth for pending work ───────────────
        def _pending_work(row, sel):
            """What `row` still needs to reach selection `sel`.

            Returns (to_add, to_remove, engine_changed, toggle_needed). Used by
            both _refresh_checks_ruby (checkbox visibility) and _on_apply (task
            building) so they can never disagree about whether a book has work
            pending — previously each computed this independently and could
            reach different answers for books annotated before the data-levels
            stamp existed (v1.6.1), where the checkbox stayed enabled but Apply
            found nothing to do.
            """
            stored  = row.get('stored_levels')
            current = row['current_levels']
            if stored is not None and stored == sel:
                # Stamp says this book is already at the target selection — it
                # may simply have no kanji in some levels, which a content diff
                # alone can't distinguish from "not yet processed".
                to_add    = set()
                to_remove = set()
            else:
                to_add    = sel - current
                to_remove = current - sel
            engine_changed = (
                not to_add and not to_remove
                and bool(current)
                and (row.get('stored_engine_id') is None
                     or row['stored_engine_id'] != prefs['manual_engine'])
            )
            toggle_needed = (
                _incl_toggle[0]
                and not row.get('has_toggle', False)
                and not to_add and not to_remove and not engine_changed
                and bool(current)
            )
            return to_add, to_remove, engine_changed, toggle_needed

        # ── Per-book up-to-date check ─────────────────────────────
        def _refresh_checks_ruby(preserve_status=False):
            """Show/hide checkboxes and update status based on levels + toggle state.

            preserve_status=True  — keep '✅ Done' labels (called post-processing)
            preserve_status=False — update status to 'Up to date'/'Toggle missing'
                                    or clear it (called on level/toggle changes)
            """
            current_sel  = {l for l, v in level_checked.items() if v}
            for row in book_rows:
                if not row['ruby_allowed']:
                    continue
                bid    = row['book_id']
                cb     = cb_map.get(bid)
                sl     = status_labels.get(bid)
                sub_lb = sub_labels.get(bid)
                if cb is None or sl is None:
                    continue

                to_add, to_remove, engine_changed, toggle_needed = (
                    _pending_work(row, current_sel))

                if not (to_add or to_remove or engine_changed or toggle_needed):
                    _up_to_date_bids.add(bid)
                    cb.setVisible(False)
                    cb.setChecked(False)
                    if not preserve_status:
                        sl.setText('Up to date')
                        sl.setStyleSheet('color: #545454;')
                else:
                    was_hidden = bid in _up_to_date_bids
                    _up_to_date_bids.discard(bid)
                    cb.setVisible(True)
                    if was_hidden:
                        cb.setChecked(True)
                    if not preserve_status and not sl.text().startswith('⚠'):
                        # toggle_needed only occurs when nothing else is pending
                        # (see its definition), so it alone means "Toggle missing".
                        if toggle_needed:
                            sl.setText('Toggle missing')
                            sl.setStyleSheet('color: #c05000; font-weight: bold;')
                        else:
                            sl.setText('')
                            sl.setStyleSheet('')

                # Update sub-info label to reflect current toggle preference
                if sub_lb is not None:
                    sub_lb.setText(_fmt_sub_text(row))

            _update_apply_state()

        # ── Apply handler ─────────────────────────────────────────
        def _on_apply():
            # Sync live checkboxes → level_checked (no-op if panel is collapsed)
            _sync_from_cbs()
            checked_levels = {l for l, v in level_checked.items() if v}

            tasks = []
            for row in book_rows:
                cb = cb_map[row['book_id']]
                if not (cb.isVisible() and cb.isChecked()):
                    continue
                to_add, to_remove, engine_changed, toggle_needed = (
                    _pending_work(row, checked_levels))
                if to_add or to_remove or engine_changed or toggle_needed:
                    # force_rerun: re-annotate at current levels so inject_css_js fires
                    force_rerun = engine_changed or toggle_needed
                    tasks.append({
                        'book_id':        row['book_id'],
                        'epub':           row['epub'],
                        'to_add':         row['current_levels'] if force_rerun else to_add,
                        'to_remove':      row['current_levels'] if force_rerun else to_remove,
                        'current_levels': row['current_levels'],
                        'final_levels':   checked_levels.copy(),
                    })

            if not tasks:
                result_te.setPlainText(
                    '⚠ Nothing to do — selected books already match '
                    'the chosen levels and settings.\n\n' + _selection_summary())
                return

            prefs['annotate_levels'] = sorted(checked_levels)

            # Resolve engine — if preferred engine unavailable, fall back
            preferred = prefs['manual_engine']
            try:
                from calibre_plugins.furigana_ruby.engine_registry import (
                    resolve_engine, _ensure_all_registered)
                _ensure_all_registered()
            except ImportError:
                from engine_registry import resolve_engine, _ensure_all_registered
                _ensure_all_registered()

            # Handle download-in-progress case
            if (_download_thread[0] is not None
                    and _download_thread[0].isRunning()
                    and preferred == 'high_accuracy'):
                _show_download_in_progress_dialog(checked_levels, tasks)
                return

            resolved_engine, actual_engine_id = resolve_engine(preferred)
            _run_bulk(tasks, checked_levels, resolved_engine, actual_engine_id,
                      preferred)

        def _show_download_in_progress_dialog(checked_levels, tasks):
            from calibre.gui2 import question_dialog
            dlg2 = QDialog(dlg)
            dlg2.setWindowTitle('Engine downloading')
            dlg2.setMinimumWidth(380)
            v2 = QVBoxLayout(dlg2)
            v2.addWidget(QLabel(
                'The high-accuracy engine is still downloading.'))
            v2.addSpacing(4)
            rb_wait = QRadioButton('Wait for download, then annotate')
            rb_now  = QRadioButton('Use Enhanced engine for this run')
            rb_now.setChecked(True)
            v2.addWidget(rb_wait)
            v2.addWidget(rb_now)
            v2.addSpacing(8)
            bb2 = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Cancel |
                QDialogButtonBox.StandardButton.Ok
                if PYQT6 else
                QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            bb2.accepted.connect(dlg2.accept)
            bb2.rejected.connect(dlg2.reject)
            v2.addWidget(bb2)
            if (dlg2.exec() if PYQT6 else dlg2.exec_()) != QDialog.DialogCode.Accepted if PYQT6 else QDialog.Accepted:
                return
            if rb_wait.isChecked():
                # Wait for download, then annotate
                def _on_dl_done(ok, err):
                    _refresh_sudachi_status()
                    _update_engine_ui()
                    if ok:
                        from calibre_plugins.furigana_ruby.engine_registry import (
                            resolve_engine, _ensure_all_registered)
                        _ensure_all_registered()
                        eng, eid = resolve_engine('high_accuracy')
                        _run_bulk(tasks, checked_levels, eng, eid, 'high_accuracy')
                    else:
                        _show_download_failed_dialog(checked_levels, tasks, err)
                _download_thread[0].done.connect(_on_dl_done)
            else:
                from calibre_plugins.furigana_ruby.engine_registry import (
                    resolve_engine, _ensure_all_registered)
                _ensure_all_registered()
                eng, eid = resolve_engine('enhanced')
                _run_bulk(tasks, checked_levels, eng, eid, 'enhanced',
                          fallback_note='(High-accuracy was downloading)')

        def _show_download_failed_dialog(checked_levels, tasks, err=''):
            dlg3 = QDialog(dlg)
            dlg3.setWindowTitle('Download failed')
            dlg3.setMinimumWidth(380)
            v3 = QVBoxLayout(dlg3)
            v3.addWidget(QLabel(
                'Could not download the high-accuracy engine.\n'
                'Check your internet connection and try again.'))
            v3.addSpacing(4)
            rb_retry   = QRadioButton('Retry download')
            rb_enhanced = QRadioButton('Use Enhanced engine for this run')
            rb_retry.setChecked(True)
            v3.addWidget(rb_retry)
            v3.addWidget(rb_enhanced)
            v3.addSpacing(8)
            bb3 = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Cancel |
                QDialogButtonBox.StandardButton.Ok
                if PYQT6 else
                QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            bb3.accepted.connect(dlg3.accept)
            bb3.rejected.connect(dlg3.reject)
            v3.addWidget(bb3)
            if (dlg3.exec() if PYQT6 else dlg3.exec_()) != QDialog.DialogCode.Accepted if PYQT6 else QDialog.Accepted:
                return
            if rb_retry.isChecked():
                _on_download()
                _show_download_in_progress_dialog(checked_levels, tasks)
            else:
                from calibre_plugins.furigana_ruby.engine_registry import (
                    resolve_engine, _ensure_all_registered)
                _ensure_all_registered()
                eng, eid = resolve_engine('enhanced')
                _run_bulk(tasks, checked_levels, eng, eid, 'enhanced',
                          fallback_note='(High-accuracy download failed)')

        _ENGINE_DISPLAY = {
            'high_accuracy': 'High-accuracy (SudachiPy)',
            'enhanced':      'Enhanced (built-in)',
            'standard':      'Standard (pykakasi)',
        }

        def _run_bulk(tasks, checked_levels, resolved_engine, actual_engine_id,
                      preferred_id, fallback_note=''):
            try:
                from calibre_plugins.furigana_ruby.plugin_logger import logger as _lg
            except ImportError:
                from plugin_logger import logger as _lg
            _lg.info(f'Ruby: starting {len(tasks)} book(s) — '
                     f'levels={sorted(checked_levels)} engine={actual_engine_id} '
                     f'toggle={_incl_toggle[0]}')
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

            worker = BulkFuriganaWorker(tasks, engine=resolved_engine,
                                        include_toggle=_incl_toggle[0])

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
                        if not db.has_format(book_id, 'ORIGINAL_EPUB'):
                            orig = task_map[book_id]['epub']
                            with open(orig, 'rb') as _f:
                                self.gui.current_db.add_format(
                                    book_id, 'ORIGINAL_EPUB', _f,
                                    index_is_id=True, notify=False, replace=False)
                    db.add_format(book_id, 'EPUB', tmp_path, replace=True)
                    saved += 1
                    # Update in-memory state so re-apply and up-to-date checks work correctly
                    if row:
                        new_auto = (row['auto_count'] + ruby_delta
                                    if ruby_delta >= 0 else max(0, row['auto_count'] + ruby_delta))
                        row['auto_count']       = new_auto
                        row['current_levels']   = checked_levels.copy()
                        row['stored_levels']    = checked_levels.copy()
                        row['stored_engine_id'] = actual_engine_id
                        # Toggle JS was either added or stripped depending on _incl_toggle
                        row['has_toggle']       = _incl_toggle[0]
                        sub_lbl = sub_labels.get(book_id)
                        if sub_lbl:
                            sub_lbl.setText(_fmt_sub_text(row))
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

            eng_label = _ENGINE_DISPLAY.get(actual_engine_id, actual_engine_id)
            if actual_engine_id != preferred_id:
                eng_label += f' (fell back from {_ENGINE_DISPLAY.get(preferred_id, preferred_id)})'
            if fallback_note:
                eng_label += f' {fallback_note}'

            lines = [f'✅ Saved {saved} book(s)']
            lines.append(f'Engine: {eng_label}')
            if save_errors:
                lines.append(f'⚠ {len(save_errors)} error(s):')
                lines += [f'  {e}' for e in save_errors[:5]]
            lines += ['', _selection_summary()]
            result_te.setPlainText('\n'.join(lines))
            if save_errors:
                for e in save_errors:
                    _lg.error(f'Ruby save error: {e}')
            _lg.info(f'Ruby: done — saved={saved} errors={len(save_errors)} '
                     f'engine={eng_label}')
            # Hide done-book checkboxes; re-enable any remaining processable books
            _refresh_checks_ruby(preserve_status=True)
            _unlock_controls()

        # ── Viewer button ─────────────────────────────────────────
        def _on_viewer():
            dlg.reject()
            # If the single selected book is non-Japanese (no eligible_rows),
            # still open it in the viewer — the button is shown for any 1-book selection.
            vid = eligible_rows[0]['book_id'] if eligible_rows else book_ids[0]
            self._open_in_viewer(vid)

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

        # Initial check: hide checkboxes for books already up to date with current levels
        _refresh_checks_ruby(preserve_status=False)

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
                if not db.has_format(book_id, 'ORIGINAL_EPUB'):
                    with open(epub_path, 'rb') as _f:
                        self.gui.current_db.add_format(
                            book_id, 'ORIGINAL_EPUB', _f,
                            index_is_id=True, notify=False, replace=False)
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
        self._show_orientation_dialog(ids)

    def _show_orientation_dialog(self, book_ids):
        try:
            from calibre_plugins.furigana_ruby.orientation_engine import detect_orientation
        except ImportError:
            from orientation_engine import detect_orientation
        try:
            from calibre_plugins.furigana_ruby.lang_detect import (
                detect_book_language, lang_display)
        except ImportError:
            from lang_detect import detect_book_language, lang_display

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
            try:
                lang_info  = detect_book_language(epub_path)
                lang_label = lang_display(lang_info) if lang_info['lang_raw'] else ''
            except Exception:
                lang_label = ''
            book_rows.append({'book_id': book_id, 'title': title,
                              'epub': epub_path, 'orientation': orientation,
                              'lang_label': lang_label})

        def _orient_label(o):
            return {'vertical': 'Vertical', 'horizontal': 'Horizontal'}.get(o, 'Unknown')

        def _selection_summary():
            parts = [f'{len(book_rows)} EPUB book(s)']
            if excluded_count:
                parts.append(f'{excluded_count} skipped (no EPUB)')
            return f'Selection: {len(book_ids)} book(s) — {" · ".join(parts)}'

        # Smart default direction for single-book selection
        _single_orientation = book_rows[0]['orientation'] if len(book_rows) == 1 else None

        # ── Build dialog ──────────────────────────────────────────
        dlg = QDialog(self.gui)
        dlg.setWindowTitle('Convert Layout')
        dlg.setMinimumWidth(680)
        dlg.resize(700, 520)

        vl = QVBoxLayout()
        vl.setSpacing(8)
        dlg.setLayout(vl)

        # Direction — pre-select based on single book's orientation if applicable
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel('<b>Direction:</b>'))
        rb_h2v = QRadioButton('Horizontal → Vertical')
        rb_v2h = QRadioButton('Vertical → Horizontal')
        if _single_orientation == 'vertical':
            rb_v2h.setChecked(True)
        else:
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
        _top_align = Qt.AlignmentFlag.AlignTop if PYQT6 else Qt.AlignTop

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

            title_lbl = WrappingClickableLabel(row['title'])
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

            _base = ' · '.join(filter(None, [row['lang_label'], 'EPUB', _orient_label(row['orientation'])]))
            sub_lbl = QLabel(_base)
            sub_lbl.setStyleSheet(_SUB_STYLE)

            top_row = QHBoxLayout()
            top_row.setSpacing(4)
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.addWidget(cb_box, 0, _top_align)
            top_row.addWidget(title_lbl, 3)
            top_row.addWidget(status_lbl, 1, _top_align)

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
        result_te.setMinimumHeight(40)
        result_te.setMaximumHeight(200)
        result_te.setSizePolicy(sp2.Preferred, sp2.Minimum)
        result_te.document().contentsChanged.connect(
            lambda: result_te.setFixedHeight(
                min(200, max(40, int(result_te.document().size().height()) + 12))
            )
        )
        result_te.setPlainText(_selection_summary())
        vl.addWidget(result_te)

        # Buttons — [📖 Open in Viewer] — stretch — [Close] [Convert]
        btn_row_hl = QHBoxLayout()
        btn_viewer = QPushButton('📖 Open in Viewer')
        btn_viewer.setMinimumWidth(150)
        btn_viewer.setVisible(len(book_rows) == 1)
        ok_btn = QPushButton('Convert')
        ok_btn.setMinimumWidth(90)
        btn_close = QPushButton('Close')
        btn_close.setMinimumWidth(70)
        btn_row_hl.addWidget(btn_viewer)
        btn_row_hl.addStretch()
        btn_row_hl.addWidget(btn_close)
        btn_row_hl.addWidget(ok_btn)
        vl.addLayout(btn_row_hl)

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
                        if orig and not db.has_format(book_id, 'ORIGINAL_EPUB'):
                            with open(orig, 'rb') as _f:
                                self.gui.current_db.add_format(
                                    book_id, 'ORIGINAL_EPUB', _f,
                                    index_is_id=True, notify=False, replace=False)
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
                    new_label = ' · '.join(filter(None, [row['lang_label'], 'EPUB', _orient_label(target)]))
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
        ok_btn.clicked.connect(_on_apply)
        btn_close.clicked.connect(dlg.reject)
        btn_viewer.clicked.connect(
            lambda: (dlg.reject(), self._open_in_viewer(book_rows[0]['book_id'])))

        if not book_rows:
            _lock_controls()
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
                detect_script_from_epub, detect_script_from_text,
                detect_script_short)
            from calibre_plugins.furigana_ruby.chinese_engine import VARIANTS_S2T
        except ImportError:
            from lang_detect import (detect_book_language, lang_display,
                                     detect_script_from_epub, detect_script_from_text,
                                     detect_script_short)
            from chinese_engine import VARIANTS_S2T

        db = self.gui.current_db.new_api

        # ── Scan selected books ───────────────────────────────────
        book_rows = []
        excluded_counts    = {}   # only 'no supported format' books (excluded from table)
        non_applicable_counts = {}  # lang_label → count of non-applicable rows in table

        for book_id in book_ids:
            title      = db.field_for('title', book_id) or f'Book {book_id}'
            authors    = list(db.field_for('authors', book_id) or [])
            title_script = detect_script_short(title + ' ' + ' '.join(authors))
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
                else:
                    # Content detection ambiguous — check the local script cache
                    # (written after each S↔T conversion)
                    cached = _script_cache.get(str(book_id), '')
                    if 'hant' in cached.lower():
                        lang_info['is_traditional'] = True
                    elif 'hans' in cached.lower():
                        lang_info['is_simplified'] = True

            author_str = ', '.join(authors) if authors else ''

            # Japanese, Korean, etc. appear in the table as "Not applicable" rows
            if lang_info['is_japanese'] or lang_info['is_korean']:
                lang_label = (lang_display(lang_info) if lang_info.get('lang_raw')
                              else 'Unknown language')
                non_applicable_counts[lang_label] = (
                    non_applicable_counts.get(lang_label, 0) + 1)
                book_rows.append({'book_id': book_id, 'title': title,
                                   'author': author_str,
                                   'epub': epub_path, 'html': html_path,
                                   'fb2': fb2_path,  'txt': txt_path,
                                   'lang_info': lang_info,
                                   'title_script': title_script,
                                   'chinese_applicable': False,
                                   'lang_label': lang_label})
                continue

            book_rows.append({'book_id': book_id, 'title': title,
                               'author': author_str,
                               'epub': epub_path, 'html': html_path,
                               'fb2': fb2_path,  'txt': txt_path,
                               'lang_info': lang_info,
                               'title_script': title_script,
                               'chinese_applicable': True})

        total_selected = len(book_ids)
        n_chinese = sum(1 for r in book_rows if r.get('chinese_applicable', True))
        _chinese_book_ids = [r['book_id'] for r in book_rows
                             if r.get('chinese_applicable', True)]

        def _selection_summary():
            """One-line breakdown of the full selection for the summary panel."""
            parts = []
            if n_chinese:
                parts.append(f'{n_chinese} Chinese')
            for lang, count in non_applicable_counts.items():
                parts.append(f'{count} {lang}')
            if excluded_counts.get('no supported format', 0):
                parts.append(
                    f"{excluded_counts['no supported format']} without supported format")
            breakdown = ' · '.join(parts) if parts else 'none'
            return f'Selection: {total_selected} book(s) — {breakdown}'

        if n_chinese == 0:
            # All selected books are non-Chinese — show dialog anyway so the
            # table and summary explain why nothing can be processed
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

        # Metadata-only mode — bare checkbox + word-wrapping label (QCheckBox has no word wrap)
        meta_only_cb = QCheckBox()
        meta_only_cb.setChecked(True)
        _sp = QSizePolicy.Policy if PYQT6 else QSizePolicy
        meta_only_lbl = QLabel(
            'Skip content re-processing for books already in the target script. '
            'Only update title and author not yet in the target script.')
        meta_only_lbl.setWordWrap(True)
        meta_only_lbl.setSizePolicy(_sp.Expanding, _sp.Preferred)
        meta_only_row = QHBoxLayout()
        meta_only_row.setContentsMargins(0, 0, 0, 0)
        meta_only_row.setSpacing(4)
        meta_only_row.addWidget(meta_only_cb)
        meta_only_row.addWidget(meta_only_lbl)
        vl.addLayout(meta_only_row)

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
        title_labels  = {}   # book_id → WrappingClickableLabel
        sub_labels    = {}   # book_id → QLabel  (language · formats [· reason])
        sub_base_text = {}   # book_id → computed sub-label text (title/content/format info)
        cb_map        = {}   # book_id → QCheckBox (for _apply_row_style)
        applicable_ids = set()   # book_ids currently applicable; avoids isVisible quirks

        _SUB_STYLE = 'color: #545454; font-size: 11px;'
        _DIM_STYLE = 'color: #959595;'

        def _script_label(li):
            """Return a human-readable script label for the language column."""
            if li.get('is_simplified'):
                return 'Simplified (简体)'
            if li.get('is_traditional'):
                return 'Traditional (繁體)'
            if li.get('is_chinese'):
                return 'Chinese (中文)'
            return lang_display(li)

        def _compute_sub_base(row):
            """Build the sub-label text, always showing content/title scripts for Chinese books."""
            li   = row['lang_info']
            lang = _script_label(li)
            fmts = '  '.join(f for f, p in [('EPUB', row['epub']),
                                              ('HTML', row['html']),
                                              ('FB2',  row['fb2']),
                                              ('TXT',  row['txt'])] if p)
            ts = row.get('title_script', 'unknown')
            content_script = ('traditional' if li.get('is_traditional')
                               else 'simplified' if li.get('is_simplified')
                               else 'unknown')
            if content_script != 'unknown':
                content_label = 'Traditional' if content_script == 'traditional' else 'Simplified'
                if ts == 'unknown':
                    return f'Content: {content_label}  ·  {fmts}'
                ts_label  = 'Traditional' if ts == 'traditional' else 'Simplified'
                mismatch  = ts != content_script
                title_part = f'Title: {ts_label}' + (' ⚠' if mismatch else '')
                return f'{title_part}  ·  Content: {content_label}  ·  {fmts}'
            return f'{lang}  ·  {fmts}'

        sp_row = QSizePolicy.Policy if PYQT6 else QSizePolicy
        _top_align = Qt.AlignmentFlag.AlignTop if PYQT6 else Qt.AlignTop

        for row in book_rows:
            li    = row['lang_info']
            _base = _compute_sub_base(row)
            _ch_applicable = row.get('chinese_applicable', True)

            # ── Checkbox in fixed-width wrapper so alignment holds when hidden
            cb = QCheckBox()
            cb.setVisible(_ch_applicable)
            cb_box = QWidget()
            cb_box.setFixedWidth(20)
            cb_box_inner = QHBoxLayout()
            cb_box_inner.setContentsMargins(0, 0, 0, 0)
            cb_box_inner.setSpacing(0)
            cb_box_inner.addStretch()
            cb_box_inner.addWidget(cb)
            cb_box_inner.addStretch()
            cb_box.setLayout(cb_box_inner)

            # ── Title — Author (wrapping, clickable — toggles the checkbox)
            display_title = (f"{row['title']}  —  {row['author']}"
                             if row['author'] else row['title'])
            title_lbl = WrappingClickableLabel(display_title)
            title_lbl.setToolTip(display_title)
            title_lbl.setSizePolicy(sp_row.Expanding, sp_row.Preferred)
            if not _ch_applicable:
                title_lbl.setStyleSheet(_DIM_STYLE)
            title_lbl.clicked.connect(
                lambda _=None, c=cb, bid=row['book_id']:
                    c.toggle() if bid in applicable_ids and c.isEnabled() else None)

            # ── Status (right column, left-aligned to match header)
            status_lbl = QLabel('' if _ch_applicable else 'Not applicable')
            try:
                status_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            except AttributeError:
                status_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            status_lbl.setMinimumWidth(170)
            if not _ch_applicable:
                status_lbl.setStyleSheet('color: #959595;')

            # ── Sub-label: title/content scripts + formats (⚠ when mismatched)
            sub_lbl = QLabel(_base)
            sub_lbl.setStyleSheet(_SUB_STYLE if _ch_applicable else _DIM_STYLE)

            # ── Top row: [cb_box][title ×3] [status ×1]
            top_row = QHBoxLayout()
            top_row.setSpacing(4)
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.addWidget(cb_box, 0, _top_align)
            top_row.addWidget(title_lbl, 3)
            top_row.addWidget(status_lbl, 1, _top_align)

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
        result_te.setMinimumHeight(40)
        result_te.setMaximumHeight(200)
        result_te.setSizePolicy(sp2.Preferred, sp2.Minimum)
        result_te.document().contentsChanged.connect(
            lambda: result_te.setFixedHeight(
                min(200, max(40, int(result_te.document().size().height()) + 12))
            )
        )
        result_te.setPlainText(_selection_summary())
        vl.addWidget(result_te)

        # Buttons — [📖 Open in Viewer] — stretch — [Close] [Apply]
        btn_row_hl = QHBoxLayout()

        btn_viewer_ch = QPushButton('📖 Open in Viewer')
        btn_viewer_ch.setMinimumWidth(150)
        btn_viewer_ch.setVisible(len(book_ids) == 1)

        ok_btn    = QPushButton('Apply')
        ok_btn.setMinimumWidth(90)
        close_btn = QPushButton('Close')
        close_btn.setMinimumWidth(70)

        btn_row_hl.addWidget(btn_viewer_ch)
        btn_row_hl.addStretch()
        btn_row_hl.addWidget(close_btn)
        btn_row_hl.addWidget(ok_btn)
        vl.addLayout(btn_row_hl)

        # ── Logic helpers ─────────────────────────────────────────

        def _is_applicable(lang_info, title_script, going_s2t):
            """
            True if this book needs work in the given direction — either content
            conversion or title/author metadata is not yet in the target script.
            """
            li = lang_info
            if not li['is_chinese']:
                return True   # unknown metadata — show as applicable, let user decide
            if going_s2t:
                content_ok = li['is_simplified'] or not li['is_traditional']
                meta_ok    = title_script == 'simplified'
            else:
                content_ok = li['is_traditional'] or not li['is_simplified']
                meta_ok    = title_script == 'traditional'
            return content_ok or meta_ok

        def _update_apply_state():
            """Enable Apply iff at least one applicable book is checked."""
            any_checked = any(
                cb.isChecked()
                for cb, row in zip(checkboxes, book_rows)
                if row['book_id'] in applicable_ids)
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
            if not row.get('chinese_applicable', True):
                return  # permanently non-applicable (non-Chinese) — never re-style
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

            # Sub-label always shows script/title info — no reason suffix
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
                if not row.get('chinese_applicable', True):
                    continue  # permanently non-applicable — leave initial state
                applicable = _is_applicable(
                    row['lang_info'], row.get('title_script', 'unknown'), going_s2t)
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
                if not row.get('chinese_applicable', True):
                    continue  # permanently non-applicable — leave initial state
                applicable = _is_applicable(
                    row['lang_info'], row.get('title_script', 'unknown'), going_s2t)
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
            meta_only_cb.setEnabled(False)
            meta_only_lbl.setEnabled(False)
            header_cb.setEnabled(False)
            for cb in checkboxes:
                cb.setEnabled(False)

        def _unlock_controls():
            """Re-enable top controls; checkboxes restored by _restore_cb_enabled."""
            rb_s2t.setEnabled(True)
            rb_t2s.setEnabled(True)
            var_combo.setEnabled(True)
            meta_only_cb.setEnabled(True)
            meta_only_lbl.setEnabled(True)
            header_cb.setEnabled(True)
            _restore_cb_enabled()

        # Wire up signals
        rb_s2t.toggled.connect(lambda _: _refresh_variants())
        var_combo.currentIndexChanged.connect(lambda _: _update_var_desc())
        for cb in checkboxes:
            cb.stateChanged.connect(lambda _: _update_apply_state())
        header_cb.clicked.connect(_on_header_clicked)
        ok_btn.clicked.connect(lambda: _on_apply())
        close_btn.clicked.connect(dlg.reject)
        btn_viewer_ch.clicked.connect(
            # Use the first Chinese book if available, otherwise the single selected book
            # (which may be non-Chinese — the button shows for any 1-book selection).
            lambda: (dlg.reject(), self._open_in_viewer(
                _chinese_book_ids[0] if _chinese_book_ids else book_ids[0])))

        # Initial populate
        _refresh_variants()

        if summary_only:
            # No Chinese books — disable everything except Close
            _lock_controls()
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
            meta_only = meta_only_cb.isChecked()
            if not variant:
                return

            def _content_already_target(row):
                li = row['lang_info']
                return li.get('is_traditional') if going_s2t else li.get('is_simplified')

            if meta_only:
                content_tasks   = [r for r in tasks if not _content_already_target(r)]
                skipped_content = [r for r in tasks if _content_already_target(r)]
            else:
                content_tasks   = tasks
                skipped_content = []

            skipped_ids = {r['book_id'] for r in skipped_content}

            _lock_controls()
            ok_btn.setEnabled(False)
            result_te.setVisible(False)
            QApplication.processEvents()

            for row in tasks:
                lbl = status_labels[row['book_id']]
                lbl.setText('')
                lbl.setStyleSheet('')

            import time as _time

            results      = []
            saved        = 0
            save_errors  = []
            timed_out_ids = set()

            target_lang = 'zh-Hant' if going_s2t else 'zh-Hans'

            # Process one book at a time so a timeout on one doesn't block the rest
            for task in content_tasks:
                _done    = [False]
                _outcome = [None]
                worker   = ChineseWorker([task], variant, target_lang=target_lang)

                def _on_book_started(bid):
                    lbl = status_labels.get(bid)
                    if lbl:
                        lbl.setText('⏳ Converting…')
                        lbl.setStyleSheet('color: #545454;')

                def _on_book_finished(bid, ok, msg):
                    lbl = status_labels.get(bid)
                    if lbl:
                        if ok:
                            lbl.setText('✅ Done')
                            lbl.setStyleSheet('color: green;')
                            cb = cb_map.get(bid)
                            if cb:
                                cb.setVisible(False)
                        else:
                            lbl.setText('⚠ Error')
                            lbl.setStyleSheet('color: red;')
                            lbl.setToolTip(msg)

                def _on_done(ok, res, tb, _d=_done, _o=_outcome):
                    _d[0] = True
                    _o[0] = (ok, res, tb)

                worker.book_started.connect(_on_book_started)
                worker.book_finished.connect(_on_book_finished)
                worker.finished.connect(_on_done)
                worker.start()

                _start     = _time.time()
                _timed_out = False
                while not _done[0]:
                    QApplication.processEvents()
                    if _time.time() - _start > 300:
                        # Disconnect signals before abandoning so the thread
                        # can finish in the background without touching the UI
                        try: worker.book_started.disconnect()
                        except: pass
                        try: worker.book_finished.disconnect()
                        except: pass
                        try: worker.finished.disconnect()
                        except: pass
                        _timed_out = True
                        break

                if _timed_out:
                    timed_out_ids.add(task['book_id'])
                    lbl = status_labels.get(task['book_id'])
                    if lbl:
                        lbl.setText('⚠ Timed out')
                        lbl.setStyleSheet('color: red;')
                        lbl.setToolTip(
                            'Conversion timed out after 5 minutes. '
                            'This usually means the opencc library failed to load '
                            '(possible architecture mismatch — rebuild the plugin '
                            'zip on a machine with the same CPU as this one).')
                    for _fmt_key, _fmt_name in [
                            ('epub','EPUB'),('html','HTML'),('fb2','FB2'),('txt','TXT')]:
                        if task.get(_fmt_key):
                            results.append((task['book_id'], _fmt_name, None, 'Timed out'))
                    continue

                worker.wait()
                ok2, book_results, tb = _outcome[0]

                if not ok2:
                    lbl = status_labels.get(task['book_id'])
                    if lbl:
                        lbl.setText('⚠ Error')
                        lbl.setStyleSheet('color: red;')
                        lbl.setToolTip((tb or '')[:300])
                    for _fmt_key, _fmt_name in [
                            ('epub','EPUB'),('html','HTML'),('fb2','FB2'),('txt','TXT')]:
                        if task.get(_fmt_key):
                            results.append((task['book_id'], _fmt_name, None,
                                            tb or 'Unknown error'))
                    continue

                # Save converted files for this book
                for book_id, fmt, tmp_path, err in book_results:
                    lbl = status_labels.get(book_id)
                    if err or not tmp_path:
                        save_errors.append(f'{fmt} ({book_id}): {err}')
                        if lbl and lbl.text() != '⚠ Error':
                            lbl.setText('⚠ Conv. error')
                            lbl.setStyleSheet('color: red;')
                        results.append((book_id, fmt, None, err))
                        continue
                    try:
                        if prefs['keep_original']:
                            orig = task.get(fmt.lower())
                            if orig:
                                orig_fmt = f'ORIGINAL_{fmt}'
                                if not db.has_format(book_id, orig_fmt):
                                    with open(orig, 'rb') as _f:
                                        self.gui.current_db.add_format(
                                            book_id, orig_fmt, _f,
                                            index_is_id=True, notify=False, replace=False)
                        db.add_format(book_id, fmt, tmp_path, replace=True)
                        saved += 1
                        results.append((book_id, fmt, tmp_path, None))
                    except Exception as e:
                        save_errors.append(f'{fmt} ({book_id}): save failed: {e}')
                        if lbl:
                            lbl.setText('⚠ Save error')
                            lbl.setStyleSheet('color: red;')
                            lbl.setToolTip(str(e))
                        results.append((book_id, fmt, None, str(e)))
                    finally:
                        try: os.unlink(tmp_path)
                        except: pass

            # Books whose content conversion failed or timed out — skip metadata
            failed_content_ids = {r[0] for r in results if r[3]} | timed_out_ids

            # Update metadata (title + authors) — always, for all selected tasks
            meta_updated  = 0
            meta_errors   = []
            target_script = 'traditional' if going_s2t else 'simplified'
            try:
                try:
                    from calibre_plugins.furigana_ruby.chinese_engine import _get_converter
                except ImportError:
                    from chinese_engine import _get_converter
                converter = _get_converter(variant)
                for row in tasks:
                    book_id = row['book_id']
                    if book_id in failed_content_ids:
                        continue
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
                        row['title_script'] = target_script

                        if book_id in skipped_ids:
                            lbl = status_labels.get(book_id)
                            if lbl:
                                lbl.setText('✅ Metadata updated')
                                lbl.setStyleSheet('color: green;')
                            cb = cb_map.get(book_id)
                            if cb:
                                cb.setVisible(False)
                    except Exception as e:
                        meta_errors.append(f'Book {book_id}: {e}')
            except Exception as e:
                meta_errors.append(f'Converter unavailable: {e}')

            self.gui.library_view.model().refresh_ids(
                list({r['book_id'] for r in tasks}))

            # Summary
            lines = []
            n_attempted = len(content_tasks)
            n_failed    = len({r[0] for r in results if r[3]})
            n_succeeded = len(content_tasks) - len(timed_out_ids) - n_failed
            if content_tasks:
                lines.append(
                    f'✅ Converted {saved} format(s) across {n_succeeded} book(s)'
                    f'  [{direction} / {variant}]'
                )
            if timed_out_ids:
                lines.append(
                    f'⚠ {len(timed_out_ids)} book(s) timed out — conversion skipped '
                    f'(see individual book rows for details)')
            if skipped_content:
                lines.append(
                    f'   Skipped content re-processing for {len(skipped_content)} book(s)')
            if meta_updated:
                lines.append(f'   Updated title/author metadata for {meta_updated} book(s)')
            if save_errors:
                lines.append(f'⚠ {len(save_errors)} save error(s):')
                lines += [f'  {e}' for e in save_errors[:5]]
            if meta_errors:
                lines.append(f'⚠ {len(meta_errors)} metadata error(s):')
                lines += [f'  {e}' for e in meta_errors[:3]]
            lines += ['', _selection_summary()]

            result_te.setVisible(True)
            result_te.setPlainText('\n'.join(lines))

            # Update lang_info in memory for successfully converted content books
            converted_ids = {r[0] for r in results if not r[3]}
            lang_code = 'zh-Hant' if going_s2t else 'zh-Hans'
            for row in book_rows:
                bid = row['book_id']
                if bid in converted_ids:
                    if going_s2t:
                        row['lang_info']['is_simplified'] = False
                        row['lang_info']['is_traditional'] = True
                    else:
                        row['lang_info']['is_traditional'] = False
                        row['lang_info']['is_simplified'] = True
                    _script_cache[str(bid)] = lang_code
                # Rebuild sub-label for all processed books (content or metadata)
                if bid in converted_ids or bid in skipped_ids:
                    new_base = _compute_sub_base(row)
                    sub_base_text[bid] = new_base
                    sub_labels[bid].setText(new_base)

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
        dlg.setMinimumHeight(400)
        dlg.resize(580, 620)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(9, 9, 9, 6)
        widget = ConfigWidget()
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame if PYQT6 else QFrame.NoFrame)
        vl.addWidget(scroll)
        bb = QDialogButtonBox(
            (QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            if PYQT6 else (QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        vl.addWidget(bb)
        if (dlg.exec() if PYQT6 else dlg.exec_()):
            widget.save_settings()
            # Sync action.py's in-memory prefs from what config.py just wrote to
            # disk; without this, any subsequent prefs write (e.g. annotate_levels)
            # would flush the old in-memory dict and overwrite the saved tile_action.
            try:
                prefs.refresh()
            except Exception:
                pass
            action = ('chinese'   if widget._rb_tile_zh.isChecked() else
                      'direction' if widget._rb_tile_dir.isChecked() else 'ruby')
            self._apply_tile_action(action)

    # ── About ─────────────────────────────────────────────────────

    def show_about(self):
        from calibre_plugins.furigana_ruby import FuriganaPluginBase
        ver = '.'.join(str(x) for x in FuriganaPluginBase.version)

        html = (
            f'<h3>振り仮名 Ruby & More Plugin <span style="font-size:small;color:grey;">v{ver}</span></h3>'
            '<p>A Calibre plugin for East Asian ebooks. Select one or more books, '
            'click the <b>振り仮名</b> toolbar button, and choose a command. '
            'The toolbar button\'s default action is configurable in Preferences.</p>'
            '<hr/>'

            '<p><b>振り仮名 &mdash; Edit Ruby&hellip;</b>'
            '&nbsp;&nbsp;<span style="color:#545454;font-size:small;">Japanese EPUBs</span></p>'
            '<p style="margin:0 0 0 12px;color:#333;">'
            'Adds or removes furigana (reading aids) above kanji, filtered by JLPT level '
            '(N5 &rarr; N1). Publisher-supplied ruby is never overwritten. '
            'Auto-generated ruby appears in <span style="color:#2b6fd4">blue</span>; '
            'use the in-viewer toggle (&#x1F233; / &#x1F4D6; / &#x1F21A;) to switch between '
            'all, publisher-only, or hidden. '
            'Choose between two engines: <b>Enhanced</b> (built-in, no download required) or '
            '<b>High-accuracy</b> (SudachiPy, ~40 MB optional download) for '
            'morphology-aware readings with conjugation support.</p>'
            '<hr/>'

            '<p><b>繁 &mdash; Convert Chinese S&harr;T&hellip;</b>'
            '&nbsp;&nbsp;<span style="color:#545454;font-size:small;">Chinese &middot; EPUB &middot; HTML &middot; FB2 &middot; TXT</span></p>'
            '<p style="margin:0 0 0 12px;color:#333;">'
            'Converts between Simplified and Traditional Chinese. '
            'Supports 8 OpenCC variants including Taiwan (正體), Hong Kong (港式繁體), '
            'and phrase-level vocabulary conversion. '
            'Title and author metadata are always converted alongside book content. '
            'The dialog detects script mismatches between content and metadata and flags them with &#9888;. '
            'A checkbox lets you skip content re-processing for books already in the target script '
            'and fix only the title/author. '
            'Text nodes only &mdash; tags, CSS, and scripts are never modified.</p>'
            '<hr/>'

            '<p><b>&harr; &mdash; Text Direction&hellip;</b>'
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

        # (Bug report section moved to Check for Updates dialog)
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
        """Query GitHub releases API and show a custom dialog with update status
        and a bug-report section below."""
        import json, sys as _sys
        from urllib.request import urlopen, Request
        from urllib.error   import URLError
        from calibre_plugins.furigana_ruby import FuriganaPluginBase

        local        = FuriganaPluginBase.version
        local_str    = '.'.join(str(x) for x in local)
        api_url      = ('https://api.github.com/repos/'
                        'tobethesidekick/furigana-ruby/releases/latest')
        releases_url = ('https://github.com/tobethesidekick/'
                        'furigana-ruby/releases/latest')
        issues_url   = ('https://github.com/tobethesidekick/'
                        'furigana-ruby/issues')

        # ── Fetch update status ───────────────────────────────────
        update_html = ''
        try:
            req  = Request(api_url,
                           headers={'User-Agent': 'FuriganaRuby-Calibre-Plugin'})
            resp = urlopen(req, timeout=10)
            data = json.loads(resp.read().decode('utf-8'))
            tag       = data.get('tag_name', '').lstrip('v')
            parts     = [int(x) for x in tag.split('.') if x.isdigit()]
            remote    = tuple(parts[:3])
            remote_str = '.'.join(str(x) for x in remote)
            html_url  = data.get('html_url', releases_url)
            if remote > local:
                update_html = (
                    f'<h3>🎉 Update available: v{remote_str}</h3>'
                    f'Installed: v{local_str}<br>'
                    f'<a href="{html_url}">Download v{remote_str} from GitHub</a><br>'
                    f'<small>Install via Calibre → Preferences → Plugins → '
                    f'Load plugin from file.</small>')
            else:
                update_html = (
                    f'<h3>✓ You are up to date</h3>'
                    f'Installed: v{local_str}<br>'
                    f'<a href="{releases_url}">View releases on GitHub</a>')
        except URLError as e:
            update_html = (
                f'<b>Could not reach GitHub.</b><br>{e}<br>'
                f'<a href="{releases_url}">Check GitHub manually</a>')
        except Exception as e:
            update_html = (
                f'<b>Update check failed:</b><br>{e}<br>'
                f'<a href="{releases_url}">GitHub releases</a>')

        # ── Build custom dialog ───────────────────────────────────
        dlg = QDialog(self.gui)
        dlg.setWindowTitle('FuriganaRuby — Check for Updates')
        dlg.setMinimumWidth(440)
        vl = QVBoxLayout(dlg)
        vl.setSpacing(8)
        vl.setContentsMargins(16, 14, 16, 12)

        # Update status
        update_lbl = QTextBrowser()
        update_lbl.setOpenExternalLinks(True)
        update_lbl.setHtml(update_html)
        update_lbl.setFrameShape(QFrame.Shape.NoFrame if PYQT6
                                 else QFrame.NoFrame)
        update_lbl.setMaximumHeight(110)
        vl.addWidget(update_lbl)

        # Separator
        sep = QFrame()
        try:
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFrameShadow(QFrame.Shadow.Sunken)
        except AttributeError:
            sep.setFrameShape(QFrame.HLine)
            sep.setFrameShadow(QFrame.Sunken)
        vl.addWidget(sep)

        # Bug report section
        bug_lbl = QLabel('<b>Having an issue?</b>  Generate a report and attach '
                         f'it to a <a href="{issues_url}">bug ticket</a>.')
        bug_lbl.setOpenExternalLinks(True)
        bug_lbl.setWordWrap(True)
        vl.addWidget(bug_lbl)

        bug_row = QHBoxLayout()
        btn_open_diag = QPushButton('Open Diagnosis')
        btn_copy_diag = QPushButton('Copy Diagnosis')
        btn_open_log  = QPushButton('Open Log Folder')
        bug_row.addWidget(btn_open_diag)
        bug_row.addWidget(btn_copy_diag)
        bug_row.addWidget(btn_open_log)
        bug_row.addStretch()
        vl.addLayout(bug_row)

        def _open_diag():
            try:
                try:
                    from calibre_plugins.furigana_ruby.diagnostics import (
                        generate_report)
                except ImportError:
                    from diagnostics import generate_report
                report = generate_report()
            except Exception as e:
                report = f'Error generating report:\n{e}'
            prev = QDialog(dlg)
            prev.setWindowTitle('Diagnostic Report')
            prev.setMinimumWidth(560)
            prev.resize(620, 440)
            pv = QVBoxLayout(prev)
            pv.addWidget(QLabel('Attach this report to your bug ticket:'))
            tb = QTextEdit()
            tb.setReadOnly(True)
            tb.setPlainText(report)
            tb.setFontFamily('Courier New')
            tb.setFontPointSize(10)
            pv.addWidget(tb)
            cb2 = QPushButton('Copy to clipboard')
            def _cp2():
                QApplication.clipboard().setText(report)
                cb2.setText('✓ Copied to clipboard!')
            cb2.clicked.connect(_cp2)
            try:
                bb2 = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            except AttributeError:
                bb2 = QDialogButtonBox(QDialogButtonBox.Close)
            bb2.rejected.connect(prev.reject)
            r2 = QHBoxLayout()
            r2.addWidget(cb2); r2.addStretch(); r2.addWidget(bb2)
            pv.addLayout(r2)
            prev.exec() if PYQT6 else prev.exec_()

        def _copy_diag():
            try:
                try:
                    from calibre_plugins.furigana_ruby.diagnostics import (
                        generate_report)
                except ImportError:
                    from diagnostics import generate_report
                report = generate_report()
                QApplication.clipboard().setText(report)
                btn_copy_diag.setText('✓ Copied to clipboard!')
            except Exception as e:
                btn_copy_diag.setText(f'Error: {str(e)[:30]}')

        def _open_log():
            try:
                try:
                    from calibre_plugins.furigana_ruby.plugin_logger import (
                        get_log_path)
                except ImportError:
                    from plugin_logger import get_log_path
                log_path = get_log_path()
                import subprocess as _sp
                if _sys.platform == 'darwin':
                    # -R reveals and selects the file in Finder
                    _sp.run(['open', '-R', log_path])
                elif _sys.platform == 'win32':
                    # /select highlights the file in Explorer
                    _sp.run(['explorer', f'/select,{log_path}'])
                else:
                    # Linux: best-effort — select not universally supported
                    try:
                        _sp.run(['nautilus', '--select', log_path])
                    except FileNotFoundError:
                        _sp.run(['xdg-open', os.path.dirname(log_path)])
            except Exception as e:
                from calibre.gui2 import warning_dialog
                warning_dialog(self.gui, 'Open Log Folder',
                               f'Could not open folder:\n{e}', show=True)

        btn_open_diag.clicked.connect(_open_diag)
        btn_copy_diag.clicked.connect(_copy_diag)
        btn_open_log.clicked.connect(_open_log)

        # OK button
        try:
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        except AttributeError:
            bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(dlg.accept)
        vl.addWidget(bb)

        dlg.exec() if PYQT6 else dlg.exec_()
