"""Ajuste 2: última pasta de cada diálogo e "Pasta padrão dos tutoriais" (engrenagem da barra)."""

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QFileDialog

from app import settings
from app.project.model import Step
from app.project.storage import ProjectWorkspace


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def pastas(tmp_path):
    out = {}
    for nome in ("padrao", "salvar", "abrir", "exportar", "logo"):
        out[nome] = tmp_path / nome
        out[nome].mkdir()
    return out


@pytest.fixture
def ws(tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    rel, path = ws.next_image_path()
    Image.new("RGB", (320, 200), (40, 90, 160)).save(path)
    ws.add_step(Step(image=rel, point=(50, 60), text="Passo 1: clique aqui", app_name="Bloco de Notas"))
    return ws


def test_config_fica_no_localappdata(tmp_path, pastas):
    settings.remember_dir("salvar", pastas["salvar"])
    config = Path(os.environ["LOCALAPPDATA"]) / "PassoAPasso" / "config.json"
    assert config.is_file()
    assert json.loads(config.read_text(encoding="utf-8"))["last_dirs"]["salvar"] == str(pastas["salvar"])


def test_sem_nada_usa_documentos_depois_a_pasta_padrao_depois_a_ultima(pastas):
    assert settings.last_dir("salvar") == Path.home() / "Documents"
    settings.set_default_dir(pastas["padrao"])
    for dialogo in settings.DIALOGS:
        assert settings.last_dir(dialogo) == pastas["padrao"]
    settings.remember_dir("salvar", pastas["salvar"])
    assert settings.last_dir("salvar") == pastas["salvar"]
    assert settings.last_dir("abrir") == pastas["padrao"]  # cada diálogo tem a sua


def test_pasta_apagada_volta_para_a_padrao(pastas):
    settings.set_default_dir(pastas["padrao"])
    settings.remember_dir("abrir", pastas["abrir"])
    pastas["abrir"].rmdir()
    assert settings.last_dir("abrir") == pastas["padrao"]


def test_config_corrompido_nao_quebra(pastas):
    settings.config_path().parent.mkdir(parents=True, exist_ok=True)
    settings.config_path().write_text("{ isto não é json", encoding="utf-8")
    assert settings.last_dir("logo") == Path.home() / "Documents"
    settings.remember_dir("logo", pastas["logo"])
    assert settings.last_dir("logo") == pastas["logo"]


def test_dialogo_salvar_abre_e_lembra_a_ultima_pasta(qapp, ws, pastas, monkeypatch):
    from app.ui.review_window import ask_save_path

    inicios = []

    def fake(parent, caption, start, filtro):
        inicios.append(Path(start))
        return str(pastas["salvar"] / "meu"), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake))
    settings.set_default_dir(pastas["padrao"])
    assert ask_save_path(None, ws.project) == pastas["salvar"] / "meu.passo"
    assert ask_save_path(None, ws.project) is not None
    assert inicios[0].parent == pastas["padrao"]
    assert inicios[1].parent == pastas["salvar"]


def test_abrir_tutorial_lembra_a_pasta(qapp, pastas, monkeypatch):
    from app.main import PassoApp

    inicios = []

    def fake(parent, caption, start, filtro):
        inicios.append(start)
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(fake))
    shell = PassoApp(qapp)
    settings.remember_dir("abrir", pastas["abrir"])
    shell.ask_and_open()
    assert inicios == [str(pastas["abrir"])]

    arquivo = pastas["exportar"] / "x.passo"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a: (str(arquivo), "")))
    monkeypatch.setattr(shell, "open_file", lambda path: None)
    shell.ask_and_open()
    assert settings.last_dir("abrir") == pastas["exportar"]


def test_exportar_comeca_e_lembra_a_ultima_pasta(qapp, ws, pastas, monkeypatch):
    from app.ui.export_dialog import ExportDialog, ExportWorker

    settings.remember_dir("exportar", pastas["exportar"])
    dialog = ExportDialog(ws)
    assert Path(dialog.path.text()).parent == pastas["exportar"]

    monkeypatch.setattr(ExportWorker, "start", lambda self: None)  # não exporta de verdade
    dialog.path.setText(str(pastas["salvar"] / "saida.pdf"))
    dialog.start_export()
    assert settings.last_dir("exportar") == pastas["salvar"]


def test_logo_comeca_e_lembra_a_ultima_pasta(qapp, ws, pastas, monkeypatch):
    from app.ui.appearance_panel import AppearancePanel

    logo = pastas["logo"] / "marca.png"
    Image.new("RGBA", (80, 40), (0, 120, 200, 255)).save(logo)
    inicios = []

    def fake(parent, caption, start, filtro):
        inicios.append(start)
        return str(logo), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(fake))
    settings.set_default_dir(pastas["padrao"])
    panel = AppearancePanel(ws)
    panel.btn_logo.click()
    panel.btn_logo.click()
    assert inicios == [str(pastas["padrao"]), str(pastas["logo"])]
    assert ws.project.theme.logo


def test_engrenagem_define_a_pasta_padrao(qapp, pastas, monkeypatch):
    from app.main import PassoApp

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a: str(pastas["padrao"])))
    shell = PassoApp(qapp)
    assert shell.bar.btn_settings.text() == "⚙"
    assert shell.bar.btn_settings.isVisibleTo(shell.bar)  # visível com a barra parada
    shell.bar.act_folder.trigger()  # engrenagem > Pasta padrão dos tutoriais…
    assert settings.default_dir() == pastas["padrao"]
    assert str(pastas["padrao"]) in shell.bar.btn_settings.toolTip()

    # Cancelar o diálogo mantém a pasta.
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a: ""))
    shell.bar.act_folder.trigger()  # engrenagem > Pasta padrão dos tutoriais…
    assert settings.default_dir() == pastas["padrao"]
