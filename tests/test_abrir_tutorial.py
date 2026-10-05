"""Regressão: "Abrir tutorial" na barra abria a revisão e o app fechava sozinho.

Causa: a janela de revisão não tinha referência guardada; o Python a descartava,
o sinal destroyed disparava app.quit e o app fechava sem erro.
"""

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QFileDialog

from app.main import PassoApp
from app.project.model import Step
from app.project.storage import ProjectWorkspace


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


class _AppSpy:
    """Repassa tudo ao QApplication, mas só registra o quit."""

    def __init__(self, app):
        self._app = app
        self.quit_called = False

    def quit(self):
        self.quit_called = True

    def __getattr__(self, name):
        return getattr(self._app, name)


@pytest.fixture
def tutorial(tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    for i in range(2):
        rel, path = ws.next_image_path()
        Image.new("RGB", (320, 200), (40 * i, 90, 160)).save(path)
        ws.add_step(Step(image=rel, point=(50, 60), text=f"Passo {i + 1}: clique aqui"))
    dest = ws.save_to(tmp_path / "tutorial.passo")
    ws.cleanup()
    return dest


def _pump(app, n=5):
    for _ in range(n):
        gc.collect()
        app.processEvents()


def test_abrir_tutorial_pela_barra_mantem_app_aberto(qapp, tutorial, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(tutorial), "")))
    spy = _AppSpy(qapp)
    shell = PassoApp(spy)
    shell.show_bar()

    shell.bar.btn_open.click()  # mesmo caminho do botão
    _pump(qapp)

    assert not spy.quit_called, "o app tentou fechar depois de abrir o tutorial"
    assert len(shell.reviews) == 1
    review = shell.reviews[0]
    assert review.isVisible()
    assert review.list.count() == 2
    assert not shell.bar.isVisible()

    # Fechar a revisão encerra o app (era a única janela).
    review.close()
    _pump(qapp)
    assert spy.quit_called
    assert shell.reviews == []


def test_arquivo_invalido_mostra_erro_e_nao_fecha(qapp, tmp_path, monkeypatch):
    ruim = tmp_path / "ruim.passo"
    ruim.write_text("não é zip")
    erros = []
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.critical", lambda *a, **k: erros.append(a))
    spy = _AppSpy(qapp)
    shell = PassoApp(spy)
    assert shell.open_file(ruim) is None
    _pump(qapp)
    assert erros and not spy.quit_called and shell.reviews == []


def test_erro_em_slot_vai_para_o_log_e_vira_aviso(qapp, tmp_path, monkeypatch):
    import sys

    import app.main as am
    from PySide6.QtCore import QObject, QTimer, Signal

    monkeypatch.setattr(am, "LOG_DIR", tmp_path)
    monkeypatch.setattr(am, "LOG_FILE", tmp_path / "erros.log")
    avisos = []
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.critical", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)  # restaura depois do teste
    am.install_error_handler()

    class Emissor(QObject):
        sinal = Signal()

    def slot_com_erro():
        raise RuntimeError("falha de teste")

    e = Emissor()
    e.sinal.connect(slot_com_erro)
    e.sinal.emit()
    qapp.processEvents()

    assert "falha de teste" in (tmp_path / "erros.log").read_text(encoding="utf-8")
    assert avisos and "falha de teste" in avisos[0][2]
