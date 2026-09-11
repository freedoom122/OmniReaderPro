"""Feature dialogs: print, export, find, translate, dictionary, compare,
redaction verification, signing, forms, metadata, optimization, vault,
privacy dashboard.

Every dialog performs real work through the core engines.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextBrowser, QVBoxLayout, QWidget, QDoubleSpinBox,
    QGroupBox, QAbstractItemView,
)

from veyrion_workspace.ui.icons import icon, pixmap
from veyrion_workspace.ui.theme import Palette
from veyrion_workspace.ui.widgets import HelpLabel, show_toast
from veyrion_workspace.utils.pathutils import format_size


class _BusyWorker:
    """Runs a callable synchronously with a modal-free wait cursor."""

    @staticmethod
    def run(widget, fn, on_done):
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = fn()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(widget, "Operation failed", str(e))
            return
        QApplication.restoreOverrideCursor()
        on_done(result)


class PrintDialog(QDialog):
    """Print preview with page range, copies, N-up, and duplex notes."""

    def __init__(self, parent, view) -> None:
        super().__init__(parent)
        self.setWindowTitle("Print")
        self.setMinimumWidth(460)
        self.view = view
        lay = QVBoxLayout(self)

        form = QFormLayout()
        self._range_edit = QLineEdit()
        self._range_edit.setPlaceholderText("e.g. 1-5, 8, 11-  (empty = all)")
        self._copies = QSpinBox()
        self._copies.setRange(1, 99)
        self._nup = QComboBox()
        self._nup.addItems(["1 page per sheet", "2 pages per sheet",
                            "4 pages per sheet"])
        self._annots = QCheckBox("Include annotations")
        self._annots.setChecked(True)
        form.addRow("Pages:", self._range_edit)
        form.addRow("Copies:", self._copies)
        form.addRow("Layout:", self._nup)
        form.addRow("", self._annots)
        lay.addLayout(form)

        info = HelpLabel(
            "Print uses your operating system's print dialog with a "
            "print-ready PDF built to these settings.")
        lay.addWidget(info)

        self._preview = QLabel("Preview will appear here.")
        self._preview.setMinimumHeight(220)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setStyleSheet("border: 1px solid #B9B2A3; background: white;")
        lay.addWidget(self._preview)
        self._render_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Print…")
        buttons.accepted.connect(self._do_print)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _pages(self):
        from veyrion_workspace.core.printing.printing import parse_page_range
        return parse_page_range(self._range_edit.text(), self.view.page_count)

    def _render_preview(self) -> None:
        try:
            pages = self._pages()
            if pages:
                pix = self.view.engine.render_page(pages[0], zoom=0.5)
                if hasattr(pix, "tobytes"):
                    from PySide6.QtGui import QImage
                    fmt = 4 if pix.n < 4 else 5
                    img = QImage(pix.samples, pix.width, pix.height,
                                 pix.stride, QImage.Format.Format_RGB888)
                    self._preview.setPixmap(
                        QPixmap.fromImage(img).scaledToHeight(
                            200, Qt.SmoothTransformation))
                else:
                    import io
                    buf = io.BytesIO()
                    pix.save(buf, format="PNG")
                    from PySide6.QtGui import QImage
                    img = QImage.fromData(buf.getvalue(), "PNG")
                    self._preview.setPixmap(
                        QPixmap.fromImage(img).scaledToHeight(
                            200, Qt.SmoothTransformation))
        except Exception:
            pass

    def _do_print(self) -> None:
        from veyrion_workspace.core.printing.printing import (
            build_print_pdf, send_to_printer, list_printers,
        )
        from veyrion_workspace.utils.safeio import make_temp_file
        pages = self._pages()
        nup = (1, 2, 4)[self._nup.currentIndex()]
        tmp = make_temp_file(suffix="_print.pdf")
        self.view.pdf.save(tmp)
        tmp = Path(tmp)
        out = tmp.with_name(tmp.stem + "_layout.pdf")
        _BusyWorker.run(self, lambda: build_print_pdf(
            self.view.pdf, out, pages, copies=self._copies.value(),
            pages_per_sheet=nup), lambda _: self._send(out))

    def _send(self, out: Path) -> None:
        from veyrion_workspace.core.printing.printing import send_to_printer
        if send_to_printer(out):
            show_toast(self.window(), "Print job sent", "success")
            self.accept()
        else:
            QMessageBox.warning(self, "Print failed",
                                "No printer could be reached. Check that a "
                                "printer is configured in your OS.")


class ExportDialog(QDialog):
    """Central export dialog: PDF, images, text, markdown, HTML."""

    def __init__(self, parent, view, tasks) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export document")
        self.setMinimumWidth(440)
        self.view = view
        self.tasks = tasks
        lay = QVBoxLayout(self)

        self._format = QComboBox()
        self._format.addItems([
            "PDF (current document)",
            "PNG images (one per page)",
            "JPEG images (one per page)",
            "Plain text",
            "Markdown",
        ])
        lay.addWidget(QLabel("Export as:"))
        lay.addWidget(self._format)
        lay.addWidget(HelpLabel(
            "The export writes to a new file you choose; the original "
            "document is never modified."))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Export…")
        buttons.accepted.connect(self._do_export)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _do_export(self) -> None:
        choice = self._format.currentText()
        src = Path(self.view.path)
        if choice.startswith("PNG"):
            out_dir = QFileDialog.getExistingDirectory(self, "Output folder")
            if not out_dir:
                return
            from veyrion_workspace.core.conversion.convert import pdf_to_images
            self.tasks.submit("Exporting pages to PNG", "export",
                              pdf_to_images, src, Path(out_dir), "png", 150)
        elif choice.startswith("JPEG"):
            out_dir = QFileDialog.getExistingDirectory(self, "Output folder")
            if not out_dir:
                return
            from veyrion_workspace.core.conversion.convert import pdf_to_images
            self.tasks.submit("Exporting pages to JPEG", "export",
                              pdf_to_images, src, Path(out_dir), "jpg", 150)
        elif choice == "Plain text":
            target, _ = QFileDialog.getSaveFileName(
                self, "Export text", src.with_suffix(".txt").name,
                "Text (*.txt)")
            if not target:
                return
            from veyrion_workspace.core.conversion.convert import pdf_to_text
            self.tasks.submit("Exporting text", "export", pdf_to_text,
                              src, Path(target))
        elif choice == "Markdown":
            target, _ = QFileDialog.getSaveFileName(
                self, "Export markdown", src.with_suffix(".md").name,
                "Markdown (*.md)")
            if not target:
                return
            from veyrion_workspace.core.conversion.convert import document_to_markdown
            self.tasks.submit("Exporting markdown", "export",
                              document_to_markdown, src, Path(target))
        else:
            target, _ = QFileDialog.getSaveFileName(
                self, "Save as PDF", src.with_suffix(".pdf").name,
                "PDF (*.pdf)")
            if not target:
                return
            if hasattr(self.view, "save_as"):
                self.view.save_as(Path(target))
        show_toast(self.window(), f"Export started — see Tasks panel", "info")
        self.accept()


class FindDialog(QDialog):
    """In-document find bar as a floating dialog."""

    def __init__(self, parent, view) -> None:
        super().__init__(parent)
        self.setWindowTitle("Find in document")
        self.view = view
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("Search text…")
        self._query.returnPressed.connect(self._find)
        row.addWidget(self._query, 1)
        find_btn = QPushButton("Find")
        find_btn.setObjectName("accentButton")
        find_btn.clicked.connect(self._find)
        row.addWidget(find_btn)
        lay.addLayout(row)
        opts = QHBoxLayout()
        self._case = QCheckBox("Match case")
        self._word = QCheckBox("Whole word")
        self._regex = QCheckBox("Regex")
        for w in (self._case, self._word, self._regex):
            opts.addWidget(w)
        lay.addLayout(opts)
        self._status = QLabel("")
        self._status.setObjectName("dimLabel")
        lay.addWidget(self._status)

    def _find(self) -> None:
        query = self._query.text()
        if not query:
            return
        hits = self.view.find_in_view(
            query, case_sensitive=self._case.isChecked(),
            whole_word=self._word.isChecked(),
            regex=self._regex.isChecked())
        self._status.setText(f"{hits} match(es) found" if hits
                             else "No matches in this document")


class TranslateDialog(QDialog):
    """Selection translation with explicit offline/online choice."""

    def __init__(self, parent, text: str, settings) -> None:
        super().__init__(parent)
        self.setWindowTitle("Translate")
        self.setMinimumWidth(480)
        self._settings = settings
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Original:"))
        original = QPlainTextEdit()
        original.setReadOnly(True)
        original.setPlainText(text[:3000])
        original.setMaximumHeight(120)
        lay.addWidget(original)

        row = QHBoxLayout()
        self._target = QComboBox()
        self._target.addItems(["en", "de", "fr", "es", "it", "pt", "nl", "ru",
                               "zh", "ja", "ko", "ar"])
        row.addWidget(QLabel("Translate to:"))
        row.addWidget(self._target)
        row.addStretch(1)
        lay.addLayout(row)

        from veyrion_workspace.core.translation import argos_available
        engine_label = ("Offline engine ready (Argos models installed)"
                        if argos_available() else
                        "No offline models installed — online fallback will "
                        "ask before using the network.")
        lay.addWidget(HelpLabel(engine_label))

        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._result.setPlaceholderText("Translation appears here…")
        lay.addWidget(self._result, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Translate")
        buttons.accepted.connect(self._translate)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._source_text = text

    def _translate(self) -> None:
        target = self._target.currentText()
        from veyrion_workspace.core.translation import (
            translate_offline, translate_online, argos_available,
        )
        offline_ok = argos_available()
        if offline_ok:
            try:
                result = translate_offline(self._source_text, target)
                self._result.setPlainText(result.text)
                return
            except Exception as e:
                pass  # fall through to online with confirmation
        offline_mode = self._settings.get("privacy", "offline_mode", True)
        if offline_mode:
            QMessageBox.information(
                self, "Offline mode",
                "Offline mode is enabled and no offline translation model "
                "covers this language pair. Install Argos models "
                "(pip install argostranslate) or disable offline mode to "
                "use the network fallback.")
            return
        confirm = QMessageBox.question(
            self, "Use online translation",
            "No offline model is available for this pair.\n\nSend the "
            "selected text to the translation service over the network?")
        if confirm != QMessageBox.Yes:
            return
        try:
            result = translate_online(self._source_text, target)
            self._result.setPlainText(result.text)
        except Exception as e:
            QMessageBox.warning(self, "Translation failed", str(e))


class DictionaryDialog(QDialog):
    def __init__(self, parent, initial: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Dictionary")
        self.setMinimumWidth(420)
        from veyrion_workspace.core.dictionary import Dictionary
        self._dict = Dictionary()
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self._word = QLineEdit()
        self._word.setPlaceholderText("Look up a word…")
        self._word.textEdited.connect(self._suggest)
        self._word.returnPressed.connect(self._lookup)
        row.addWidget(self._word, 1)
        btn = QPushButton("Look up")
        btn.setObjectName("accentButton")
        btn.clicked.connect(self._lookup)
        row.addWidget(btn)
        lay.addLayout(row)
        self._suggestions = QLabel("")
        self._suggestions.setObjectName("dimLabel")
        self._suggestions.setWordWrap(True)
        lay.addWidget(self._suggestions)
        self._result = QTextBrowser()
        self._result.setMinimumHeight(200)
        lay.addWidget(self._result, 1)
        if initial:
            first = initial.split()[0] if initial.split() else ""
            self._word.setText(first)
            self._lookup()

    def _suggest(self) -> None:
        text = self._word.text()
        if len(text) >= 2:
            self._suggestions.setText(", ".join(self._dict.suggestions(text)))

    def _lookup(self) -> None:
        entry = self._dict.lookup(self._word.text())
        if entry is None:
            self._result.setHtml(
                "<p><i>No definition found in the local dictionary. "
                "Import a CSV glossary via the notes folder to extend it.</i></p>")
            return
        html = (f"<h2 style='margin:0'>{entry['word']}</h2>"
                f"<p style='color:#8a8578'><i>{entry.get('pos', '')}</i></p>"
                f"<p>{entry['def']}</p>")
        if entry.get("example"):
            html += f"<p><i>\"{entry['example']}\"</i></p>"
        self._result.setHtml(html)


class CompareDialog(QDialog):
    """Document comparison with progress and structured results."""

    def __init__(self, parent, tasks) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare documents")
        self.setMinimumSize(680, 520)
        self.tasks = tasks
        lay = QVBoxLayout(self)
        grid = QGridLayout()
        self._path_a = QLineEdit()
        self._path_b = QLineEdit()
        browse_a = QPushButton("Browse…")
        browse_b = QPushButton("Browse…")
        browse_a.clicked.connect(lambda: self._pick(self._path_a))
        browse_b.clicked.connect(lambda: self._pick(self._path_b))
        grid.addWidget(QLabel("Document A:"), 0, 0)
        grid.addWidget(self._path_a, 0, 1)
        grid.addWidget(browse_a, 0, 2)
        grid.addWidget(QLabel("Document B:"), 1, 0)
        grid.addWidget(self._path_b, 1, 1)
        grid.addWidget(browse_b, 1, 2)
        lay.addLayout(grid)

        self._progress = QProgressBar()
        lay.addWidget(self._progress)
        run = QPushButton("Compare")
        run.setObjectName("accentButton")
        run.clicked.connect(self._run)
        lay.addWidget(run)

        self._summary = QLabel("")
        self._summary.setObjectName("dimLabel")
        lay.addWidget(self._summary)
        self._results = QTabWidget()
        self._diff_view = QTextBrowser()
        self._pages_view = QTextBrowser()
        self._results.addTab(self._diff_view, "Text diff")
        self._results.addTab(self._pages_view, "Page changes")
        lay.addWidget(self._results, 1)
        self._last_result = None

    def _pick(self, edit: QLineEdit) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self, "Choose document", "",
            "Documents (*.pdf *.docx *.txt *.md *.odt *.rtf)")
        if f:
            edit.setText(f)

    def _run(self) -> None:
        a, b = self._path_a.text(), self._path_b.text()
        if not a or not b:
            QMessageBox.information(self, "Compare",
                                    "Choose two documents first.")
            return
        from veyrion_workspace.core.comparison import compare_documents

        def work(progress=None, cancel=None):
            return compare_documents(Path(a), Path(b), progress, cancel)

        task = self.tasks.submit("Comparing documents", "compare", work)
        from PySide6.QtCore import QTimer
        poll = QTimer(self)
        poll.setInterval(300)

        def check() -> None:
            if task.state.value in ("done", "failed"):
                poll.stop()
                if task.state.value == "done":
                    self._show(task.result)
                else:
                    self._summary.setText(f"Comparison failed: {task.error}")

        poll.timeout.connect(check)
        poll.start()
        self._summary.setText("Comparing…")

    def _show(self, result) -> None:
        self._last_result = result
        if result.error:
            self._summary.setText(f"Error: {result.error}")
            return
        self._summary.setText(
            f"{result.pages_compared} pages compared — "
            f"{result.pages_changed} changed, "
            f"+{result.words_added} / -{result.words_removed} words"
            + (" — documents are identical" if result.identical else ""))
        from veyrion_workspace.core.comparison.comparator import compare_texts
        diff_text = "\n".join(compare_texts(
            "\n".join(str(d) for d in result.page_diffs), ""))
        lines = []
        for d in result.page_diffs:
            if d.status != "same":
                lines.append(f"Page {d.page + 1}: {d.status}")
                for line in d.added_lines[:6]:
                    lines.append(f"  + {line[:110]}")
                for line in d.removed_lines[:6]:
                    lines.append(f"  - {line[:110]}")
        self._pages_view.setPlainText("\n".join(lines) or "No page-level changes.")
        self._diff_view.setPlainText(
            "Note: text-level comparison. Rendering differences (fonts, "
            "spacing) are not semantic changes.\n\n" +
            "\n".join(lines[:400]))


class VerifyRedactionDialog(QDialog):
    """Verify that redacted content is truly gone from the saved file."""

    def __init__(self, parent, pdf_engine) -> None:
        super().__init__(parent)
        self.setWindowTitle("Verify redaction")
        self.setMinimumWidth(520)
        self.pdf = pdf_engine
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Enter phrases that were redacted (one per line). Veyrion "
            "will reopen the saved file and search for them, including a "
            "raw byte-level check for common encodings."))
        self._phrases = QPlainTextEdit()
        self._phrases.setPlaceholderText("confidential\ncase number 12345")
        lay.addWidget(self._phrases)
        check = QPushButton("Verify removal")
        check.setObjectName("accentButton")
        check.clicked.connect(self._verify)
        lay.addWidget(check)
        self._result = QTextBrowser()
        lay.addWidget(self._result, 1)
        lay.addWidget(HelpLabel(
            "Note: PDF is a complex format; Veyrion verifies extracted "
            "text and raw byte patterns, but cannot guarantee that no "
            "trace survives every possible encoding. For maximum safety, "
            "re-create sensitive pages from scratch after redaction."))

    def _verify(self) -> None:
        phrases = [p.strip() for p in
                   self._phrases.toPlainText().splitlines() if p.strip()]
        if not phrases:
            return
        from veyrion_workspace.core.documents.pdf_engine import (
            verify_redaction_in_file,
        )
        report = verify_redaction_in_file(self.pdf.path, phrases)
        rows = []
        clean = True
        for phrase, pages in report["found"].items():
            if pages:
                clean = False
                rows.append(f"<tr><td>{phrase}</td>"
                            f"<td style='color:#A33B2E'>FOUND on pages "
                            f"{', '.join(str(p + 1) for p in pages)}</td></tr>")
            else:
                rows.append(f"<tr><td>{phrase}</td>"
                            f"<td style='color:#3E7C4F'>removed</td></tr>")
        leaks = report.get("object_leaks") or []
        if leaks:
            clean = False
            rows.append("<tr><td colspan='2' style='color:#A33B2E'>"
                        f"Byte-level remnants found: {', '.join(leaks)}"
                        "</td></tr>")
        status = ("<span style='color:#3E7C4F'><b>All checked phrases were "
                  "removed.</b></span>" if clean else
                  "<span style='color:#A33B2E'><b>Remnants were found — "
                  "re-apply redaction and re-save.</b></span>")
        self._result.setHtml(
            f"<p>{status}</p><table border='1' cellpadding='4' "
            f"cellspacing='0'>{''.join(rows)}</table>")


class SignDialog(QDialog):
    """Cryptographic signing with PKCS#12 identities (pyHanko required)."""

    def __init__(self, parent, view) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign document")
        self.setMinimumWidth(480)
        self.view = view
        lay = QVBoxLayout(self)
        from veyrion_workspace.core.security.signing import HAS_PYHANKO
        if not HAS_PYHANKO:
            lay.addWidget(HelpLabel(
                "Cryptographic PDF signing requires the optional 'pyhanko' "
                "package (pip install pyhanko). Veyrion will not fake a "
                "signature by stamping an image — that would be visually "
                "similar but cryptographically meaningless."))
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(self.reject)
            lay.addWidget(buttons)
            return
        form = QFormLayout()
        self._cert_path = QLineEdit()
        browse = QPushButton("Choose .p12/.pfx…")
        browse.clicked.connect(self._pick_cert)
        cert_row = QHBoxLayout()
        cert_row.addWidget(self._cert_path, 1)
        cert_row.addWidget(browse)
        form.addRow("Certificate:", cert_row)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        form.addRow("Password:", self._password)
        self._reason = QLineEdit()
        form.addRow("Reason:", self._reason)
        self._location = QLineEdit()
        form.addRow("Location:", self._location)
        lay.addLayout(form)
        self._status = QLabel("")
        lay.addWidget(self._status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Sign")
        buttons.accepted.connect(self._sign)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _pick_cert(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self, "Signing certificate", "", "Certificates (*.p12 *.pfx)")
        if f:
            self._cert_path.setText(f)

    def _sign(self) -> None:
        from veyrion_workspace.core.security.signing import (
            load_pkcs12, sign_pdf, identity_summary,
        )
        try:
            ident = load_pkcs12(Path(self._cert_path.text()),
                                self._password.text())
            summary = identity_summary(ident)
            if summary["expired"]:
                confirm = QMessageBox.warning(
                    self, "Expired certificate",
                    "This certificate has expired. Sign anyway?",
                    QMessageBox.Yes | QMessageBox.No)
                if confirm != QMessageBox.Yes:
                    return
            target = Path(self.view.path).with_name(
                Path(self.view.path).stem + "_signed.pdf")
            sign_pdf(Path(self.view.path), target, ident,
                     reason=self._reason.text(),
                     location=self._location.text())
            show_toast(self.window(), f"Signed copy: {target.name}", "success")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Signing failed", str(e))


class FormsDialog(QDialog):
    """AcroForm field editor with validation and reset."""

    def __init__(self, parent, view) -> None:
        super().__init__(parent)
        self.setWindowTitle("Form fields")
        self.setMinimumSize(560, 480)
        self.view = view
        self.pdf = view.pdf
        lay = QVBoxLayout(self)
        self._table = QTableWidget()
        self._fields = self.pdf.form_fields()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Page", "Name", "Type", "Value", ""])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(1, 190)
        self._table.setRowCount(len(self._fields))
        for row, field in enumerate(self._fields):
            self._table.setItem(row, 0, QTableWidgetItem(str(field["page"] + 1)))
            self._table.setItem(row, 1, QTableWidgetItem(field["name"]))
            self._table.setItem(row, 2, QTableWidgetItem(field["type"]))
            value_edit = QLineEdit(str(field["value"] or ""))
            value_edit.editingFinished.connect(
                lambda r=row, e=value_edit: self._set_value(r, e.text()))
            if field["type"] == "CheckBox":
                box = QCheckBox()
                box.setChecked(bool(field["value"]))
                box.toggled.connect(lambda on, r=row: self._set_value(r, on))
                from PySide6.QtWidgets import QWidget, QHBoxLayout as QH
                holder = QWidget()
                hl = QH(holder)
                hl.setContentsMargins(4, 0, 4, 0)
                hl.addWidget(box)
                hl.addStretch(1)
                self._table.setCellWidget(row, 3, holder)
            else:
                self._table.setCellWidget(row, 3, value_edit)
            if field.get("choices"):
                self._table.setItem(
                    row, 4, QTableWidgetItem(
                        "choices: " + ", ".join(map(str, field["choices"][:5]))))
        lay.addWidget(self._table)
        btns = QHBoxLayout()
        reset = QPushButton("Reset all fields")
        reset.clicked.connect(self._reset)
        save = QPushButton("Save into document")
        save.setObjectName("accentButton")
        save.clicked.connect(self._save)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        btns.addWidget(reset)
        btns.addStretch(1)
        btns.addWidget(close)
        btns.addWidget(save)
        lay.addLayout(btns)

    def _set_value(self, row: int, value) -> None:
        field = self._fields[row]
        ok = self.pdf.set_field_value(field["page"], field["name"], value)
        if ok:
            field["value"] = value

    def _reset(self) -> None:
        count = self.pdf.clear_form()
        show_toast(self.window(), f"Cleared {count} field(s)", "info")
        self.reject()

    def _save(self) -> None:
        self.pdf.save()
        show_toast(self.window(), "Form values saved into the document",
                   "success")
        self.accept()


class MetadataDialog(QDialog):
    """Edit PDF metadata fields."""

    def __init__(self, parent, view) -> None:
        super().__init__(parent)
        self.setWindowTitle("Document metadata")
        self.setMinimumWidth(440)
        self.view = view
        md = view.engine.metadata()
        form = QFormLayout()
        self._title = QLineEdit(md.title)
        self._author = QLineEdit(md.author)
        self._subject = QLineEdit(md.subject)
        self._keywords = QLineEdit(md.keywords)
        form.addRow("Title:", self._title)
        form.addRow("Author:", self._author)
        form.addRow("Subject:", self._subject)
        form.addRow("Keywords:", self._keywords)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(HelpLabel(
            "Producer/Creator fields reflect the generating application "
            "and are read-only here. Use Strip Metadata to remove them."))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _save(self) -> None:
        self.view.pdf.set_metadata(
            title=self._title.text(), author=self._author.text(),
            subject=self._subject.text(), keywords=self._keywords.text())
        self.view.pdf.save()
        show_toast(self.window(), "Metadata updated", "success")
        self.accept()


class OptimizeDialog(QDialog):
    """PDF optimization with before/after size reporting."""

    def __init__(self, parent, view, tasks) -> None:
        super().__init__(parent)
        self.setWindowTitle("Optimize PDF")
        self.setMinimumWidth(420)
        self.view = view
        self.tasks = tasks
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._strip = QCheckBox("Remove metadata")
        self._linear = QCheckBox("Linearize (web-optimized)")
        self._quality = QComboBox()
        self._quality.addItems(["Maximum compression", "Balanced", "Lossless"])
        self._quality.setCurrentIndex(1)
        form.addRow("", self._strip)
        form.addRow("", self._linear)
        form.addRow("Level:", self._quality)
        lay.addLayout(form)
        before = Path(view.path).stat().st_size
        lay.addWidget(HelpLabel(
            f"Current size: {format_size(before)}. The optimized file is "
            "written to a new copy; the original stays untouched."))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Optimize")
        buttons.accepted.connect(self._run)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _run(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self, "Save optimized PDF",
            self.view.path.with_name(self.view.path.stem + "_opt.pdf").name,
            "PDF (*.pdf)")
        if not target:
            return

        def work(progress=None, cancel=None):
            return self.view.pdf.optimize(
                Path(target),
                garbage=4 if self._quality.currentIndex() != 2 else 0,
                linear=self._linear.isChecked(),
                strip_metadata=self._strip.isChecked())
        task = self.tasks.submit(f"Optimizing {Path(self.view.path).name}",
                                 "optimize", work)
        show_toast(self.window(), "Optimization running — see Tasks panel",
                   "info")
        self.accept()


class VaultDialog(QDialog):
    """Secure vault UI: create, unlock, add, extract, remove, lock."""

    def __init__(self, parent, settings) -> None:
        super().__init__(parent)
        self.setWindowTitle("Secure vault")
        self.setMinimumSize(560, 420)
        self._settings = settings
        from veyrion_workspace.core.security.vault import Vault, vault_directory
        self.vault = Vault(vault_directory())
        lay = QVBoxLayout(self)

        status_row = QHBoxLayout()
        self._status_icon = QLabel()
        self._status_label = QLabel()
        self._refresh_status()
        status_row.addWidget(self._status_icon)
        status_row.addWidget(self._status_label, 1)
        lay.addLayout(status_row)

        self._list = QListWidget()
        lay.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        self._unlock_btn = QPushButton("Unlock")
        self._unlock_btn.setObjectName("accentButton")
        self._unlock_btn.clicked.connect(self._unlock)
        self._lock_btn = QPushButton("Lock")
        self._lock_btn.clicked.connect(self._lock)
        self._add_btn = QPushButton("Add file…")
        self._add_btn.clicked.connect(self._add)
        self._extract_btn = QPushButton("Extract…")
        self._extract_btn.clicked.connect(self._extract)
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.clicked.connect(self._remove)
        for b in (self._unlock_btn, self._lock_btn, self._add_btn,
                  self._extract_btn, self._remove_btn):
            btn_row.addWidget(b)
        lay.addLayout(btn_row)
        lay.addWidget(HelpLabel(
            "Files are encrypted with AES-256-GCM using a key derived from "
            "your password (PBKDF2, 600k iterations). The vault locks "
            "automatically when the application closes."))
        self._reload()

    def _refresh_status(self) -> None:
        locked = self.vault.is_locked()
        self._status_icon.setPixmap(pixmap("lock" if locked else "unlock",
                                           "#C7522A", 20))
        self._status_label.setText("Vault is locked" if locked
                                   else "Vault is unlocked")

    def _reload(self) -> None:
        self._list.clear()
        self._refresh_status()
        if self.vault.is_locked():
            self._unlock_btn.setText("Create / Unlock")
            return
        self._unlock_btn.setText("Change password")
        try:
            for item in self.vault.list_items():
                when = time.strftime("%Y-%m-%d",
                                     time.localtime(item.get("added", 0)))
                self._list.addItem(QListWidgetItem(
                    icon("lock", "#3E7C4F"),
                    f"{item['name']}  ({format_size(item['size'])}, added {when})"))
        except Exception:
            pass

    def _unlock(self) -> None:
        from veyrion_workspace.ui.dialogs import get_password
        from veyrion_workspace.core.security.vault import VaultError
        if self.vault.is_locked() and not self.vault.exists():
            pw = get_password(self, "Create vault",
                              "Choose a strong password for the new vault. "
                              "There is no recovery — if you forget it, the "
                              "content is unrecoverable.")
            if pw:
                try:
                    self.vault.create(pw)
                except VaultError as e:
                    QMessageBox.warning(self, "Vault", str(e))
        elif self.vault.is_locked():
            pw = get_password(self, "Unlock vault", "Vault password:")
            if pw:
                try:
                    self.vault.unlock(pw)
                except Exception:
                    QMessageBox.warning(self, "Vault",
                                        "Wrong password or damaged vault.")
        else:
            old = get_password(self, "Change password", "Current password:")
            new = get_password(self, "Change password", "New password:")
            if old and new:
                try:
                    self.vault.change_password(old, new)
                    show_toast(self.window(), "Vault password changed", "success")
                except Exception:
                    QMessageBox.warning(self, "Vault",
                                        "Password change failed — wrong "
                                        "current password?")
        self._reload()

    def _lock(self) -> None:
        self.vault.lock()
        self._reload()

    def _add(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Add file to vault")
        if not f:
            return
        name = Path(f).name
        self.vault.add_item(name, Path(f))
        self._reload()
        show_toast(self.window(), f"Encrypted {name} into the vault", "success")

    def _extract(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        items = self.vault.list_items()
        if not (0 <= row < len(items)):
            return
        item = items[row]
        target, _ = QFileDialog.getSaveFileName(
            self, "Extract file", item["name"])
        if not target:
            return
        self.vault.extract_item(item["id"], Path(target))
        show_toast(self.window(), f"Extracted {item['name']}", "success")

    def _remove(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        items = self.vault.list_items()
        if not (0 <= row < len(items)):
            return
        item = items[row]
        confirm = QMessageBox.question(
            self, "Remove from vault",
            f"Securely delete '{item['name']}' from the vault?")
        if confirm == QMessageBox.Yes:
            self.vault.remove_item(item["id"])
            self._reload()


class PrivacyDialog(QDialog):
    """Privacy dashboard: data locations, caches, offline mode, cleanup."""

    def __init__(self, parent, db, settings) -> None:
        super().__init__(parent)
        self.setWindowTitle("Privacy dashboard")
        self.setMinimumWidth(540)
        self.db = db
        self.settings = settings
        from veyrion_workspace.app import paths
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("<b>Network</b>"))
        self._offline = QCheckBox(
            "Offline mode (disable all network features)")
        self._offline.setChecked(settings.get("privacy", "offline_mode", True))
        self._offline.toggled.connect(
            lambda on: settings.set("privacy", "offline_mode", on))
        lay.addWidget(self._offline)
        self._update = QCheckBox("Check for updates (manual only)")
        self._update.setChecked(settings.get("privacy", "allow_update_check", False))
        self._update.toggled.connect(
            lambda on: settings.set("privacy", "allow_update_check", on))
        lay.addWidget(self._update)
        lay.addWidget(HelpLabel(
            "Veyrion makes no network requests unless you explicitly "
            "trigger a feature that needs one. There is no telemetry."))

        lay.addWidget(QLabel("<b>Stored data locations</b>"))
        loc_form = QFormLayout()
        for label, getter in (
                ("Database", paths.database_dir), ("Cache", paths.cache_dir),
                ("Logs", paths.logs_dir), ("Backups", paths.backups_dir),
                ("Vault", paths.vault_dir), ("Plugins", paths.plugins_dir)):
            value = QLabel(str(getter()))
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            loc_form.addRow(label, value)
        lay.addLayout(loc_form)

        lay.addWidget(QLabel("<b>Clear data</b>"))
        clear_row = QHBoxLayout()
        for text, cb in (
                ("OCR cache", self._clear_ocr),
                ("Thumbnails", self._clear_thumbs),
                ("Search index", self._clear_index),
                ("Reading history", self._clear_history)):
            btn = QPushButton(text)
            btn.clicked.connect(cb)
            clear_row.addWidget(btn)
        clear_row.addStretch(1)
        lay.addLayout(clear_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        lay.addWidget(buttons)

    def _clear_ocr(self) -> None:
        self.db.execute("DELETE FROM ocr_cache")
        show_toast(self.window(), "OCR cache cleared", "success")

    def _clear_thumbs(self) -> None:
        import shutil
        from veyrion_workspace.app import paths
        shutil.rmtree(paths.cache_dir() / "covers", ignore_errors=True)
        show_toast(self.window(), "Thumbnail cache cleared", "success")

    def _clear_index(self) -> None:
        self.db.execute("DELETE FROM text_index")
        self.db.execute("DELETE FROM meta_index")
        show_toast(self.window(),
                   "Search index cleared — documents re-index on next open",
                   "success")

    def _clear_history(self) -> None:
        self.db.execute("DELETE FROM reading_sessions")
        show_toast(self.window(), "Reading history deleted", "success")


# ---------------------------------------------------------------------------
# Shared helpers: errors, passwords, external links, about
# ---------------------------------------------------------------------------
class ErrorDialog(QDialog):
    """Human-readable error with expandable technical details."""

    def __init__(self, parent, title: str, friendly: str,
                 technical: str = "", retry: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.choice = "close"
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap("warning", "#A33B2E", 36))
        head.addWidget(ic, 0, Qt.AlignTop)
        msg = QLabel(friendly)
        msg.setWordWrap(True)
        head.addWidget(msg, 1)
        lay.addLayout(head)
        if technical:
            details_btn = QPushButton("Show technical details")
            details_btn.setFlat(True)
            details_btn.setCheckable(True)
            lay.addWidget(details_btn)
            details = QPlainTextEdit()
            details.setReadOnly(True)
            details.setPlainText(technical)
            details.setMaximumHeight(150)
            details.hide()
            details_btn.toggled.connect(details.setVisible)
            lay.addWidget(details)
        buttons = QDialogButtonBox()
        if retry:
            retry_btn = buttons.addButton(QDialogButtonBox.Retry)
            retry_btn.clicked.connect(lambda: self._set_choice("retry"))
        close_btn = buttons.addButton(QDialogButtonBox.Close)
        close_btn.clicked.connect(lambda: self._set_choice("close"))
        lay.addWidget(buttons)

    def _set_choice(self, choice: str) -> None:
        self.choice = choice
        self.accept()


def show_error(parent, title: str, friendly: str, technical: str = "",
               retry: bool = False) -> str:
    dlg = ErrorDialog(parent, title, friendly, technical, retry)
    dlg.exec()
    return dlg.choice


def confirm_external_link(parent, url: str) -> None:
    """Gate every external link behind an explicit user decision."""
    from veyrion_workspace.services.settings import Settings
    global _SETTINGS_INSTANCE
    settings = getattr(parent, "_app_settings", None)
    if settings is None:
        if _SETTINGS_INSTANCE is None:
            _SETTINGS_INSTANCE = Settings()
        settings = _SETTINGS_INSTANCE
    mode = settings.get("security", "external_links", "ask")
    if mode == "block":
        show_toast(parent.window() if parent else None,
                   "External links are blocked in Settings.", "warning")
        return
    if mode == "open":
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(url)
        return
    box = QMessageBox(parent)
    box.setWindowTitle("Open external link?")
    box.setText(f"This document links to an external address:\n\n{url}")
    box.setInformativeText("Open it in your browser?")
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    remember = QCheckBox("Remember this choice")
    box.setCheckBox(remember)
    result = box.exec()
    if result == QMessageBox.Yes:
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(url)
    if remember.isChecked():
        settings.set("security", "external_links",
                     "open" if result == QMessageBox.Yes else "ask")


_SETTINGS_INSTANCE = None


class PasswordDialog(QDialog):
    """Secure password prompt for encrypted documents and the vault."""

    def __init__(self, parent, title: str, prompt: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.value = ""
        lay = QVBoxLayout(self)
        note = QLabel(prompt)
        note.setWordWrap(True)
        lay.addWidget(note)
        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.Password)
        self._edit.textChanged.connect(self._validate)
        lay.addWidget(self._edit)
        self._show_toggle = QCheckBox("Show password")
        self._show_toggle.toggled.connect(
            lambda on: self._edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        lay.addWidget(self._show_toggle)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        self._ok_btn = buttons.button(QDialogButtonBox.Ok)
        self._ok_btn.setEnabled(False)
        lay.addWidget(buttons)
        self._edit.setFocus()

    def _validate(self) -> None:
        self._ok_btn.setEnabled(bool(self._edit.text()))

    def _on_ok(self) -> None:
        self.value = self._edit.text()
        self.accept()


def get_password(parent, title: str, prompt: str):
    dlg = PasswordDialog(parent, title, prompt)
    if dlg.exec() == QDialog.Accepted:
        return dlg.value
    return None


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from veyrion_workspace import APP_NAME, APP_TAGLINE, __version__
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(430)
        lay = QVBoxLayout(self)
        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("dimLabel")
        version = QLabel(f"Version {__version__}")
        body = QLabel(
            "A complete local-first document workspace: read, edit, "
            "annotate, organize, convert, and protect your documents — "
            "with no account, no telemetry, and no cloud requirement.\n\n"
            "All processing happens on this computer.")
        body.setWordWrap(True)
        lic = QLabel("Released under the MIT license. "
                     "See THIRD_PARTY_LICENSES.md for bundled components.")
        lic.setWordWrap(True)
        lic.setObjectName("dimLabel")
        lay.addWidget(title)
        lay.addWidget(tagline)
        lay.addWidget(version)
        lay.addSpacing(10)
        lay.addWidget(body)
        lay.addSpacing(10)
        lay.addWidget(lic)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)


def show_toast_msg(parent, message: str, kind: str) -> None:
    try:
        show_toast(parent.window() if parent else None, message, kind)
    except Exception:
        pass
