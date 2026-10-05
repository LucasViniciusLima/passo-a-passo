"""Janela simples de revisão: miniaturas à esquerda, captura anotada e texto do passo."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from app.project.storage import ProjectWorkspace
from app.render.annotate import annotate_step
from app.render.preview import export_step_images
from app.ui.appearance_panel import AppearancePanel
from app.ui.export_dialog import ExportDialog
from app.ui.qt_image import pil_to_qpixmap

THUMB_SIZE = QSize(200, 120)


def ask_save_path(parent: QWidget | None, suggested: str = "tutorial.passo") -> Path | None:
    start = str(Path.home() / "Documents" / suggested)
    path, _ = QFileDialog.getSaveFileName(parent, "Salvar tutorial", start, "Projeto Passo a Passo (*.passo)")
    if not path:
        return None
    path = Path(path)
    return path if path.suffix.lower() == ".passo" else path.with_suffix(".passo")


class _ImageView(QLabel):
    """Mostra o pixmap inteiro, redimensionado para caber mantendo a proporção."""

    def __init__(self) -> None:
        super().__init__()
        self._pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 200)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setStyleSheet("background: #ECEFF1;")

    def set_image(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._pixmap is None:
            self.clear()
            return
        self.setPixmap(self._pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))


class ReviewWindow(QMainWindow):
    def __init__(self, workspace: ProjectWorkspace, saved_path: Path | None = None) -> None:
        super().__init__()
        self.workspace = workspace
        self.project = workspace.project
        self.saved_path = saved_path
        self.dirty = saved_path is None
        self._cache: dict[str, QPixmap] = {}

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.TopToBottom)
        self.list.setWrapping(False)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setWordWrap(True)
        self.list.setIconSize(THUMB_SIZE)
        self.list.setGridSize(QSize(THUMB_SIZE.width() + 20, THUMB_SIZE.height() + 50))
        self.list.setFixedWidth(THUMB_SIZE.width() + 44)
        self.view = _ImageView()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Texto do passo")
        self.btn_save = QPushButton("Salvar")
        self.btn_images = QPushButton("Salvar imagens")
        self.btn_images.setToolTip("Grava um PNG por passo, com o círculo e o texto")

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Texto:"))
        bottom.addWidget(self.text, 1)
        bottom.addWidget(self.btn_images)
        bottom.addWidget(self.btn_save)
        self.title = QLineEdit(self.project.title)
        self.title.setPlaceholderText("Título do tutorial")
        self.title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px;")
        self.btn_export = QPushButton("Exportar…")
        self.btn_export.setToolTip("PDF, GIF animado ou vídeo MP4")
        self.btn_export.setStyleSheet("background: #E53935; color: white; padding: 6px 16px; border-radius: 4px;")
        top = QHBoxLayout()
        top.addWidget(QLabel("Título:"))
        top.addWidget(self.title, 1)
        top.addWidget(self.btn_export)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.addLayout(top)
        center_layout.addWidget(self.view, 1)
        center_layout.addLayout(bottom)

        self.appearance = AppearancePanel(workspace)

        splitter = QSplitter()
        splitter.addWidget(self.list)
        splitter.addWidget(center)
        splitter.addWidget(self.appearance)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)
        self.resize(1400, 800)

        for step in self.project.steps:
            item = QListWidgetItem(QIcon(self._thumbnail(step)), step.text)
            self.list.addItem(item)

        self.list.currentRowChanged.connect(self._show_step)
        self.text.textEdited.connect(self._edit_text)
        self.btn_save.clicked.connect(self.save)
        self.btn_images.clicked.connect(self.save_images)
        self.btn_export.clicked.connect(self.open_export)
        self.title.textEdited.connect(self._edit_title)
        self.appearance.changed.connect(self._theme_changed)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save)
        self._update_title()
        if self.project.steps:
            self.list.setCurrentRow(0)

    def _annotated(self, index: int) -> QPixmap:
        step = self.project.steps[index]
        if step.id not in self._cache:
            with Image.open(self.workspace.root / step.image) as img:
                self._cache[step.id] = pil_to_qpixmap(annotate_step(img, step, self.project))
        return self._cache[step.id]

    def _thumbnail(self, step) -> QPixmap:
        index = self.project.steps.index(step)
        return self._annotated(index).scaled(
            THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )

    def _show_step(self, row: int) -> None:
        if row < 0:
            self.view.set_image(None)
            self.text.clear()
            return
        self.view.set_image(self._annotated(row))
        self.text.setText(self.project.steps[row].text)

    def _edit_text(self, value: str) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.project.steps[row].text = value
        self.list.item(row).setText(value)
        self.workspace.flush()
        self.dirty = True
        self._update_title()

    def _mark_dirty(self) -> None:
        self.workspace.flush()
        self.dirty = True
        self._update_title()

    def _edit_title(self, value: str) -> None:
        self.project.title = value.strip() or "Novo tutorial"
        self._mark_dirty()

    def _theme_changed(self) -> None:
        # Prévia ao vivo: refaz a captura atual e as miniaturas com o tema novo.
        self._cache.clear()
        for row, step in enumerate(self.project.steps):
            self.list.item(row).setIcon(QIcon(self._thumbnail(step)))
        self._show_step(self.list.currentRow())
        self._mark_dirty()

    def open_export(self) -> None:
        start = self.saved_path.parent if self.saved_path else None
        ExportDialog(self.workspace, start, self).exec()

    def _update_title(self) -> None:
        name = self.saved_path.name if self.saved_path else "não salvo"
        mark = " *" if self.dirty else ""
        self.setWindowTitle(f"Revisão — {name}{mark} — Passo a Passo")

    def save(self) -> bool:
        path = self.saved_path or ask_save_path(self)
        if path is None:
            return False
        try:
            self.workspace.save_to(path)
        except OSError as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))
            return False
        self.saved_path = path
        self.dirty = False
        self._update_title()
        return True

    def save_images(self) -> None:
        start = str(self.saved_path.parent if self.saved_path else Path.home() / "Documents")
        folder = QFileDialog.getExistingDirectory(self, "Pasta para as imagens", start)
        if not folder:
            return
        try:
            paths = export_step_images(self.project, self.workspace.root, folder)
        except OSError as exc:
            QMessageBox.critical(self, "Erro ao salvar imagens", str(exc))
            return
        QMessageBox.information(self, "Imagens salvas", f"{len(paths)} imagens salvas em:\n{folder}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def closeEvent(self, event) -> None:
        if self.dirty:
            answer = QMessageBox.question(
                self, "Salvar alterações?", "O tutorial tem alterações não salvas. Deseja salvar?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel or (
                answer == QMessageBox.StandardButton.Save and not self.save()
            ):
                event.ignore()
                return
        self.workspace.cleanup()
        event.accept()
