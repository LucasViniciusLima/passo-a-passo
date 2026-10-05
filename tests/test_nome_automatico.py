"""Ajuste 3: nome automático "Tutorial <app> AAAA-MM-DD HHhMM" ao salvar um tutorial novo."""

import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QFileDialog

from app import settings
from app.project.model import Project, Step
from app.project.naming import auto_title, unique_path
from app.project.storage import ProjectWorkspace

QUANDO = datetime(2026, 10, 5, 15, 7)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _projeto(app_name="Bloco de Notas"):
    project = Project(created_at=QUANDO.astimezone().isoformat())
    project.steps.append(Step(image="a.png", point=(0, 0), app_name=app_name))
    project.steps.append(Step(image="b.png", point=(0, 0), app_name="Outro App"))
    return project


def test_formato_com_app_do_primeiro_passo():
    assert auto_title(_projeto(), QUANDO) == "Tutorial Bloco de Notas 2026-10-05 15h07"


def test_usa_a_hora_da_gravacao_por_padrao():
    assert auto_title(_projeto()) == "Tutorial Bloco de Notas 2026-10-05 15h07"


def test_sem_app_ou_sem_passos():
    assert auto_title(_projeto(app_name=None), QUANDO) == "Tutorial 2026-10-05 15h07"
    assert auto_title(Project(), QUANDO) == "Tutorial 2026-10-05 15h07"


def test_caracteres_invalidos_saem_do_nome():
    assert auto_title(_projeto(app_name='Editor: "a/b"'), QUANDO) == "Tutorial Editor ab 2026-10-05 15h07"


def test_sufixo_quando_ja_existe(tmp_path):
    base = "Tutorial Bloco de Notas 2026-10-05 15h07"
    assert unique_path(tmp_path, base, ".passo").name == f"{base}.passo"
    (tmp_path / f"{base}.passo").touch()
    assert unique_path(tmp_path, base, ".passo").name == f"{base} (2).passo"
    (tmp_path / f"{base} (2).passo").touch()
    assert unique_path(tmp_path, base, ".passo").name == f"{base} (3).passo"


def _salvar_capturando(monkeypatch):
    sugestoes = []

    def fake(parent, caption, start, filtro):
        sugestoes.append(Path(start))
        return start, ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake))
    return sugestoes


def test_dialogo_sugere_nome_com_sufixo_e_define_titulo(qapp, tmp_path, monkeypatch):
    from app.ui.review_window import ask_save_path

    settings.set_default_dir(tmp_path)
    nome = "Tutorial Bloco de Notas 2026-10-05 15h07"
    (tmp_path / f"{nome}.passo").touch()
    sugestoes = _salvar_capturando(monkeypatch)
    project = _projeto()

    path = ask_save_path(None, project)

    assert sugestoes[0].name == f"{nome} (2).passo"
    assert path == tmp_path / f"{nome} (2).passo"
    assert project.title == nome


def test_titulo_ja_editado_e_mantido(qapp, tmp_path, monkeypatch):
    from app.ui.review_window import ask_save_path

    settings.set_default_dir(tmp_path)
    sugestoes = _salvar_capturando(monkeypatch)
    project = _projeto()
    project.title = "Como emitir nota"
    ask_save_path(None, project)
    assert project.title == "Como emitir nota"
    assert sugestoes[0].name == "Como emitir nota.passo"


def test_ao_finalizar_gravacao_salva_com_nome_e_titulo_automaticos(qapp, tmp_path, monkeypatch):
    from app.main import PassoApp

    settings.set_default_dir(tmp_path / "docs")
    (tmp_path / "docs").mkdir()
    _salvar_capturando(monkeypatch)
    ws = ProjectWorkspace(root=tmp_path / "ws")
    ws.project.created_at = QUANDO.astimezone().isoformat()
    rel, path = ws.next_image_path()
    Image.new("RGB", (320, 200), (40, 90, 160)).save(path)
    ws.add_step(Step(image=rel, point=(50, 60), text="Passo 1: clique aqui", app_name="Calculadora"))

    shell = PassoApp(qapp)
    shell.on_finished(ws)
    review = shell.reviews[0]
    try:
        nome = "Tutorial Calculadora 2026-10-05 15h07"
        assert review.saved_path == tmp_path / "docs" / f"{nome}.passo"
        assert review.saved_path.is_file()
        assert review.title.text() == nome and ws.project.title == nome
    finally:
        review.dirty = False
        review.close()


def test_salvar_na_revisao_atualiza_o_campo_titulo(qapp, tmp_path, monkeypatch):
    from app.ui.review_window import ReviewWindow

    settings.set_default_dir(tmp_path)
    _salvar_capturando(monkeypatch)
    ws = ProjectWorkspace(root=tmp_path / "ws")
    ws.project.created_at = QUANDO.astimezone().isoformat()
    rel, path = ws.next_image_path()
    Image.new("RGB", (320, 200), (40, 90, 160)).save(path)
    ws.add_step(Step(image=rel, point=(50, 60), text="Passo 1: clique aqui", app_name="Paint"))
    review = ReviewWindow(ws, None)
    try:
        assert review.title.text() == "Novo tutorial"
        assert review.save()
        assert review.title.text() == "Tutorial Paint 2026-10-05 15h07"
        assert review.saved_path.name == "Tutorial Paint 2026-10-05 15h07.passo"
    finally:
        review.dirty = False
        review.close()
