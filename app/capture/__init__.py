"""Escolhe os adaptadores de captura do sistema atual."""

from __future__ import annotations

import sys

from app.capture.base import (
    ClickEvent, ElementInfo, ElementInspector, InputHook, KeyEvent, KeyHook, NullInspector, ScreenGrabber,
)
from app.capture.coords import Monitor

__all__ = [
    "ClickEvent", "ElementInfo", "ElementInspector", "InputHook", "KeyEvent", "KeyHook", "NullInspector",
    "ScreenGrabber", "Monitor", "create_element_inspector",
    "create_input_hook", "create_key_hook", "create_screen_grabber", "enable_dpi_awareness",
    "exclude_from_capture", "window_rect", "double_click_settings",
    "elevated_window_in_use", "foreground_is_own_process", "is_admin", "restart_as_admin",
]

IS_WINDOWS = sys.platform == "win32"


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise NotImplementedError("Nesta fase só há adaptador de captura para Windows.")


def create_input_hook() -> InputHook:
    _require_windows()
    from app.capture.windows import PynputInputHook

    return PynputInputHook()


def create_key_hook() -> KeyHook:
    _require_windows()
    from app.capture.windows import PynputKeyHook

    return PynputKeyHook()


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


def elevated_window_in_use():
    """Janela de administrador em uso (cujos cliques não chegam até nós), ou None."""
    if not IS_WINDOWS:
        return None
    from app.capture.elevacao import elevated_window_in_use as impl

    return impl()


def foreground_is_own_process() -> bool:
    if not IS_WINDOWS:
        return False
    from app.capture.elevacao import foreground_is_own_process as impl

    return impl()


def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    from app.capture.elevacao import is_admin as impl

    return impl()


def restart_as_admin() -> bool:
    if not IS_WINDOWS:
        return False
    from app.capture.elevacao import restart_as_admin as impl

    return impl()
