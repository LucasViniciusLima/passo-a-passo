"""Painel "Aparência": logo, cores do tema e destaque do fundo, com prévia ao vivo."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.project.storage import ProjectWorkspace
from app.theme import LOGO_FORMATS, contrast_ratio, remove_logo, set_logo

COLORS = [
    ("highlight_color", "Destaque"),
    ("margin_color", "Margens"),
    ("page_background", "Fundo da página"),
    ("text_color", "Texto"),
]
SPOTLIGHT = [("janela", "Janela clicada nítida"), ("circulo", "Só em volta do clique"), ("desligado", "Sem desfoque")]
MIN_CONTRAST = 4.5


class AppearancePanel(QWidget):
    changed = Signal()

    def __init__(self, workspace: ProjectWorkspace, parent=None) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.theme = workspace.project.theme
        self.setMinimumWidth(230)

        logo_box = QGroupBox("Logo")
        self.logo_preview = QLabel("Nenhuma", alignment=Qt.AlignmentFlag.AlignCenter)
        self.logo_preview.setMinimumHeight(70)
        self.logo_preview.setStyleSheet("background: #FAFAFA; border: 1px dashed #B0BEC5;")
        self.btn_logo = QPushButton("Escolher…")
        self.btn_remove_logo = QPushButton("Remover")
        row = QHBoxLayout()
        row.addWidget(self.btn_logo)
        row.addWidget(self.btn_remove_logo)
        lv = QVBoxLayout(logo_box)
        lv.addWidget(self.logo_preview)
        lv.addLayout(row)

        colors_box = QGroupBox("Cores")
        form = QFormLayout(colors_box)
        self.color_buttons: dict[str, QPushButton] = {}
        for attr, label in COLORS:
            button = QPushButton()
            button.setFixedHeight(26)
            button.clicked.connect(lambda _=False, a=attr, lb=label: self._pick_color(a, lb))
            self.color_buttons[attr] = button
            form.addRow(label, button)
        self.contrast_warning = QLabel(wordWrap=True)
        self.contrast_warning.setStyleSheet("color: #E65100;")
        form.addRow(self.contrast_warning)

        spot_box = QGroupBox("Destaque do fundo")
        self.spotlight = QComboBox()
        for key, label in SPOTLIGHT:
            self.spotlight.addItem(label, key)
        sv = QVBoxLayout(spot_box)
        sv.addWidget(self.spotlight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(logo_box)
        layout.addWidget(colors_box)
        layout.addWidget(spot_box)
        layout.addStretch(1)

        self.btn_logo.clicked.connect(self._choose_logo)
        self.btn_remove_logo.clicked.connect(self._remove_logo)
        self.spotlight.currentIndexChanged.connect(self._spotlight_changed)
        self.refresh()

    def refresh(self) -> None:
        for attr, button in self.color_buttons.items():
            value = getattr(self.theme, attr)
            fg = "#000000" if QColor(value).lightness() > 140 else "#FFFFFF"
            button.setText(value.upper())
            button.setStyleSheet(f"background: {value}; color: {fg}; border: 1px solid #90A4AE; border-radius: 4px;")
        ratio = min(contrast_ratio(self.theme.text_color, self.theme.margin_color),
                    contrast_ratio(self.theme.text_color, self.theme.page_background))
        self.contrast_warning.setText(
            f"⚠ Pouco contraste entre o texto e o fundo ({ratio:.1f}:1). O ideal é 4,5:1 ou mais."
            if ratio < MIN_CONTRAST else ""
        )
        self.contrast_warning.setVisible(ratio < MIN_CONTRAST)
        index = self.spotlight.findData(self.theme.spotlight.mode)
        self.spotlight.blockSignals(True)
        self.spotlight.setCurrentIndex(max(index, 0))
        self.spotlight.blockSignals(False)
        logo = self.workspace.root / self.theme.logo if self.theme.logo else None
        if logo is not None and logo.is_file():
            pix = QPixmap(str(logo)).scaled(200, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            self.logo_preview.setPixmap(pix)
            self.btn_logo.setText("Substituir…")
            self.btn_remove_logo.setEnabled(True)
        else:
            self.logo_preview.clear()
            self.logo_preview.setText("Nenhuma")
            self.btn_logo.setText("Escolher…")
            self.btn_remove_logo.setEnabled(False)

    def set_color(self, attr: str, value: str) -> None:
        setattr(self.theme, attr, value.upper())
        self._apply()

    def _apply(self) -> None:
        self.workspace.flush()
        self.refresh()
        self.changed.emit()

    def _pick_color(self, attr: str, label: str) -> None:
        color = QColorDialog.getColor(QColor(getattr(self.theme, attr)), self, f"Cor: {label}")
        if color.isValid():
            self.set_color(attr, color.name())

    def _spotlight_changed(self) -> None:
        self.theme.spotlight.mode = self.spotlight.currentData()
        self._apply()

    def _choose_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Escolher logo", "", LOGO_FORMATS)
        if not path:
            return
        try:
            set_logo(self.workspace, path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Logo", f"Não foi possível usar esta imagem:\n{exc}")
            return
        self._apply()

    def _remove_logo(self) -> None:
        remove_logo(self.workspace)
        self._apply()
