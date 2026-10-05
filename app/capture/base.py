"""Interfaces da camada de captura; cada sistema fornece seus adaptadores."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image

from app.capture.coords import Monitor


@dataclass(frozen=True)
class ClickEvent:
    """Botão pressionado, em pixels físicos da área de trabalho virtual."""

    x: int
    y: int
    button: str  # "left", "right" ou "middle"
    time: float  # time.monotonic() no momento do clique


class InputHook(ABC):
    """Escuta cliques globais. O callback roda na thread do hook e deve ser rápido."""

    @abstractmethod
    def start(self, on_click: Callable[[ClickEvent], None]) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...


@dataclass(frozen=True)
class ElementInfo:
    """O que estava sob o ponto clicado."""

    exe_path: str | None = None
    window_title: str | None = None
    root_class: str | None = None  # classe da janela principal
    control_class: str | None = None  # classe da janela filha sob o ponto
    element_name: str | None = None  # nome do botão ou campo (UI Automation)
    element_type: str | None = None  # tipo em pt-BR: "botão", "campo", "aba"...
    automation_id: str | None = None
    # Retângulo da janela clicada em pixels físicos da área de trabalho (esq, topo, dir, baixo).
    window_rect: tuple[int, int, int, int] | None = None


class ElementInspector(ABC):
    """Descobre a janela e o elemento sob um ponto da tela.

    A versão Win32 só conhece janelas; uma versão com UI Automation poderá
    preencher element_name e element_type com o nome do botão ou campo.
    """

    @abstractmethod
    def inspect(self, x: int, y: int) -> ElementInfo: ...


class NullInspector(ElementInspector):
    def inspect(self, x: int, y: int) -> ElementInfo:
        return ElementInfo()


class ScreenGrabber(ABC):
    """Tira capturas de tela por monitor."""

    @abstractmethod
    def monitors(self) -> list[Monitor]: ...

    @abstractmethod
    def grab(self, monitor: Monitor) -> Image.Image: ...

    def close(self) -> None:
        pass
