"""Exportadores: PDF (ReportLab), MP4 e GIF (FFmpeg). Todos só leem o projeto."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

Progress = Callable[[float], None]  # recebe de 0.0 a 1.0


class Cancelled(Exception):
    """A exportação foi cancelada pelo usuário."""


def check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


@dataclass
class PdfOptions:
    page_size: str = "A4"  # "A4" ou "Carta"
    steps_per_page: int = 1  # 1 ou 2
    orientation: str = "auto"  # "auto" (paisagem com 1 passo, retrato com 2), "retrato" ou "paisagem"
    jpeg_quality: int = 90
    font: str | None = None  # None = Segoe UI (ou Helvetica se não houver)
    compress: bool = True


@dataclass
class VideoOptions:
    height: int = 1080  # 1080 ou 720
    fps: int = 30
    seconds_per_step: float = 3.0
    transition: str = "esmaecer"  # "esmaecer", "deslizar" ou "zoom"
    transition_seconds: float = 0.5
    crf: int = 20  # qualidade do H.264 (menor = melhor)


@dataclass
class GifOptions:
    width: int = 960
    fps: int = 12
    seconds_per_step: float = 3.0
    transition: str = "esmaecer"
    transition_seconds: float = 0.5
    max_colors: int = 256


TRANSITIONS = {"esmaecer": "Esmaecer", "deslizar": "Deslizar", "zoom": "Zoom"}
