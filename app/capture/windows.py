"""Adaptador Windows: pynput para cliques e mss para capturas."""

from __future__ import annotations

import ctypes
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

import mss
from PIL import Image
from pynput import mouse

from app.capture.base import ClickEvent, ElementInfo, ElementInspector, InputHook, ScreenGrabber
from app.capture.coords import Monitor

_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
_WDA_EXCLUDEFROMCAPTURE = 0x11
_MONITOR_DEFAULTTONEAREST = 2
_MDT_EFFECTIVE_DPI = 0
_SM_CXDOUBLECLK = 36


def enable_dpi_awareness() -> bool:
    """Declara DPI Per-Monitor V2. Precisa rodar antes de criar qualquer janela."""
    user32 = ctypes.windll.user32
    try:
        if user32.SetProcessDpiAwarenessContext(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return True
    except AttributeError:
        pass
    try:  # Windows 8.1 e versões antigas do 10
        return ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0
    except (AttributeError, OSError):
        return False


def exclude_from_capture(hwnd: int) -> bool:
    """Tira a janela das capturas de tela (Windows 10 2004 ou mais novo)."""
    return bool(ctypes.windll.user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), _WDA_EXCLUDEFROMCAPTURE))


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Retângulo da janela em pixels físicos (esquerda, topo, direita, baixo)."""
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def monitor_scale(x: int, y: int) -> float:
    """Escala do monitor que contém o ponto (1.0 = 100%)."""
    try:
        hmon = ctypes.windll.user32.MonitorFromPoint(wintypes.POINT(x, y), _MONITOR_DEFAULTTONEAREST)
        dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
        ok = ctypes.windll.shcore.GetDpiForMonitor(
            hmon, _MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        )
        return dpi_x.value / 96 if ok == 0 and dpi_x.value else 1.0
    except (AttributeError, OSError):
        return 1.0


def double_click_settings() -> tuple[float, int]:
    """Intervalo (s) e distância (px) de duplo clique configurados no Windows."""
    user32 = ctypes.windll.user32
    return user32.GetDoubleClickTime() / 1000, max(user32.GetSystemMetrics(_SM_CXDOUBLECLK) // 2, 2)


_GA_ROOT = 2
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _window_text(hwnd) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _process_path(hwnd) -> str | None:
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(handle)


_GA_ROOTOWNER = 3
_DWMWA_EXTENDED_FRAME_BOUNDS = 9
# Janelas que cobrem a tela toda: não há "janela principal" para destacar.
_FULL_SCREEN_CLASSES = {"Progman", "WorkerW"}


def _frame_rect(hwnd) -> tuple[int, int, int, int] | None:
    """Retângulo visível da janela (sem a sombra invisível do Windows 10/11)."""
    rect = wintypes.RECT()
    try:
        ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
        ) == 0
    except (AttributeError, OSError):
        ok = False
    if not ok and not ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return None
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def _union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


class Win32ElementInspector(ElementInspector):
    """Janela sob o ponto via user32: título, classe e executável do processo."""

    def __init__(self) -> None:
        user32 = ctypes.windll.user32
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        ctypes.windll.kernel32.OpenProcess.restype = wintypes.HANDLE

    def inspect(self, x: int, y: int) -> ElementInfo:
        user32 = ctypes.windll.user32
        child = user32.WindowFromPoint(wintypes.POINT(x, y))
        if not child:
            return ElementInfo()
        root = user32.GetAncestor(child, _GA_ROOT) or child
        root_class = _class_name(root) or None
        # Janela em destaque: a clicada mais a dona dela (ex.: "Salvar como" + Bloco de Notas).
        window_rect = None
        if root_class not in _FULL_SCREEN_CLASSES:
            owner = user32.GetAncestor(child, _GA_ROOTOWNER)
            window_rect = _frame_rect(root)
            if owner and owner != root and _class_name(owner) not in _FULL_SCREEN_CLASSES:
                window_rect = _union(window_rect, _frame_rect(owner))
        return ElementInfo(
            exe_path=_process_path(root),
            window_title=_window_text(root) or None,
            root_class=root_class,
            control_class=_class_name(child) or None,
            window_rect=window_rect,
        )


_BUTTONS = {mouse.Button.left: "left", mouse.Button.right: "right", mouse.Button.middle: "middle"}


class PynputInputHook(InputHook):
    """Hook global de mouse (WH_MOUSE_LL via pynput). Só reage ao botão pressionado."""

    def __init__(self) -> None:
        self._listener: mouse.Listener | None = None

    def start(self, on_click: Callable[[ClickEvent], None]) -> None:
        def handler(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
            if pressed:
                on_click(ClickEvent(int(x), int(y), _BUTTONS.get(button, "left"), time.monotonic()))

        self._listener = mouse.Listener(on_click=handler)
        self._listener.start()
        self._listener.wait()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


class MssScreenGrabber(ScreenGrabber):
    """Capturas com mss. Cada thread usa sua própria instância do mss."""

    def __init__(self) -> None:
        self._local = threading.local()

    def _sct(self) -> mss.MSS:
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = self._local.sct = mss.MSS()
        return sct

    def monitors(self) -> list[Monitor]:
        result = []
        for i, m in enumerate(self._sct().monitors[1:], start=1):
            scale = monitor_scale(m["left"] + m["width"] // 2, m["top"] + m["height"] // 2)
            result.append(Monitor(i, m["left"], m["top"], m["width"], m["height"], scale))
        return result

    def grab(self, monitor: Monitor) -> Image.Image:
        region = {"left": monitor.left, "top": monitor.top, "width": monitor.width, "height": monitor.height}
        shot = self._sct().grab(region)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def close(self) -> None:
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            sct.close()
            self._local.sct = None
