"""Controlador da gravação: liga hook, worker, atalhos e máquina de estados."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal

from app import capture
from app.capture.base import ClickEvent
from app.capture.coords import rect_contains
from app.project.storage import ProjectWorkspace
from app.recorder.hotkeys import GlobalHotkeys
from app.recorder.state import RecorderState, StateMachine
from app.recorder.worker import CaptureWorker


class RecordingController(QObject):
    stateChanged = Signal(object)  # RecorderState
    stepCountChanged = Signal(int)
    finished = Signal(object)  # ProjectWorkspace
    error = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.machine = StateMachine()
        self.workspace: ProjectWorkspace | None = None
        self._hook = None
        self._worker: CaptureWorker | None = None
        self._ignore_rect: tuple[int, int, int, int] | None = None
        self.hotkeys = GlobalHotkeys(self)
        self.hotkeys.togglePause.connect(self.toggle_pause)
        self.hotkeys.finish.connect(self.finish)

    @property
    def state(self) -> RecorderState:
        return self.machine.state

    def elapsed(self) -> float:
        return self.machine.elapsed(time.monotonic())

    def set_ignore_rect(self, rect: tuple[int, int, int, int] | None) -> None:
        """Retângulo (pixels físicos) da barra; cliques dentro dele são ignorados."""
        self._ignore_rect = rect

    def start(self) -> None:
        if self.state is not RecorderState.IDLE:
            return
        now = time.monotonic()
        self.workspace = ProjectWorkspace()
        self._worker = CaptureWorker(
            self.workspace,
            capture.create_screen_grabber(),
            t0=now,
            double_click=capture.double_click_settings(),
            inspector=capture.create_element_inspector(),
        )
        self._worker.stepAdded.connect(lambda _s: self.stepCountChanged.emit(len(self.workspace.project.steps)))
        self._worker.failed.connect(self.error)
        self._worker.start()
        self._set_state(RecorderState.RECORDING, now)
        self._hook = capture.create_input_hook()
        self._hook.start(self._on_click)
        self.hotkeys.start()

    def pause(self) -> None:
        if self.state is RecorderState.RECORDING:
            self._set_state(RecorderState.PAUSED)

    def resume(self) -> None:
        if self.state is RecorderState.PAUSED:
            self._set_state(RecorderState.RECORDING)

    def toggle_pause(self) -> None:
        if self.state is RecorderState.RECORDING:
            self.pause()
        elif self.state is RecorderState.PAUSED:
            self.resume()

    def finish(self) -> None:
        if not self.machine.can(RecorderState.FINISHED):
            return
        self._set_state(RecorderState.FINISHED)
        self.hotkeys.stop()
        if self._hook is not None:
            self._hook.stop()
            self._hook = None
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait()
            self._worker = None
        self.finished.emit(self.workspace)

    def _set_state(self, new: RecorderState, now: float | None = None) -> None:
        self.machine.go(new, time.monotonic() if now is None else now)
        self.stateChanged.emit(new)

    def _on_click(self, event: ClickEvent) -> None:
        # Roda na thread do hook: só filtra e enfileira. Em Pausado o evento é descartado.
        if not self.machine.accepts_clicks or self._worker is None:
            return
        if rect_contains(self._ignore_rect, event.x, event.y):
            return
        self._worker.submit(event)
