"""Passos de teclado: Tab e Enter viram passos; o resto do que é digitado nunca é registrado."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import sys

import pytest
from PIL import Image

from app import settings
from app.capture.base import ClickEvent, ElementInfo, ElementInspector, KeyEvent, ScreenGrabber
from app.capture.coords import Monitor
from app.project.model import Project, Step, default_text
from app.project.storage import ProjectWorkspace
from app.recorder.worker import KEY_REPEAT_GAP, CaptureWorker

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="hooks de teclado só no Windows")


class _Inspector(ElementInspector):
    def __init__(self, focus=(120, 60), focus_error=None):
        self.focus = focus
        self.focus_error = focus_error
        self.points = []

    def inspect(self, x, y):
        self.points.append((x, y))
        return ElementInfo(r"C:\Windows\notepad.exe", "nota.txt - Bloco de Notas", "Notepad", "RichEditD2DPT",
                           window_rect=(0, 0, 400, 200))

    def focus_point(self):
        if self.focus_error:
            raise self.focus_error
        return self.focus


class _Grabber(ScreenGrabber):
    def monitors(self):
        return [Monitor(1, 0, 0, 400, 200)]

    def grab(self, monitor):
        return Image.new("RGB", (400, 200), "white")


@pytest.fixture
def worker(tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    return CaptureWorker(ws, _Grabber(), t0=0, double_click=(0.5, 4), inspector=_Inspector())


def test_texto_dos_passos_de_teclado():
    assert default_text("key", 3, "No Bloco de Notas", key="Enter") == "Passo 3: Pressione Enter no Bloco de Notas"
    assert default_text("key", 1, None, key="Tab") == "Passo 1: Pressione Tab"
    assert default_text("key", 2, "No app Siscob", key="Tab", count=4) == "Passo 2: Pressione Tab 4 vezes no app Siscob"
    assert default_text("key", 2, None, key="Shift+Tab") == "Passo 2: Pressione Shift+Tab"


def test_atalhos_com_ctrl_alt_win_sao_ignorados():
    from app.capture.windows import key_name

    assert key_name("Tab", False, False, False, False) == "Tab"
    assert key_name("Enter", False, False, False, True) == "Enter"
    assert key_name("Tab", False, False, False, True) == "Shift+Tab"
    assert key_name("Tab", True, False, False, False) is None  # Ctrl+Tab troca de aba
    assert key_name("Tab", False, True, False, False) is None  # Alt+Tab troca de janela
    assert key_name("Enter", False, False, True, False) is None
    assert key_name("Enter", False, True, False, False) is None  # Alt+Enter


def test_hook_so_repassa_tab_e_enter(monkeypatch):
    from pynput.keyboard import Key, KeyCode

    from app.capture import windows

    monkeypatch.setattr(windows, "modifiers_down", lambda: (False, False, False, False))
    hook = windows.PynputKeyHook()
    recebidas = []
    hook._on_key = recebidas.append
    for key in [KeyCode.from_char("s"), KeyCode.from_char("1"), Key.space, Key.backspace, Key.esc, Key.f9,
                Key.tab, KeyCode.from_char("x"), Key.enter, Key.shift, Key.ctrl_l]:
        hook.handle(key)
    assert [e.key for e in recebidas] == ["Tab", "Enter"]
    # Nem o objeto do evento guarda outra coisa além do nome da tecla e da hora.
    assert set(vars(recebidas[0])) == {"key", "time"}

    monkeypatch.setattr(windows, "modifiers_down", lambda: (True, False, False, False))
    hook.handle(Key.tab)
    assert len(recebidas) == 2


def test_tabs_seguidos_viram_um_passo(worker):
    for t in (1.0, 1.2, 1.4):
        worker._process_key(KeyEvent("Tab", t))
    (step,) = worker.workspace.project.steps
    assert (step.action, step.key, step.count) == ("key", "Tab", 3)
    assert step.text == "Passo 1: Pressione Tab 3 vezes no Bloco de Notas (nota.txt)"
    assert step.point == (120, 60)  # onde está o foco do teclado, não o mouse
    assert step.app_name == "Bloco de Notas"
    assert step.focus_rect == [0, 0, 400, 200]


def test_enter_pausa_ou_clique_quebram_a_sequencia(worker):
    worker._process_key(KeyEvent("Tab", 1.0))
    worker._process_key(KeyEvent("Enter", 1.3))  # outra tecla
    worker._process_key(KeyEvent("Enter", 1.4 + KEY_REPEAT_GAP + 0.1))  # depois de uma pausa
    worker._process(ClickEvent(50, 50, "left", 5.0))
    worker._process_key(KeyEvent("Tab", 5.2))  # depois de um clique
    worker._process_key(KeyEvent("Tab", 5.3))
    textos = [s.text for s in worker.workspace.project.steps]
    assert textos == [
        "Passo 1: Pressione Tab no Bloco de Notas (nota.txt)",
        "Passo 2: Pressione Enter no Bloco de Notas (nota.txt)",
        "Passo 3: Pressione Enter no Bloco de Notas (nota.txt)",
        "Passo 4: No Bloco de Notas (nota.txt), clique aqui",
        "Passo 5: Pressione Tab 2 vezes no Bloco de Notas (nota.txt)",
    ]


def test_tab_logo_depois_de_clique_nao_vira_duplo_clique(worker):
    worker._process(ClickEvent(50, 50, "left", 1.0))
    worker._process_key(KeyEvent("Tab", 1.1))
    worker._process(ClickEvent(50, 50, "left", 1.2))
    assert [s.action for s in worker.workspace.project.steps] == ["click", "key", "click"]


def test_sem_foco_conhecido_usa_o_centro_da_tela(tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    insp = _Inspector(focus_error=RuntimeError("UIA travado"))
    worker = CaptureWorker(ws, _Grabber(), t0=0, inspector=insp)
    worker._process_key(KeyEvent("Enter", 1.0))
    assert ws.project.steps[0].point == (200, 100)
    assert "Foco do teclado indisponível" in (settings.config_dir() / "erros.log").read_text(encoding="utf-8")


def test_passo_de_teclado_salva_e_reabre():
    step = Step(image="images/x.png", point=(1, 2), action="key", key="Tab", count=5, text="Passo 1: Pressione Tab 5 vezes")
    data = Project(steps=[step]).to_dict()
    assert data["steps"][0]["key"] == "Tab" and data["steps"][0]["count"] == 5
    back = Project.from_dict(data).steps[0]
    assert (back.action, back.key, back.count) == ("key", "Tab", 5)
    # Passos de clique continuam sem os campos novos.
    assert "key" not in Step(image="a.png", point=(0, 0)).to_dict()


def test_opcao_da_engrenagem_liga_e_desliga():
    assert settings.keyboard_steps() is True  # ligado por padrão
    settings.set_keyboard_steps(False)
    assert settings.keyboard_steps() is False
    settings.set_keyboard_steps(True)
    assert settings.keyboard_steps() is True


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_menu_da_engrenagem_grava_a_opcao(qapp):
    from app.recorder.controller import RecordingController
    from app.ui.recording_bar import RecordingBar

    bar = RecordingBar(RecordingController())
    assert bar.act_keys.isCheckable() and bar.act_keys.isChecked()
    bar.act_keys.trigger()
    assert settings.keyboard_steps() is False
    assert RecordingBar(RecordingController()).act_keys.isChecked() is False


class _FakeWorker:
    def __init__(self, *a, **k):
        self.recebidos = []
        self.stepAdded = self.failed = type("S", (), {"connect": lambda *a: None})()

    def start(self):
        pass

    def submit(self, event):
        self.recebidos.append(event)

    def stop(self):
        pass

    def wait(self):
        pass


class _FakeHook:
    def __init__(self, log):
        self.log = log

    def start(self, cb):
        self.log.append("start")

    def stop(self):
        pass


@pytest.fixture
def controller(monkeypatch):
    from app.recorder import controller as ctl

    hooks = []
    monkeypatch.setattr(ctl, "CaptureWorker", _FakeWorker)
    monkeypatch.setattr(ctl.capture, "create_screen_grabber", lambda: None)
    monkeypatch.setattr(ctl.capture, "create_element_inspector", lambda: None)
    monkeypatch.setattr(ctl.capture, "double_click_settings", lambda: None)
    monkeypatch.setattr(ctl.capture, "create_input_hook", lambda: _FakeHook([]))
    monkeypatch.setattr(ctl.capture, "create_key_hook", lambda: _FakeHook(hooks))
    monkeypatch.setattr(ctl.capture, "foreground_is_own_process", lambda: False)
    c = ctl.RecordingController()
    monkeypatch.setattr(c.hotkeys, "start", lambda: None)
    monkeypatch.setattr(c.hotkeys, "stop", lambda: None)
    c.key_hooks = hooks
    yield c
    if c.workspace is not None:
        c.workspace.cleanup()


def test_controlador_filtra_teclas(controller, monkeypatch):
    controller.start()
    assert controller.key_hooks == ["start"]
    worker = controller._worker
    controller._on_key(KeyEvent("Tab", 1.0))
    controller.pause()
    controller._on_key(KeyEvent("Enter", 2.0))  # pausado: descartado
    controller.resume()
    monkeypatch.setattr("app.capture.foreground_is_own_process", lambda: True)
    controller._on_key(KeyEvent("Enter", 3.0))  # na própria barra: descartado
    assert [e.key for e in worker.recebidos] == ["Tab"]
    log = (settings.config_dir() / "erros.log").read_text(encoding="utf-8")
    assert "Evento descartado: Enter durante a pausa" in log


def test_opcao_desligada_nao_liga_o_hook_de_teclado(controller):
    settings.set_keyboard_steps(False)
    controller.start()
    assert controller.key_hooks == []
    assert controller._keys is None
