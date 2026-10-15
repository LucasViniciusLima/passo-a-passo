"""Programas que não viram passos: janelas de administrador (UIPI) e apps de console/legados."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import subprocess
import sys

import pytest
from PIL import Image

from app import settings
from app.capture.base import ClickEvent, ElementInfo, ElementInspector, ScreenGrabber
from app.capture.coords import Monitor
from app.project.storage import ProjectWorkspace
from app.recorder.worker import CaptureWorker

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="integridade e UIA só no Windows")


def _log() -> str:
    path = settings.config_dir() / "erros.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --- nível de integridade ----------------------------------------------------


def test_regra_de_processo_mais_alto():
    from app.capture.elevacao import HIGH, MEDIUM, ProcessInfo, is_higher

    assert is_higher(ProcessInfo(1, "a.exe", HIGH), MEDIUM)
    assert not is_higher(ProcessInfo(1, "a.exe", MEDIUM), MEDIUM)
    assert not is_higher(ProcessInfo(1, "a.exe", HIGH), HIGH)  # já somos administrador
    assert is_higher(ProcessInfo(1, None, None), MEDIUM)  # o Windows negou a leitura: está acima
    assert not is_higher(ProcessInfo(1, None, None), HIGH)


def test_le_a_integridade_deste_processo():
    from app.capture.elevacao import own_integrity, process_info

    info = process_info(os.getpid())
    assert info.integrity == own_integrity()
    assert info.exe_path and info.exe_path.lower().endswith(".exe")


def _pid_de(nome: str) -> int | None:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {nome}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    for linha in out.splitlines():
        partes = [p.strip('"') for p in linha.split('","')]
        if len(partes) > 1 and partes[0].lower() == nome:
            return int(partes[1])
    return None


def test_processo_do_sistema_conta_como_elevado():
    """services.exe roda acima de qualquer usuário: serve de "janela elevada" real, sem abrir nada."""
    from app.capture.elevacao import is_admin, is_higher, own_integrity, process_info

    pid = _pid_de("services.exe")
    if pid is None:
        pytest.skip("services.exe não encontrado")
    if is_admin():
        pytest.skip("os testes estão rodando como administrador")
    assert is_higher(process_info(pid), own_integrity())


@pytest.fixture
def janela_cobol(monkeypatch):
    """Simula uma janela em primeiro plano de um sistema COBOL que roda como administrador."""
    from app.capture import elevacao

    monkeypatch.setattr(elevacao, "own_integrity", lambda: elevacao.MEDIUM)
    monkeypatch.setattr(elevacao, "_candidate_windows", lambda: [0x1234])
    monkeypatch.setattr(elevacao, "_window_pid", lambda hwnd: 4242)
    monkeypatch.setattr(elevacao, "_title", lambda hwnd: "SISCOB - Contas a Receber")
    monkeypatch.setattr(elevacao, "process_info",
                        lambda pid: elevacao.ProcessInfo(pid, r"C:\SISCOB\RUNCOBOL.EXE", elevacao.HIGH))
    return elevacao


def test_detecta_janela_elevada(janela_cobol, monkeypatch):
    window = janela_cobol.elevated_window_in_use()
    assert window is not None and window.name == "SISCOB - Contas a Receber"
    assert window.exe_path == r"C:\SISCOB\RUNCOBOL.EXE"

    # Mesma integridade: nada a avisar.
    monkeypatch.setattr(janela_cobol, "process_info",
                        lambda pid: janela_cobol.ProcessInfo(pid, "app.exe", janela_cobol.MEDIUM))
    assert janela_cobol.elevated_window_in_use() is None


def test_ja_sendo_admin_nao_avisa(janela_cobol, monkeypatch):
    monkeypatch.setattr(janela_cobol, "own_integrity", lambda: janela_cobol.HIGH)
    assert janela_cobol.elevated_window_in_use() is None


def test_propria_janela_nao_conta(janela_cobol, monkeypatch):
    monkeypatch.setattr(janela_cobol, "_window_pid", lambda hwnd: os.getpid())
    assert janela_cobol.elevated_window_in_use() is None


def test_comando_para_reiniciar(monkeypatch, tmp_path):
    from app.capture import elevacao

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\Passo a Passo\Passo a Passo.exe")
    assert elevacao.restart_command() == (r"C:\Apps\Passo a Passo\Passo a Passo.exe", "", r"C:\Apps\Passo a Passo")

    monkeypatch.delattr(sys, "frozen")
    main = tmp_path / "app" / "__main__.py"
    main.parent.mkdir()
    main.write_text("")
    monkeypatch.setattr(sys, "argv", [str(main)])
    exe, params, cwd = elevacao.restart_command()
    assert params == "-m app" and cwd == str(tmp_path)


# --- barra e controlador -------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def test_controlador_registra_o_motivo_uma_vez(janela_cobol):
    from app.recorder.controller import RecordingController

    c = RecordingController()
    assert c.check_elevated().name == "SISCOB - Contas a Receber"
    c.check_elevated()
    log = _log()
    assert log.count("RUNCOBOL.EXE") == 1
    assert "roda como administrador" in log and "UIPI" in log


def test_barra_avisa_e_oferece_reiniciar(qapp, janela_cobol):
    from app.recorder.controller import RecordingController
    from app.ui.recording_bar import RecordingBar

    bar = RecordingBar(RecordingController())
    pedidos = []
    bar.restartAsAdminRequested.connect(lambda: pedidos.append(1))
    bar.check_elevated()
    assert bar.warning_row.isVisibleTo(bar)
    assert "SISCOB - Contas a Receber" in bar.warning.text()
    assert "administrador" in bar.warning.text()
    bar.btn_admin.click()
    assert pedidos == [1]
    bar.show_elevated(None)
    assert not bar.warning_row.isVisibleTo(bar)


def test_reiniciar_como_admin(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.main import PassoApp

    shell = PassoApp(qapp)
    saidas = []
    shell.app = type("A", (), {"quit": lambda self: saidas.append("quit")})()
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: avisos.append(a)))

    monkeypatch.setattr("app.capture.restart_as_admin", lambda: False)  # UAC recusado
    assert shell.restart_as_admin() is False
    assert avisos and saidas == []

    monkeypatch.setattr("app.capture.restart_as_admin", lambda: True)
    assert shell.restart_as_admin() is True
    assert saidas == ["quit"]


# --- console e apps legados: o passo nunca se perde ---------------------------


class _Grabber(ScreenGrabber):
    def monitors(self):
        return [Monitor(1, 0, 0, 300, 200)]

    def grab(self, monitor):
        return Image.new("RGB", (300, 200), "black")


class _Quebrado(ElementInspector):
    def inspect(self, x, y):
        raise OSError("WindowFromPoint falhou")


def test_inspecao_falhando_ainda_grava_o_passo(tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    worker = CaptureWorker(ws, _Grabber(), t0=0, inspector=_Quebrado())
    worker._process(ClickEvent(30, 40, "left", 1.0))
    (step,) = ws.project.steps
    assert step.text == "Passo 1: clique aqui" and step.point == (30, 40)
    assert "passo gravado com texto padrão" in _log()


def test_console_com_uia_travado_usa_o_nome_do_app(tmp_path):
    """Programa COBOL de console: o UIA não responde, mas o Win32 já dá o nome do app."""
    import threading

    from app.capture.uia import UIAElementInspector

    class _Console(ElementInspector):
        def inspect(self, x, y):
            return ElementInfo(r"C:\Windows\System32\cmd.exe", "SISCOB", "ConsoleWindowClass", None,
                               window_rect=(0, 0, 300, 200))

    liberar = threading.Event()

    class _UIATravado(UIAElementInspector):
        def _init_com(self):
            pass

        def _query(self, x, y):
            liberar.wait(5)
            return {}

    insp = _UIATravado(_Console(), timeout=0.1)
    insp._pending.result(timeout=2)
    try:
        ws = ProjectWorkspace(root=tmp_path / "ws")
        worker = CaptureWorker(ws, _Grabber(), t0=0, inspector=insp)
        worker._process(ClickEvent(30, 40, "left", 1.0))
        worker._process(ClickEvent(200, 40, "left", 3.0))
        assert [s.text for s in ws.project.steps] == [
            "Passo 1: No Prompt de Comando, clique aqui",
            "Passo 2: No Prompt de Comando, clique aqui",
        ]
    finally:
        liberar.set()


def test_erro_na_captura_fica_no_log(tmp_path):
    class _SemTela(_Grabber):
        def grab(self, monitor):
            raise OSError("tela bloqueada")

    ws = ProjectWorkspace(root=tmp_path / "ws")
    worker = CaptureWorker(ws, _SemTela(), t0=0, inspector=_Quebrado())
    worker.queue.put(ClickEvent(1, 1, "left", 1.0))
    worker.stop()
    worker.run()  # roda na thread do teste
    assert ws.project.steps == []
    assert "Passo descartado" in _log() and "tela bloqueada" in _log()
