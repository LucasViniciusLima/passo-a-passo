"""Janela simples de revisão: miniaturas à esquerda, captura anotada e texto do passo."""

from __future__ import annotations

import html
import re
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QSizePolicy, QSpinBox, QSplitter, QStyle, QStyledItemDelegate,
    QToolButton, QVBoxLayout, QWidget,
)

from app import settings
from app.project.model import Project, renumber_steps
from app.project.naming import DEFAULT_TITLE, auto_title, safe_filename, unique_path
from app.project.storage import ProjectWorkspace
from app.render.annotate import annotate_step
from app.render.preview import export_step_images
from app.ui.appearance_panel import AppearancePanel
from app.ui.export_dialog import ExportDialog
from app.ui.qt_image import pil_to_qpixmap

THUMB_SIZE = QSize(200, 120)
GRID_SIZE = QSize(THUMB_SIZE.width() + 20, THUMB_SIZE.height() + 50)
SELECTED_BORDER = 3  # px, na cor de destaque do tema


def ask_save_path(parent: QWidget | None, project: Project | None = None) -> Path | None:
    """Pergunta onde salvar, já sugerindo um nome que não sobrescreve nada.

    Tutorial novo (título padrão) ganha o nome automático, que vira também o título.
    """
    folder = settings.last_dir("salvar")
    stem = "tutorial"
    if project is not None:
        if project.title.strip() in ("", DEFAULT_TITLE):
            project.title = auto_title(project)
        stem = safe_filename(project.title)
    start = str(unique_path(folder, stem, ".passo"))
    path, _ = QFileDialog.getSaveFileName(parent, "Salvar tutorial", start, "Projeto Passo a Passo (*.passo)")
    if not path:
        return None
    path = Path(path)
    settings.remember_dir("salvar", path.parent)
    return path if path.suffix.lower() == ".passo" else path.with_suffix(".passo")


_NUMERO = re.compile(r"^(Passo \d+:)(.*)$", re.DOTALL)


def item_html(text: str, selected: bool) -> str:
    """Texto da miniatura; na selecionada, o "Passo N:" vai em negrito."""
    if not selected:
        return html.escape(text)
    match = _NUMERO.match(text)
    if match is None:
        return f"<b>{html.escape(text)}</b>"
    return f"<b>{html.escape(match.group(1))}</b>{html.escape(match.group(2))}"


class ThumbnailDelegate(QStyledItemDelegate):
    """Selecionada: contorno na cor de destaque e número em negrito, com ou sem foco na lista."""

    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self.color = color

    def sizeHint(self, option, index) -> QSize:
        return QSize(GRID_SIZE.width() - 4, GRID_SIZE.height() - 4)

    def paint(self, painter: QPainter, option, index) -> None:
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect.adjusted(1, 1, -1, -1)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if selected:
            half = SELECTED_BORDER / 2
            painter.setPen(QPen(QColor(self.color), SELECTED_BORDER))
            painter.setBrush(Qt.BrushStyle.NoBrush)  # só o contorno; fundo e fonte seguem o tema do sistema
            painter.drawRoundedRect(QRectF(rect).adjusted(half, half, -half, -half), 6, 6)

        top = rect.top() + SELECTED_BORDER + 3
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            pixmap = icon.pixmap(THUMB_SIZE)
            size = pixmap.deviceIndependentSize().toSize()
            painter.drawPixmap(rect.center().x() - size.width() // 2, top, size.width(), size.height(), pixmap)
            top += THUMB_SIZE.height() + 2

        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        color = option.palette.text().color().name()
        doc.setHtml(f'<div align="center" style="color: {color}">{item_html(index.data() or "", selected)}</div>')
        doc.setTextWidth(rect.width() - 2 * SELECTED_BORDER - 4)
        painter.translate(rect.left() + SELECTED_BORDER + 2, top)
        doc.drawContents(painter, QRectF(0, 0, doc.textWidth(), rect.bottom() - top - SELECTED_BORDER))
        painter.restore()


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
        # Cada exclusão ou mudança de ordem guarda os passos, os textos, a linha de antes
        # e a mensagem do desfazer, para o Ctrl+Z.
        self._undo: list[tuple[list, dict[str, str], int, str]] = []

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.TopToBottom)
        self.list.setWrapping(False)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setWordWrap(True)
        self.list.setIconSize(THUMB_SIZE)
        self.list.setGridSize(GRID_SIZE)
        self.list.setFixedWidth(THUMB_SIZE.width() + 44)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumbs = ThumbnailDelegate(self.project.theme.highlight_color, self.list)
        self.list.setItemDelegate(self.thumbs)
        self.view = _ImageView()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Texto do passo")
        self.btn_save = QPushButton("Salvar")
        self.btn_images = QPushButton("Salvar imagens")
        self.btn_images.setToolTip("Grava um PNG por passo, com o círculo e o texto")
        self.btn_delete = QPushButton("Excluir passo")
        self.btn_delete.setToolTip("Exclui os passos selecionados (Delete). Ctrl+Z desfaz.")

        # Ordem dos passos: setas e posição digitada (de 1 até o total, validada pela caixa).
        self.btn_up = QToolButton(text="▲")
        self.btn_up.setToolTip("Subir o passo (Ctrl+↑)")
        self.btn_down = QToolButton(text="▼")
        self.btn_down.setToolTip("Descer o passo (Ctrl+↓)")
        self.position = QSpinBox()
        self.position.setToolTip("Digite a nova posição do passo e tecle Enter")
        self.position.setKeyboardTracking(False)  # só move ao confirmar, não a cada dígito
        self.position.setMinimumWidth(52)
        self.position_total = QLabel()
        order = QHBoxLayout()
        order.setContentsMargins(0, 0, 0, 0)
        order.addWidget(self.btn_up)
        order.addWidget(self.btn_down)
        order.addStretch(1)
        order.addWidget(QLabel("Posição:"))
        order.addWidget(self.position)
        order.addWidget(self.position_total)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.list, 1)
        left_layout.addLayout(order)
        left.setFixedWidth(THUMB_SIZE.width() + 44)

        bottom = QHBoxLayout()
        bottom.addWidget(self.btn_delete)
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
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(self.appearance)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)
        self.resize(1400, 800)

        self._fill_list()

        self.list.currentRowChanged.connect(self._show_step)
        self.list.itemSelectionChanged.connect(self._update_delete_button)
        self.list.currentRowChanged.connect(lambda _row: self._update_order_controls())
        self.btn_up.clicked.connect(lambda: self.move_current(-1))
        self.btn_down.clicked.connect(lambda: self.move_current(+1))
        self.position.valueChanged.connect(self._position_entered)
        self.text.textEdited.connect(self._edit_text)
        self.btn_delete.clicked.connect(lambda: self.delete_selected())
        self.btn_save.clicked.connect(self.save)
        self.btn_images.clicked.connect(self.save_images)
        self.btn_export.clicked.connect(self.open_export)
        self.title.textEdited.connect(self._edit_title)
        self.appearance.changed.connect(self._theme_changed)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save)
        # Delete só na lista: no campo de texto a tecla continua apagando letras.
        QShortcut(QKeySequence.StandardKey.Delete, self.list, activated=lambda: self.delete_selected(),
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        # Nos campos de texto o Ctrl+Z continua desfazendo a digitação (o campo trata antes).
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo_delete)
        # Ctrl+↑/↓ na lista move o passo (a lista usaria a tecla só para mudar o foco).
        self.list.installEventFilter(self)
        self._update_title()
        if self.project.steps:
            self.list.setCurrentRow(0)
        self._update_delete_button()
        self._update_order_controls()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.list and event.type() == QEvent.Type.KeyPress:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self.move_current(-1 if event.key() == Qt.Key.Key_Up else +1)
                return True
        return super().eventFilter(obj, event)

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

    def _fill_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for step in self.project.steps:
            self.list.addItem(QListWidgetItem(QIcon(self._thumbnail(step)), step.text))
        self.list.blockSignals(False)

    def _select(self, row: int) -> None:
        self.list.clearSelection()
        if self.project.steps:
            self.list.setCurrentRow(max(0, min(row, len(self.project.steps) - 1)))
        self._show_step(self.list.currentRow())
        self._update_delete_button()
        self._update_order_controls()

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

    # --- excluir passos --------------------------------------------------

    def selected_rows(self) -> list[int]:
        rows = sorted({self.list.row(item) for item in self.list.selectedItems()})
        if not rows and self.list.currentRow() >= 0:
            rows = [self.list.currentRow()]
        return rows

    def _update_delete_button(self) -> None:
        n = len(self.selected_rows())
        self.btn_delete.setText("Excluir passo" if n <= 1 else f"Excluir {n} passos")
        self.btn_delete.setEnabled(n > 0)

    def delete_selected(self, confirm: bool = True) -> bool:
        rows = self.selected_rows()
        if not rows:
            return False
        if len(rows) >= len(self.project.steps):
            QMessageBox.information(self, "Excluir passo", "O tutorial precisa ter pelo menos um passo.")
            return False
        if confirm:
            question = (f"Excluir o passo {rows[0] + 1}?" if len(rows) == 1
                        else f"Excluir os {len(rows)} passos selecionados?")
            answer = QMessageBox.question(
                self, "Excluir passo", f"{question}\nVocê pode desfazer com Ctrl+Z.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        steps = self.project.steps
        self._push_undo("Exclusão desfeita")
        # As imagens ficam na pasta temporária (para o Ctrl+Z); o .passo e as exportações
        # só leem os passos restantes.
        removed = set(rows)
        steps[:] = [s for i, s in enumerate(steps) if i not in removed]
        renumber_steps(steps)
        self._fill_list()
        self._select(rows[0])
        self._mark_dirty()
        n = len(rows)
        done = "1 passo excluído" if n == 1 else f"{n} passos excluídos"
        self.statusBar().showMessage(f"{done} — Ctrl+Z para desfazer", 8000)
        return True

    def _push_undo(self, message: str) -> None:
        steps = self.project.steps
        self._undo.append((list(steps), {s.id: s.text for s in steps}, self.list.currentRow(), message))

    def undo_delete(self) -> bool:
        """Ctrl+Z: desfaz a última exclusão ou mudança de ordem."""
        if not self._undo:
            return False
        steps, texts, row, message = self._undo.pop()
        self.project.steps[:] = steps
        for step in steps:
            step.text = texts.get(step.id, step.text)
        self._fill_list()
        self._select(row)
        self._mark_dirty()
        self.statusBar().showMessage(message, 5000)
        return True

    # --- ordem dos passos ------------------------------------------------

    def _update_order_controls(self) -> None:
        total = len(self.project.steps)
        row = self.list.currentRow()
        self.btn_up.setEnabled(0 < row)
        self.btn_down.setEnabled(0 <= row < total - 1)
        self.position.blockSignals(True)
        self.position.setRange(1, max(total, 1))
        self.position.setValue(row + 1 if row >= 0 else 1)
        self.position.setEnabled(row >= 0 and total > 1)
        self.position.blockSignals(False)
        self.position_total.setText(f"de {total}")

    def _position_entered(self, value: int) -> None:
        if not self.move_step(self.list.currentRow(), value - 1):
            self._update_order_controls()  # posição inválida: volta a mostrar a atual

    def move_current(self, delta: int) -> bool:
        row = self.list.currentRow()
        return self.move_step(row, row + delta)

    def move_step(self, row: int, new_row: int) -> bool:
        """Leva o passo da linha row para new_row (0 = primeiro) e renumera os textos."""
        steps = self.project.steps
        if not (0 <= row < len(steps)) or not (0 <= new_row < len(steps)) or row == new_row:
            return False
        self._push_undo("Mudança de ordem desfeita")
        steps.insert(new_row, steps.pop(row))
        renumber_steps(steps)
        self._fill_list()
        self._select(new_row)
        self._mark_dirty()
        self.statusBar().showMessage(f"Passo movido para a posição {new_row + 1} — Ctrl+Z para desfazer", 6000)
        return True

    # --- edição ----------------------------------------------------------

    def _mark_dirty(self) -> None:
        self.workspace.flush()
        self.dirty = True
        self._update_title()

    def _edit_title(self, value: str) -> None:
        self.project.title = value.strip() or DEFAULT_TITLE
        self._mark_dirty()

    def _theme_changed(self) -> None:
        # Prévia ao vivo: refaz a captura atual e as miniaturas com o tema novo.
        self.thumbs.color = self.project.theme.highlight_color
        self._cache.clear()
        for row, step in enumerate(self.project.steps):
            self.list.item(row).setIcon(QIcon(self._thumbnail(step)))
        self._show_step(self.list.currentRow())
        self._mark_dirty()

    def open_export(self) -> None:
        ExportDialog(self.workspace, None, self).exec()

    def _update_title(self) -> None:
        name = self.saved_path.name if self.saved_path else "não salvo"
        mark = " *" if self.dirty else ""
        self.setWindowTitle(f"Revisão — {name}{mark} — Passo a Passo")

    def save(self) -> bool:
        path = self.saved_path or ask_save_path(self, self.project)
        if self.title.text() != self.project.title:
            self.title.setText(self.project.title)  # o nome automático vira o título
            self.workspace.flush()
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
        start = str(settings.last_dir("imagens"))
        folder = QFileDialog.getExistingDirectory(self, "Pasta para as imagens", start)
        if not folder:
            return
        settings.remember_dir("imagens", folder)
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
