"""Ajuste 4: a última logo e as últimas cores escolhidas viram o padrão dos próximos tutoriais."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from app import settings
from app.project.storage import ProjectWorkspace
from app.theme import LOGO_FILE, apply_brand_defaults

AZUL = (0, 90, 200, 255)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def logo(tmp_path):
    path = tmp_path / "marca.jpg"
    Image.new("RGB", (120, 60), AZUL[:3]).save(path)
    return path


def _novo(tmp_path, nome):
    ws = ProjectWorkspace(root=tmp_path / nome)
    apply_brand_defaults(ws)
    return ws


def test_sem_padrao_o_tutorial_novo_usa_o_tema_de_fabrica(tmp_path):
    ws = _novo(tmp_path, "novo")
    assert ws.project.theme.logo is None
    assert ws.project.theme.highlight_color == "#E53935"


def test_logo_escolhida_vira_padrao_em_png(qapp, tmp_path, logo):
    from app.ui.appearance_panel import AppearancePanel

    panel = AppearancePanel(ProjectWorkspace(root=tmp_path / "a"))
    assert panel.use_logo(logo)

    padrao = Path(os.environ["LOCALAPPDATA"]) / "PassoAPasso" / "logo_padrao.png"
    assert padrao.is_file()
    with Image.open(padrao) as img:
        assert img.format == "PNG" and img.convert("RGBA").getpixel((5, 5)) == AZUL

    ws = _novo(tmp_path, "b")
    assert ws.project.theme.logo == LOGO_FILE
    assert (ws.root / LOGO_FILE).is_file()
    # A logo é copiada para dentro do projeto: apagar o padrão não afeta este tutorial.
    padrao.unlink()
    assert (ws.root / LOGO_FILE).is_file()


def test_substituir_logo_troca_o_padrao(qapp, tmp_path, logo):
    from app.ui.appearance_panel import AppearancePanel

    panel = AppearancePanel(ProjectWorkspace(root=tmp_path / "a"))
    panel.use_logo(logo)
    verde = tmp_path / "verde.png"
    Image.new("RGBA", (50, 50), (0, 160, 0, 255)).save(verde)
    panel.use_logo(verde)
    with Image.open(settings.default_logo_path()) as img:
        assert img.convert("RGBA").getpixel((5, 5)) == (0, 160, 0, 255)


def test_remover_logo_limpa_o_padrao(qapp, tmp_path, logo):
    from app.ui.appearance_panel import AppearancePanel

    panel = AppearancePanel(ProjectWorkspace(root=tmp_path / "a"))
    panel.use_logo(logo)
    assert settings.default_logo() is not None
    panel.btn_remove_logo.click()
    assert settings.default_logo() is None
    assert _novo(tmp_path, "b").project.theme.logo is None


def test_ultimas_cores_viram_padrao(qapp, tmp_path):
    from app.ui.appearance_panel import AppearancePanel

    panel = AppearancePanel(ProjectWorkspace(root=tmp_path / "a"))
    panel.set_color("highlight_color", "#00897b")
    panel.set_color("page_background", "#fff8e1")
    panel.set_color("highlight_color", "#1e88e5")  # vale a última escolha

    theme = _novo(tmp_path, "b").project.theme
    assert theme.highlight_color == "#1E88E5"
    assert theme.page_background == "#FFF8E1"
    assert theme.margin_color == "#FFFFFF"  # não escolhida: continua a de fábrica
    assert theme.text_color == "#212121"
    # O tema padrão vai para o project.json do tutorial novo.
    assert "#1E88E5" in (tmp_path / "b" / "project.json").read_text(encoding="utf-8")


def test_logo_padrao_corrompida_nao_impede_gravar(tmp_path):
    settings.default_logo_path().parent.mkdir(parents=True, exist_ok=True)
    settings.default_logo_path().write_bytes(b"isto nao e png")
    assert _novo(tmp_path, "b").project.theme.logo is None


def test_gravacao_nova_aplica_os_padroes(qapp, tmp_path, monkeypatch):
    from app.recorder import controller as ctl

    settings.remember_color("highlight_color", "#8E24AA")
    criados = []

    class FakeWorker:
        def __init__(self, workspace, *a, **k):
            criados.append(workspace)
            self.stepAdded = self.failed = type("S", (), {"connect": lambda *a: None})()

        def start(self):
            pass

    class FakeHook:
        def start(self, cb):
            pass

    monkeypatch.setattr(ctl, "CaptureWorker", FakeWorker)
    monkeypatch.setattr(ctl.capture, "create_screen_grabber", lambda: None)
    monkeypatch.setattr(ctl.capture, "create_element_inspector", lambda: None)
    monkeypatch.setattr(ctl.capture, "double_click_settings", lambda: None)
    monkeypatch.setattr(ctl.capture, "create_input_hook", lambda: FakeHook())
    c = ctl.RecordingController()
    monkeypatch.setattr(c.hotkeys, "start", lambda: None)
    c.start()
    try:
        assert criados[0].project.theme.highlight_color == "#8E24AA"
    finally:
        criados[0].cleanup()
