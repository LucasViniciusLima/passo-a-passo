"""Escolhe os adaptadores de captura do sistema atual."""

from __future__ import annotations

import sys

from app.capture.base import (
    ClickEvent, ElementInfo, ElementInspector, InputHook, NullInspector, ScreenGrabber,
)
from app.capture.coords import Monitor

__all__ = [
    "ClickEvent", "ElementInfo", "ElementInspector", "InputHook", "NullInspector",
    "ScreenGrabber", "Monitor", "create_element_inspector",
    "create_input_hook", "create_screen_grabber", "enable_dpi_awareness",
    "exclude_from_capture", "window_rect", "double_click_settings",
]

IS_WINDOWS = sys.platform == "win32"


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise NotImplementedError("Nesta fase só há adaptador de captura para Windows.")


def create_input_hook() -> InputHook:
    _require_windows()
    from app.capture.windows import PynputInputHook

    return PynputInputHook()


def create_element_inspector() -> ElementInspector:
    if not IS_WINDOWS:
        return NullInspector()
    from app.capture.windows import Win32ElementInspector

    win32 = Win32ElementInspector()
    try:
        from app.capture.uia import UIAElementInspector
    except ImportError:
        return win32
    return UIAElementInspector(win32)


def create_screen_grabber() -> ScreenGrabber:
    _require_windows()
    from app.capture.windows import MssScreenGrabber

    return MssScreenGrabber()


def enable_dpi_awareness() -> bool:
    if not IS_WINDOWS:
        return False
    from app.capture.windows import enable_dpi_awareness as impl

    return impl()


def exclude_from_capture(hwnd: int) -> bool:
    if not IS_WINDOWS:
        return False
    from app.capture.windows import exclude_from_capture as impl

    return impl(hwnd)


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if not IS_WINDOWS:
        return None
    from app.capture.windows import window_rect as impl

    return impl(hwnd)


def double_click_settings() -> tuple[float, int]:
    if not IS_WINDOWS:
        return 0.5, 4
    from app.capture.windows import double_click_settings as impl

    return impl()
