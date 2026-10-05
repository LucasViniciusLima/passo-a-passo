"""Diálogo "Exportar": PDF, GIF ou vídeo MP4, com progresso e Cancelar."""

from __future__ import annotations

import re
import threading
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from app.export import TRANSITIONS, Cancelled, GifOptions, PdfOptions, VideoOptions
from app.project.storage import ProjectWorkspace

FORMATS = [("pdf", "PDF", ".pdf"), ("gif", "GIF animado", ".gif"), ("mp4", "Vídeo MP4", ".mp4")]
FILTERS = {"pdf": "PDF (*.pdf)", "gif": "GIF (*.gif)", "mp4": "Vídeo MP4 (*.mp4)"}


def safe_filename(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip().strip(".")
    return name or "tutorial"


class ExportWorker(QThread):
    progress = Signal(float)
    done = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, kind: str, workspace: ProjectWorkspace, dest: Path, options, parent=None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.workspace = workspace
        self.dest = dest
        self.options = options
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        from app.export.pdf import export_pdf
        from app.export.video import export_gif, export_mp4

        func = {"pdf": export_pdf, "gif": export_gif, "mp4": export_mp4}[self.kind]
        try:
            path = func(self.workspace.project, self.workspace.root, self.dest, self.options,
                        progress=self.progress.emit, cancel=self.cancel_event)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:  # o erro vira aviso no diálogo
            self.failed.emit(str(exc))
        else:
            self.done.emit(str(path))


def _transition_combo() -> QComboBox:
    combo = QComboBox()
    for key, label in TRANSITIONS.items():
        combo.addItem(label, key)
    return combo


def _seconds_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(1.0, 15.0)
    spin.setSingleStep(0.5)
    spin.setValue(3.0)
    spin.setSuffix(" s")
    return spin


class ExportDialog(QDialog):
    def __init__(self, workspace: ProjectWorkspace, start_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar tutorial")
        self.setMinimumWidth(460)
        self.workspace = workspace
        self.start_dir = start_dir or Path.home() / "Documents"
        self.worker: ExportWorker | None = None
        self.result_path: Path | None = None

        self.format = QComboBox()
        for key, label, _ in FORMATS:
            self.format.addItem(label, key)

        # PDF
        self.pdf_size = QComboBox()
        self.pdf_size.addItems(["A4", "Carta"])
        self.pdf_per_page = QComboBox()
        self.pdf_per_page.addItem("1 passo por página", 1)
        self.pdf_per_page.addItem("2 passos por página", 2)
        self.pdf_orientation = QComboBox()
        self.pdf_orientation.addItem("Automática", "auto")
        self.pdf_orientation.addItem("Retrato", "retrato")
        self.pdf_orientation.addItem("Paisagem", "paisagem")
        pdf_page = QWidget()
        f = QFormLayout(pdf_page)
        f.addRow("Papel", self.pdf_size)
        f.addRow("Layout", self.pdf_per_page)
        f.addRow("Orientação", self.pdf_orientation)

        # GIF
        self.gif_width = QSpinBox()
        self.gif_width.setRange(320, 1920)
        self.gif_width.setSingleStep(160)
        self.gif_width.setValue(960)
        self.gif_width.setSuffix(" px")
        self.gif_fps = QSpinBox()
        self.gif_fps.setRange(5, 30)
        self.gif_fps.setValue(12)
        self.gif_fps.setSuffix(" quadros/s")
        self.gif_seconds = _seconds_spin()
        self.gif_transition = _transition_combo()
        gif_page = QWidget()
        f = QFormLayout(gif_page)
        f.addRow("Largura", self.gif_width)
        f.addRow("Fluidez", self.gif_fps)
        f.addRow("Tempo por passo", self.gif_seconds)
        f.addRow("Transição", self.gif_transition)

        # Vídeo
        self.video_res = QComboBox()
        self.video_res.addItem("1080p (1920×1080)", 1080)
        self.video_res.addItem("720p (1280×720)", 720)
        self.video_seconds = _seconds_spin()
        self.video_transition = _transition_combo()
        video_page = QWidget()
        f = QFormLayout(video_page)
        f.addRow("Resolução", self.video_res)
        f.addRow("Tempo por passo", self.video_seconds)
        f.addRow("Transição", self.video_transition)

        self.pages = QStackedWidget()
        for page in (pdf_page, gif_page, video_page):
            self.pages.addWidget(page)

        self.path = QLineEdit()
        self.btn_browse = QPushButton("Escolher…")
        path_row = QHBoxLayout()
        path_row.addWidget(self.path, 1)
        path_row.addWidget(self.btn_browse)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.status = QLabel("")
        self.btn_export = QPushButton("Exportar")
        self.btn_export.setDefault(True)
        self.btn_cancel = QPushButton("Fechar")
        buttons = QHBoxLayout()
        buttons.addWidget(self.status, 1)
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_export)

        form = QFormLayout()
        form.addRow("Formato", self.format)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.pages)
        layout.addWidget(QLabel("Salvar em:"))
        layout.addLayout(path_row)
        layout.addWidget(self.bar)
        layout.addLayout(buttons)

        self.format.currentIndexChanged.connect(self._format_changed)
        self.btn_browse.clicked.connect(self._browse)
        self.btn_export.clicked.connect(self.start_export)
        self.btn_cancel.clicked.connect(self._cancel_or_close)
        self._format_changed()

    # --- formulário ------------------------------------------------------

    def kind(self) -> str:
        return self.format.currentData()

    def _extension(self) -> str:
        return {k: ext for k, _, ext in FORMATS}[self.kind()]

    def _format_changed(self) -> None:
        self.pages.setCurrentIndex(self.format.currentIndex())
        current = Path(self.path.text()) if self.path.text() else None
        base = current.with_suffix("") if current else self.start_dir / safe_filename(self.workspace.project.title)
        self.path.setText(str(base.with_suffix(self._extension())))

    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar para", self.path.text(), FILTERS[self.kind()])
        if path:
            path = Path(path)
            if path.suffix.lower() != self._extension():
                path = path.with_suffix(self._extension())
            self.path.setText(str(path))

    def options(self):
        kind = self.kind()
        if kind == "pdf":
            return PdfOptions(page_size=self.pdf_size.currentText(), steps_per_page=self.pdf_per_page.currentData(),
                              orientation=self.pdf_orientation.currentData())
        if kind == "gif":
            return GifOptions(width=self.gif_width.value(), fps=self.gif_fps.value(),
                              seconds_per_step=self.gif_seconds.value(),
                              transition=self.gif_transition.currentData())
        return VideoOptions(height=self.video_res.currentData(), seconds_per_step=self.video_seconds.value(),
                            transition=self.video_transition.currentData())

    # --- exportação ------------------------------------------------------

    def _set_running(self, running: bool) -> None:
        for w in (self.format, self.pages, self.path, self.btn_browse, self.btn_export):
            w.setEnabled(not running)
        self.btn_cancel.setText("Cancelar" if running else "Fechar")

    def start_export(self) -> None:
        if self.worker is not None:
            return
        dest = Path(self.path.text()).expanduser()
        if not dest.parent.is_dir():
            QMessageBox.warning(self, "Exportar", "A pasta escolhida não existe.")
            return
        self.result_path = None
        self.bar.setValue(0)
        self.status.setText("Exportando…")
        self._set_running(True)
        self.worker = ExportWorker(self.kind(), self.workspace, dest, self.options(), self)
        self.worker.progress.connect(lambda v: self.bar.setValue(round(v * 1000)))
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.cancelled.connect(self._cancelled)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _worker_finished(self) -> None:
        self.worker = None
        self._set_running(False)

    def _done(self, path: str) -> None:
        self.result_path = Path(path)
        self.bar.setValue(1000)
        size = self.result_path.stat().st_size / (1024 * 1024)
        self.status.setText(f"Pronto: {self.result_path.name} ({size:.1f} MB)")
        answer = QMessageBox.question(self, "Exportação concluída",
                                      f"{self.result_path.name} foi salvo ({size:.1f} MB).\nAbrir o arquivo agora?")
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result_path)))

    def _failed(self, message: str) -> None:
        self.status.setText("Falhou.")
        QMessageBox.critical(self, "Erro ao exportar", message)

    def _cancelled(self) -> None:
        self.bar.setValue(0)
        self.status.setText("Exportação cancelada.")

    def _cancel_or_close(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.status.setText("Cancelando…")
        else:
            self.reject()

    def reject(self) -> None:
        # Fechar (Esc ou X) no meio da exportação cancela e espera a thread terminar.
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait(15000)
        super().reject()
