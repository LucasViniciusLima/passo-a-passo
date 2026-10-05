"""Máquina de estados da gravação."""

from __future__ import annotations

from enum import Enum


class RecorderState(Enum):
    IDLE = "Ocioso"
    RECORDING = "Gravando"
    PAUSED = "Pausado"
    FINISHED = "Finalizado"


_ALLOWED = {
    RecorderState.IDLE: {RecorderState.RECORDING},
    RecorderState.RECORDING: {RecorderState.PAUSED, RecorderState.FINISHED},
    RecorderState.PAUSED: {RecorderState.RECORDING, RecorderState.FINISHED},
    RecorderState.FINISHED: set(),
}


class InvalidTransition(Exception):
    pass


class StateMachine:
    """Guarda o estado atual e o tempo gravado, descontando as pausas."""

    def __init__(self) -> None:
        self.state = RecorderState.IDLE
        self._elapsed = 0.0
        self._since: float | None = None

    def can(self, new: RecorderState) -> bool:
        return new in _ALLOWED[self.state]

    def go(self, new: RecorderState, now: float) -> None:
        if not self.can(new):
            raise InvalidTransition(f"{self.state.value} -> {new.value}")
        if self.state is RecorderState.RECORDING and self._since is not None:
            self._elapsed += now - self._since
            self._since = None
        if new is RecorderState.RECORDING:
            self._since = now
        self.state = new

    def elapsed(self, now: float) -> float:
        running = now - self._since if self._since is not None else 0.0
        return self._elapsed + running

    @property
    def accepts_clicks(self) -> bool:
        return self.state is RecorderState.RECORDING
