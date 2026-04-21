"""
action.py  v12
Unified level-state dialog:
  - Single "Edit Ruby…" button; checkboxes show which levels are currently
    annotated in the EPUB (pre-checked = already present).
  - Checking a new level → adds it; unchecking an existing level → removes it.
  - "Open in Viewer" closes the status modal automatically.
"""

import os
import tempfile

try:
    from PyQt6.QtWidgets import (QMenu, QProgressDialog, QApplication,
                                  QToolButton, QDialog, QVBoxLayout,
                                  QHBoxLayout, QCheckBox, QLabel,
                                  QGroupBox, QDialogButtonBox, QPushButton,
                                  QSizePolicy, QTextEdit)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QIcon, QAction
    PYQT6 = True
except ImportError:
    from PyQt5.Qt import (QMenu, QProgressDialog, QApplication,
                           QToolButton, QDialog, QVBoxLayout,
                           QHBoxLayout, QCheckBox, QLabel,
                           QGroupBox, QDialogButtonBox, QPushButton,
                           QSizePolicy, QTextEdit,
                           Qt, QThread, pyqtSignal, QIcon, QAction)
    PYQT6 = False

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, info_dialog, warning_dialog

_ALL_LEVELS = {'N1', 'N2', 'N3', 'N4', 'N5', 'unlisted'}


# ── Unified level-manage dialog ───────────────────────────────────────────────

class LevelManageDialog(QDialog):
    """
    Shows all JLPT levels as checkboxes.
    Levels that are currently annotated in the EPUB are pre-checked.
    On Apply: checked - current  → levels to ADD
               current - checked → levels to REMOVE
    """
    def __init__(self, parent, current_levels=None):
        super().__init__(parent)
        self.setWindowTitle('Ruby Annotation Levels')
        self.setMinimumWidth(440)

        if current_levels is None:
            current_levels = set()

        layout = QVBoxLayout()
        self.setLayout(layout)

        if current_levels:
            present = ', '.join(
                l for l in ['N1','N2','N3','N4','N5','unlisted']
                if l in current_levels
            )
            desc_text = (
                f'<b>Currently annotated:</b> {present}<br>'
                '<small>☑ = has ruby &nbsp;·&nbsp; ☐ = no ruby yet<br>'
                'Check a level to <b>add</b> ruby; uncheck to <b>remove</b> it.</small>'
            )
        else:
            desc_text = (
                '<b>No auto ruby yet.</b><br>'
                '<small>Check the levels you want to add furigana for.</small>'
            )

        desc = QLabel(desc_text)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        grp = QGroupBox('JLPT Levels')
        grp_layout = QVBoxLayout()
        self._cbs = {}
        for level, label in [
            ('N1',       'N1  —  Rare & literary kanji'),
            ('N2',       'N2  —  Advanced kanji'),
            ('N3',       'N3  —  Intermediate kanji  ★'),
            ('N4',       'N4  —  Basic kanji  (学、週、料理…)'),
            ('N5',       'N5  —  Elementary kanji  (日、人、山…)'),
            ('unlisted', 'Unlisted  —  Kanji not in any JLPT list'),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(level in current_levels)
            self._cbs[level] = cb
            grp_layout.addWidget(cb)
        grp.setLayout(grp_layout)
        layout.addWidget(grp)

        layout.addWidget(QLabel('Quick select:'))
        btn_row = QHBoxLayout()
        for label, levels in [
            ('None',    set()),
            ('N1',      {'N1'}),
            ('N1–N2',   {'N1', 'N2'}),
            ('N1–N3 ★', {'N1', 'N2', 'N3'}),
            ('N1–N4',   {'N1', 'N2', 'N3', 'N4'}),
            ('All',     _ALL_LEVELS),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, lvls=levels: self._apply(lvls))
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        note = QLabel(
            '<small><i>Publisher ruby is never modified.<br>'
            'Changes only affect auto-generated (blue) ruby.</i></small>'
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        try:
            std = QDialogButtonBox.StandardButton
            bb = QDialogButtonBox(std.Ok | std.Cancel)
        except AttributeError:
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = bb.button(
            QDialogButtonBox.StandardButton.Ok if PYQT6 else QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setText('Apply')
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _apply(self, levels):
        for level, cb in self._cbs.items():
            cb.setChecked(level in levels)

    def selected_levels(self):
        return {lvl for lvl, cb in self._cbs.items() if cb.isChecked()}


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

        self.menu.addSeparator()

        a3 = QAction('ℹ About / Help', self.gui)
        a3.triggered.connect(self.show_about)
        self.menu.addAction(a3)

    # ── Helpers ───────────────────────────────────────────────────

    def _selected_ids(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        return [self.gui.library_view.model().id(r) for r in rows]

    def _epub_path(self, book_id):
        db = self.gui.current_db.new_api
        return (db.format_abspath(book_id, 'EPUB')
                if db.has_format(book_id, 'EPUB') else None)

    def _default_levels(self):
        from calibre.utils.config import JSONConfig
        p = JSONConfig('plugins/furigana_ruby')
        p.defaults['annotate_levels'] = ['N1', 'N2', 'N3']
        return set(p.get('annotate_levels', ['N1', 'N2', 'N3']))

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
                'Select a Japanese EPUB book first.', show=True)
            return
        self._show_status_dialog(ids[0])

    # ── Unified status dialog ─────────────────────────────────────

    def _show_status_dialog(self, book_id):
        path = self._epub_path(book_id)
        if not path:
            warning_dialog(self.gui, 'No EPUB',
                'No EPUB format found for this book.', show=True)
            return

        db = self.gui.current_db.new_api

        # ── Build dialog ──────────────────────────────────────────
        dlg = QDialog(self.gui)
        dlg.setWindowTitle('Furigana Status')
        dlg.setMinimumWidth(580)
        dlg.setMinimumHeight(400)
        dlg.resize(600, 420)

        vl = QVBoxLayout()
        vl.setSpacing(10)
        dlg.setLayout(vl)

        te = QTextEdit()
        te.setReadOnly(True)
        sp = QSizePolicy.Policy if PYQT6 else QSizePolicy
        te.setSizePolicy(sp.Expanding, sp.Expanding)
        vl.addWidget(te)

        # ── Button row: [Edit Ruby…] ——— [Open in Viewer] [Close] ─
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_edit   = QPushButton('✦ Edit Ruby…')
        btn_viewer = QPushButton('📖 Open in Viewer')
        btn_close  = QPushButton('Close')

        btn_edit.setMinimumWidth(110)
        btn_viewer.setMinimumWidth(130)
        btn_close.setMinimumWidth(70)

        btn_row.addWidget(btn_edit)
        btn_row.addStretch()
        btn_row.addWidget(btn_viewer)
        btn_row.addWidget(btn_close)

        vl.addLayout(btn_row)

        # ── Refresh helper ────────────────────────────────────────
        def refresh(result_msg=None):
            """Re-scan the EPUB and update text + button states."""
            try:
                auto_count, pub_count, file_count = self._scan_epub(path)
            except Exception as e:
                te.setPlainText(f'⚠ Error scanning EPUB:\n{e}')
                return

            title    = db.field_for('title', book_id) or 'this book'
            has_auto = auto_count > 0

            if auto_count == 0 and pub_count == 0:
                status = (f'❌  No ruby in "{title}"\n\n'
                          f'No furigana annotations found.\n'
                          f'Click "Edit Ruby…" to add them.')
            elif auto_count == 0:
                status = (f'📖  Publisher ruby only — "{title}"\n\n'
                          f'  Publisher annotations:  {pub_count:,}\n'
                          f'  Auto-generated:         0\n\n'
                          f'Click "Edit Ruby…" to fill in remaining kanji.')
            else:
                status = (f'✅  Furigana active — "{title}"\n\n'
                          f'  Auto-generated (blue):   {auto_count:,}\n'
                          f'  Publisher (original):    {pub_count:,}\n'
                          f'  Files with ruby:         {file_count}\n\n'
                          f'In viewer — Cmd+Shift+R to toggle:\n'
                          f'  🈳 All → 📖 Publisher only → 🈚 Off')

            full_text = (result_msg + '\n\n' + ('─' * 40) + '\n\n' + status
                         if result_msg else status)
            te.setPlainText(full_text)

        # ── Edit Ruby handler ─────────────────────────────────────
        def on_edit():
            if not self._ensure_deps():
                return

            # Detect which levels are currently in the EPUB
            current_levels = self._get_annotated_levels(path)

            level_dlg = LevelManageDialog(self.gui, current_levels=current_levels)
            accepted = (level_dlg.exec() == QDialog.DialogCode.Accepted
                        if PYQT6 else level_dlg.exec_() == QDialog.Accepted)
            if not accepted:
                return

            new_levels = level_dlg.selected_levels()

            levels_to_add    = new_levels - current_levels
            levels_to_remove = current_levels - new_levels

            if not levels_to_add and not levels_to_remove:
                return   # nothing changed — close picker silently

            btn_edit.setEnabled(False)
            result_parts = []

            # ── Remove first ──────────────────────────────────────
            if levels_to_remove:
                # None = full strip (faster); subset = selective strip
                rl = (None if levels_to_remove >= current_levels
                      else levels_to_remove)
                msg = self._run_epub(
                    book_id, path, 'remove', None,
                    display_levels=levels_to_remove,
                    remove_levels=rl,
                )
                result_parts.append(msg)

            # ── Add next (re-fetch path in case Calibre moved it) ─
            if levels_to_add:
                updated_path = self._epub_path(book_id) or path
                # Save last-used levels for future default
                from calibre.utils.config import JSONConfig
                JSONConfig('plugins/furigana_ruby')['annotate_levels'] = \
                    sorted(levels_to_add)
                al = None if levels_to_add >= _ALL_LEVELS else levels_to_add
                msg = self._run_epub(
                    book_id, updated_path, 'add',
                    annotate_levels=al,
                    display_levels=levels_to_add,
                )
                result_parts.append(msg)

            self.gui.library_view.model().refresh_ids([book_id])
            btn_edit.setEnabled(True)
            refresh('\n'.join(result_parts))

        # ── Viewer: also closes the modal ─────────────────────────
        def on_viewer():
            dlg.reject()
            self._open_in_viewer(book_id)

        btn_edit.clicked.connect(on_edit)
        btn_viewer.clicked.connect(on_viewer)
        btn_close.clicked.connect(dlg.reject)

        # Initial render
        refresh()

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
        prog.setValue(0)
        prog.show()

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
                'Select a Japanese/Chinese/Korean EPUB book first.', show=True)
            return
        self._show_orientation_dialog(ids[0])

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
            prog.setValue(0)
            prog.show()

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
                self.gui.current_db.new_api.add_format(
                    book_id, 'EPUB', tmp, replace=True)
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

    # ── About ─────────────────────────────────────────────────────

    def show_about(self):
        info_dialog(self.gui, '振り仮名 Ruby Plugin',
            '<h3>振り仮名 Ruby Plugin</h3>'
            '<b>Workflow:</b><ol>'
            '<li>Select a Japanese EPUB in the library</li>'
            '<li>Click the <b>振り仮名 Ruby</b> toolbar button</li>'
            '<li>Review status, then click <b>Edit Ruby…</b></li>'
            '<li>Check the levels you want annotated — pre-checked levels are '
            'already in the book</li>'
            '<li>Click <b>Apply</b> — checked levels are added, unchecked are removed</li>'
            '<li>Click <b>Open in Viewer</b> to read</li>'
            '<li>Press <b>Cmd+Shift+R</b> in viewer to toggle display</li>'
            '</ol>'
            '<b>Toggle modes:</b> 🈳 All → 📖 Publisher only → 🈚 Off<br><br>'
            '<b>Publisher ruby</b> is never modified.<br>'
            '<b>Auto ruby</b> appears in '
            '<span style="color:#4a72c4">blue</span>.',
            show=True)
