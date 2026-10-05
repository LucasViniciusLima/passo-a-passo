"""Atalhos globais de teclado (pynput). Os sinais chegam na thread da interface."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from pynput import keyboard

TOGGLE_PAUSE = "<ctrl>+<shift>+<f9>"
FINISH = "<ctrl>+<shift>+<f10>"


class GlobalHotkeys(QObject):
    togglePause = Signal()
    finish = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = keyboard.GlobalHotKeys(
            {TOGGLE_PAUSE: self.togglePause.emit, FINISH: self.finish.emit}
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
