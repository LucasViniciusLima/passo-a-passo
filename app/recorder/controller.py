"""Controlador da gravação: liga hook, worker, atalhos e máquina de estados."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal

from app import capture, settings
from app.capture.base import ClickEvent, KeyEvent
from app.capture.coords import rect_contains
from app.project.storage import ProjectWorkspace
from app.recorder.hotkeys import GlobalHotkeys
from app.recorder.state import RecorderState, StateMachine
from app.recorder.worker import CaptureWorker
from app.registro import registrar
from app.theme import apply_brand_defaults


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
        self._keys = None
        self._worker: CaptureWorker | None = None
        self._ignore_rect: tuple[int, int, int, int] | None = None
        # Motivos de descarte já registrados nesta gravação (um registro por motivo, não por clique).
        self._logged: set[str] = set()
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
        apply_brand_defaults(self.workspace)
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
        self._logged = set()
        self._hook = capture.create_input_hook()
        self._hook.start(self._on_click)
        if settings.keyboard_steps():
            try:
                self._keys = capture.create_key_hook()
                self._keys.start(self._on_key)
            except Exception as exc:  # sem passos de teclado, a gravação de cliques segue
                self._keys = None
                registrar(f"Passos de teclado indisponíveis: {exc}")
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
        self._stop_capture()
        self.finished.emit(self.workspace)

    def abort(self) -> None:
        """Para tudo e descarta a gravação (ao reiniciar como administrador)."""
        self._stop_capture()
        if self.workspace is not None:
            self.workspace.cleanup()
            self.workspace = None

    def _stop_capture(self) -> None:
        self.hotkeys.stop()
        if self._hook is not None:
            self._hook.stop()
            self._hook = None
        if self._keys is not None:
            self._keys.stop()
            self._keys = None
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait()
            self._worker = None

    def _set_state(self, new: RecorderState, now: float | None = None) -> None:
        self.machine.go(new, time.monotonic() if now is None else now)
        self.stateChanged.emit(new)

    def _discard(self, reason: str) -> None:
        if reason not in self._logged:
            self._logged.add(reason)
            registrar(f"Evento descartado: {reason}")

    def _on_click(self, event: ClickEvent) -> None:
        # Roda na thread do hook: só filtra e enfileira. Em Pausado o evento é descartado.
        if self._worker is None:
            return
        if not self.machine.accepts_clicks:
            self._discard("clique durante a pausa")
            return
        if rect_contains(self._ignore_rect, event.x, event.y):
            return  # clique na própria barra
        self._worker.submit(event)

    def _on_key(self, event: KeyEvent) -> None:
        # Só chegam Tab e Enter sem Ctrl, Alt ou Win; nada do que é digitado passa por aqui.
        if self._worker is None:
            return
        if not self.machine.accepts_clicks:
            self._discard(f"{event.key} durante a pausa")
            return
        if capture.foreground_is_own_process():
            return  # tecla na barra ou em outra janela do próprio app
        self._worker.submit(event)

    def check_elevated(self):
        """Janela de administrador em uso durante a gravação (seus cliques não chegam), ou None."""
        try:
            window = capture.elevated_window_in_use()
        except Exception as exc:
            self._discard(f"verificação de janelas de administrador falhou: {exc}")
            return None
        if window is not None:
            self._discard(
                f"cliques e teclas em {window.exe_path or window.name} não chegam ao Passo a Passo: "
                "o programa roda como administrador e o Windows bloqueia (UIPI). "
                "Abra o Passo a Passo como administrador para gravá-lo."
            )
        return window
