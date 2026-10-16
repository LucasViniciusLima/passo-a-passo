"""Mudar a ordem dos passos na revisão: setas, Ctrl+↑/↓, posição digitada e Ctrl+Z."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.project.model import Step
from app.project.storage import ProjectWorkspace, open_passo
from app.ui.review_window import ReviewWindow

TEXTOS = ["Passo 1: Abra o menu Arquivo", "Passo 2: Clique em Salvar", "Passo 3: Digite o nome", "Passo 4: Clique em OK"]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def review(qapp, tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    for i, text in enumerate(TEXTOS):
        rel, path = ws.next_image_path()
        Image.new("RGB", (320, 200), (40 * i, 90, 160)).save(path)
        ws.add_step(Step(image=rel, point=(50, 60), text=text))
    win = ReviewWindow(ws, None)
    win.dirty = False
    yield win
    win.dirty = False
    win.close()


def _textos(win):
    return [s.text for s in win.project.steps]


def _lista(win):
    return [win.list.item(i).text() for i in range(win.list.count())]


def test_setas_sobem_e_descem_e_renumeram(review):
    review.list.setCurrentRow(2)
    review.btn_up.click()
    assert _textos(review) == ["Passo 1: Abra o menu Arquivo", "Passo 2: Digite o nome",
                               "Passo 3: Clique em Salvar", "Passo 4: Clique em OK"]
    assert _lista(review) == _textos(review)  # cards atualizados
    assert review.list.currentRow() == 1  # a seleção acompanha o passo
    assert review.dirty
    review.btn_down.click()
    review.btn_down.click()
    assert _textos(review)[3] == "Passo 4: Digite o nome"
    assert review.list.currentRow() == 3


def test_setas_desabilitadas_nas_pontas(review):
    review.list.setCurrentRow(0)
    assert not review.btn_up.isEnabled() and review.btn_down.isEnabled()
    review.list.setCurrentRow(3)
    assert review.btn_up.isEnabled() and not review.btn_down.isEnabled()
    assert review.move_current(+1) is False  # já é o último
    assert _textos(review) == TEXTOS


def test_atalhos_ctrl_seta(review):
    review.show()
    review.list.setFocus()
    review.list.setCurrentRow(0)
    QTest.keyClick(review.list, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    assert _textos(review)[1] == "Passo 2: Abra o menu Arquivo"
    QTest.keyClick(review.list, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
    assert _textos(review) == TEXTOS


def test_posicao_digitada_move_o_passo(review):
    review.list.setCurrentRow(0)
    assert review.position.value() == 1 and review.position_total.text() == "de 4"
    review.position.setValue(4)
    assert _textos(review) == ["Passo 1: Clique em Salvar", "Passo 2: Digite o nome",
                               "Passo 3: Clique em OK", "Passo 4: Abra o menu Arquivo"]
    assert review.list.currentRow() == 3 and review.position.value() == 4


def test_posicao_validada(review):
    assert (review.position.minimum(), review.position.maximum()) == (1, 4)
    review.list.setCurrentRow(1)
    review.position.lineEdit().setText("9")  # fora do intervalo: a caixa não aceita
    review.position.interpretText()
    assert review.position.value() in (1, 2, 3, 4)
    assert review.move_step(1, 9) is False and review.move_step(1, -1) is False
    assert review.move_step(1, 1) is False  # mesma posição
    assert _textos(review)[1] == "Passo 2: Clique em Salvar"


def test_ctrl_z_desfaz_a_mudanca_de_ordem(review):
    review.list.setCurrentRow(3)
    review.position.setValue(1)
    assert _textos(review)[0] == "Passo 1: Clique em OK"
    assert review.undo_delete()
    assert _textos(review) == TEXTOS and _lista(review) == TEXTOS
    assert review.list.currentRow() == 3


def test_exclusao_continua_desfazendo(review, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    review.list.setCurrentRow(0)
    review.move_current(+1)
    review.list.setCurrentRow(3)
    review.delete_selected()
    assert len(review.project.steps) == 3
    assert review.undo_delete()  # desfaz a exclusão
    assert len(review.project.steps) == 4 and _textos(review)[0] == "Passo 1: Clique em Salvar"
    assert review.undo_delete()  # desfaz a mudança de ordem
    assert _textos(review) == TEXTOS


def test_nova_ordem_vai_para_o_arquivo(review, tmp_path):
    review.list.setCurrentRow(3)
    review.move_current(-1)
    destino = tmp_path / "ordem.passo"
    review.saved_path = destino
    assert review.save()
    reaberto = open_passo(destino)
    try:
        assert [s.text for s in reaberto.project.steps] == [
            "Passo 1: Abra o menu Arquivo", "Passo 2: Clique em Salvar", "Passo 3: Clique em OK", "Passo 4: Digite o nome",
        ]
        assert [s.image for s in reaberto.project.steps] == [s.image for s in review.project.steps]
    finally:
        reaberto.cleanup()


def test_um_passo_so_desabilita_a_ordem(qapp, tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "um")
    rel, path = ws.next_image_path()
    Image.new("RGB", (100, 80)).save(path)
    ws.add_step(Step(image=rel, point=(1, 1), text="Passo 1: clique aqui"))
    win = ReviewWindow(ws, None)
    try:
        assert not win.btn_up.isEnabled() and not win.btn_down.isEnabled()
        assert not win.position.isEnabled()
    finally:
        win.dirty = False
        win.close()
