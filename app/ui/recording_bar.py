"""Barra flutuante de gravação: pequena, sem borda, sempre no topo e arrastável."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app import capture, settings
from app.recorder.controller import RecordingController
from app.recorder.state import RecorderState

COUNTDOWN_SECONDS = 3

_STYLE = """
QWidget#bar { background: #263238; border-radius: 8px; }
QLabel { color: #ECEFF1; font-size: 13px; }
QLabel#status { color: #FF8A80; font-weight: bold; min-width: 90px; }
QPushButton { background: #37474F; color: white; border: none; border-radius: 5px; padding: 6px 12px; }
QPushButton:hover { background: #455A64; }
QPushButton:disabled { color: #78909C; }
QPushButton#start { background: #E53935; }
QPushButton#start:hover { background: #EF5350; }
QPushButton#close, QPushButton#settings { background: transparent; padding: 4px 8px; }
QPushButton#settings { font-size: 15px; }
"""


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class RecordingBar(QWidget):
    openRequested = Signal()
    settingsRequested = Signal()

    def __init__(self, controller: RecordingController) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.controller = controller
        self.setWindowTitle("Passo a Passo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("bar")
        self.setStyleSheet(_STYLE)
        self._drag_offset: QPoint | None = None
        self._countdown = 0

        self.status = QLabel("Pronto", objectName="status")
        self.btn_start = QPushButton("● Iniciar", objectName="start")
        self.btn_open = QPushButton("Abrir tutorial")
        self.btn_pause = QPushButton("Pausar")
        self.btn_finish = QPushButton("Finalizar")
        self.steps_label = QLabel("0 passos")
        self.time_label = QLabel("00:00")
        self.btn_settings = QPushButton("⚙", objectName="settings")
        self.update_settings_tooltip()
        self.btn_close = QPushButton("✕", objectName="close")
        self.btn_close.setToolTip("Fechar")
        self.btn_pause.setToolTip("Pausar ou retomar (Ctrl+Shift+F9)")
        self.btn_finish.setToolTip("Finalizar (Ctrl+Shift+F10)")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 6, 6)
        layout.setSpacing(8)
        for w in (self.status, self.btn_start, self.btn_open, self.btn_pause, self.btn_finish,
                  self.steps_label, self.time_label, self.btn_settings, self.btn_close):
            layout.addWidget(w)

        self.btn_start.clicked.connect(self._begin_countdown)
        self.btn_pause.clicked.connect(controller.toggle_pause)
        self.btn_finish.clicked.connect(controller.finish)
        self.btn_close.clicked.connect(self.close)
        self.btn_open.clicked.connect(self.openRequested)
        self.btn_settings.clicked.connect(self.settingsRequested)
        controller.stateChanged.connect(self._on_state)
        controller.stepCountChanged.connect(self._on_steps)

        self._clock = QTimer(self, interval=250)
        self._clock.timeout.connect(self._tick)
        self._countdown_timer = QTimer(self, interval=1000)
        self._countdown_timer.timeout.connect(self._countdown_step)
        self._on_state(RecorderState.IDLE)

    def update_settings_tooltip(self) -> None:
        self.btn_settings.setToolTip(f"Pasta padrão dos tutoriais:\n{settings.default_dir()}")

    # --- estados ---------------------------------------------------------

    def _on_state(self, state: RecorderState) -> None:
        idle = state is RecorderState.IDLE
        self.btn_start.setVisible(idle)
        self.btn_open.setVisible(idle)
        self.btn_pause.setVisible(not idle)
        self.btn_finish.setVisible(not idle)
        self.btn_close.setVisible(idle)
        self.btn_settings.setVisible(idle)
        self.btn_pause.setText("Retomar" if state is RecorderState.PAUSED else "Pausar")
        self.status.setText(state.value if not idle else "Pronto")
        if state in (RecorderState.RECORDING, RecorderState.PAUSED):
            self._clock.start()
        else:
            self._clock.stop()
        self.adjustSize()
        self._update_ignore_rect()

    def _on_steps(self, count: int) -> None:
        self.steps_label.setText("1 passo" if count == 1 else f"{count} passos")

    def _tick(self) -> None:
        self.time_label.setText(format_elapsed(self.controller.elapsed()))

    def _begin_countdown(self) -> None:
        self._countdown = COUNTDOWN_SECONDS
        self.btn_start.setEnabled(False)
        self.btn_open.setEnabled(False)
        self.btn_settings.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.status.setText(f"Gravando em {self._countdown}…")
        self._countdown_timer.start()

    def _countdown_step(self) -> None:
        self._countdown -= 1
        if self._countdown > 0:
            self.status.setText(f"Gravando em {self._countdown}…")
            return
        self._countdown_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.btn_settings.setEnabled(True)
        self.btn_close.setEnabled(True)
        self._update_ignore_rect()
        self.controller.start()

    # --- janela ----------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        capture.exclude_from_capture(int(self.winId()))
        self._update_ignore_rect()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._update_ignore_rect()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_ignore_rect()

    def _update_ignore_rect(self) -> None:
        if self.isVisible():
            self.controller.set_ignore_rect(capture.window_rect(int(self.winId())))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
