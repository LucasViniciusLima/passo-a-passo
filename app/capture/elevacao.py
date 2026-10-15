"""Janelas de administrador (nível de integridade) e reinício elevado, via Win32.

O Windows (UIPI) não entrega ao hook de mouse e teclado de um processo comum os
eventos feitos sobre janelas de um processo elevado. Nada falha: os cliques
simplesmente não chegam. Por isso o app procura essas janelas e avisa.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TOKEN_QUERY = 0x0008
_TOKEN_INTEGRITY_LEVEL = 25
_GA_ROOT = 2
_SW_SHOWNORMAL = 1

MEDIUM = 0x2000
HIGH = 0x3000  # administrador

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_advapi32 = ctypes.windll.advapi32

_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
_advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
_advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
]
_advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
_advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
_advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
_advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = [wintypes.POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_shell32 = ctypes.windll.shell32
_shell32.ShellExecuteW.argtypes = [
    wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int
]
_shell32.ShellExecuteW.restype = ctypes.c_void_p


def _token_integrity(process: int) -> int | None:
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        size = wintypes.DWORD()
        _advapi32.GetTokenInformation(token, _TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(size))
        if not size.value:
            return None
        buf = ctypes.create_string_buffer(size.value)
        if not _advapi32.GetTokenInformation(token, _TOKEN_INTEGRITY_LEVEL, buf, size, ctypes.byref(size)):
            return None
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        count = _advapi32.GetSidSubAuthorityCount(sid)[0]
        return int(_advapi32.GetSidSubAuthority(sid, count - 1)[0])
    finally:
        _kernel32.CloseHandle(token)


def own_integrity() -> int:
    return _token_integrity(_kernel32.GetCurrentProcess()) or MEDIUM


def is_admin() -> bool:
    return own_integrity() >= HIGH


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    exe_path: str | None
    integrity: int | None  # None: o Windows negou a leitura (processo de nível mais alto)


def process_info(pid: int) -> ProcessInfo:
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ProcessInfo(pid, None, None)
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        exe = buf.value if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else None
        return ProcessInfo(pid, exe, _token_integrity(handle))
    finally:
        _kernel32.CloseHandle(handle)


def is_higher(info: ProcessInfo, mine: int) -> bool:
    """O processo está acima do nosso? Sem acesso ao token, também conta como acima."""
    if info.integrity is None:
        return mine < HIGH
    return info.integrity > mine


@dataclass(frozen=True)
class ElevatedWindow:
    exe_path: str | None
    title: str

    @property
    def name(self) -> str:
        if self.title:
            return self.title[:60]
        return Path(self.exe_path).stem if self.exe_path else "Um programa"


def _window_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _title(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _candidate_windows() -> list:
    """Janela em primeiro plano e janela raiz sob o ponteiro do mouse."""
    windows = [_user32.GetForegroundWindow()]
    point = wintypes.POINT()
    if _user32.GetCursorPos(ctypes.byref(point)):
        under = _user32.WindowFromPoint(point)
        if under:
            windows.append(_user32.GetAncestor(under, _GA_ROOT) or under)
    return [w for w in windows if w]


def elevated_window_in_use() -> ElevatedWindow | None:
    """Janela em primeiro plano ou sob o mouse que pertence a um processo mais alto que o nosso."""
    mine = own_integrity()
    if mine >= HIGH:
        return None  # já somos administrador: o Windows entrega tudo
    own_pid = os.getpid()
    for hwnd in _candidate_windows():
        pid = _window_pid(hwnd)
        if not pid or pid == own_pid:
            continue
        info = process_info(pid)
        if is_higher(info, mine):
            return ElevatedWindow(info.exe_path, _title(hwnd))
    return None


def foreground_is_own_process() -> bool:
    hwnd = _user32.GetForegroundWindow()
    return bool(hwnd) and _window_pid(hwnd) == os.getpid()


def restart_command() -> tuple[str, str, str]:
    """(programa, parâmetros, pasta) para abrir de novo este mesmo app."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return exe, "", str(Path(exe).parent)
    exe = sys.executable
    pythonw = Path(exe).with_name("pythonw.exe")
    if pythonw.is_file():
        exe = str(pythonw)
    script = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
    if script is not None and script.name == "__main__.py":
        root = script.parent.parent
        return exe, f"-m {script.parent.name}", str(root)
    if script is not None and script.is_file():
        return exe, f'"{script}"', str(script.parent)
    root = Path(__file__).resolve().parents[2]
    return exe, "-m app", str(root)


def restart_as_admin() -> bool:
    """Pede elevação (UAC) e abre outra instância. False se o usuário recusou ou deu erro."""
    exe, params, cwd = restart_command()
    result = _shell32.ShellExecuteW(None, "runas", exe, params or None, cwd, _SW_SHOWNORMAL)
    return (result or 0) > 32
