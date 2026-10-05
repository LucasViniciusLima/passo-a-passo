"""Ajuste 1: excluir passos na revisão (botão, Delete, seleção múltipla, confirmação, Ctrl+Z)."""

import os
import re
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.export import PdfOptions
from app.export.pdf import export_pdf
from app.project.model import Step, renumber_steps
from app.project.storage import ProjectWorkspace, open_passo
from app.ui.review_window import ReviewWindow

TEXTOS = ["Passo 1: clique aqui", "Passo 2: Abra o menu Arquivo", "Passo 3: clique aqui", "Passo 4: Clique em OK"]
SIM = QMessageBox.StandardButton.Yes
NAO = QMessageBox.StandardButton.No


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def review(qapp, tmp_path, monkeypatch):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    for i, text in enumerate(TEXTOS):
        rel, path = ws.next_image_path()
        Image.new("RGB", (320, 200), (40 * i, 90, 160)).save(path)
        ws.add_step(Step(image=rel, point=(50, 60), text=text))
    win = ReviewWindow(ws, None)
    win.dirty = False  # fechar no fim do teste sem perguntar
    yield win
    win.dirty = False
    win.close()


@pytest.fixture
def perguntas(monkeypatch):
    """Registra as confirmações e responde com o valor de perguntas.resposta."""

    class Registro(list):
        resposta = SIM

    reg = Registro()

    def question(parent, title, text, *a, **k):
        reg.append(text)
        return reg.resposta

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return reg


def _selecionar(win, rows):
    win.list.clearSelection()
    win.list.setCurrentRow(rows[0])
    for r in rows:
        win.list.item(r).setSelected(True)


def _textos(win):
    return [s.text for s in win.project.steps]


def test_renumera_so_o_prefixo():
    steps = [Step(image="a", point=(0, 0), text=t) for t in ("Passo 3: abra", "Texto livre", "Passo 9: fim")]
    renumber_steps(steps)
    assert [s.text for s in steps] == ["Passo 1: abra", "Texto livre", "Passo 3: fim"]


def test_botao_exclui_selecao_multipla_com_confirmacao_e_renumera(review, perguntas):
    assert review.list.selectionMode() == review.list.SelectionMode.ExtendedSelection
    _selecionar(review, [1, 2])
    assert review.btn_delete.text() == "Excluir 2 passos"

    review.btn_delete.click()

    assert len(perguntas) == 1 and "2 passos" in perguntas[0]
    assert _textos(review) == ["Passo 1: clique aqui", "Passo 2: Clique em OK"]
    assert [review.list.item(i).text() for i in range(review.list.count())] == _textos(review)
    assert review.dirty and review.windowTitle().startswith("Revisão — não salvo *")


def test_cancelar_a_confirmacao_nao_exclui(review, perguntas):
    perguntas.resposta = NAO
    _selecionar(review, [0])
    assert review.delete_selected() is False
    assert perguntas and "passo 1" in perguntas[0]
    assert _textos(review) == TEXTOS


def test_ctrl_z_desfaz_varias_exclusoes_em_ordem(review, perguntas):
    _selecionar(review, [0])
    review.delete_selected()
    _selecionar(review, [2])
    review.delete_selected()
    assert _textos(review) == ["Passo 1: Abra o menu Arquivo", "Passo 2: clique aqui"]

    assert review.undo_delete()
    assert _textos(review) == ["Passo 1: Abra o menu Arquivo", "Passo 2: clique aqui", "Passo 3: Clique em OK"]
    assert review.undo_delete()
    assert _textos(review) == TEXTOS
    assert review.list.count() == 4
    assert review.undo_delete() is False


def test_tecla_delete_e_ctrl_z_pelo_teclado(review, perguntas, qapp):
    review.show()  # plataforma offscreen: nada aparece na tela
    review.activateWindow()
    review.list.setFocus()
    qapp.processEvents()
    _selecionar(review, [3])

    QTest.keyClick(review.list, Qt.Key.Key_Delete)
    assert perguntas and _textos(review) == TEXTOS[:3]

    QTest.keyClick(review.list, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert _textos(review) == TEXTOS


def test_delete_no_campo_de_texto_nao_exclui_passo(review, perguntas, qapp):
    review.show()
    review.activateWindow()
    review.text.setFocus()
    qapp.processEvents()
    review.text.setCursorPosition(0)
    QTest.keyClick(review.text, Qt.Key.Key_Delete)
    assert not perguntas and len(review.project.steps) == 4


def test_nao_exclui_todos_os_passos(review, perguntas, monkeypatch):
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a)))
    _selecionar(review, [0, 1, 2, 3])
    assert review.delete_selected() is False
    assert avisos and not perguntas and len(review.project.steps) == 4


def _paginas(pdf):
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))


def test_salvar_e_exportar_usam_so_os_passos_restantes(review, perguntas, tmp_path):
    antes = export_pdf(review.project, review.workspace.root, tmp_path / "antes.pdf", PdfOptions())
    _selecionar(review, [0, 2])
    review.delete_selected()
    restantes = [s.image for s in review.project.steps]

    depois = export_pdf(review.project, review.workspace.root, tmp_path / "depois.pdf", PdfOptions())
    assert _paginas(antes) - _paginas(depois) == 2

    dest = review.workspace.save_to(tmp_path / "t.passo")
    with zipfile.ZipFile(dest) as zf:
        imagens = sorted(n for n in zf.namelist() if n.startswith("images/"))
    assert imagens == sorted(restantes)
    aberto = open_passo(dest)
    try:
        assert [s.text for s in aberto.project.steps] == ["Passo 1: Abra o menu Arquivo", "Passo 2: Clique em OK"]
    finally:
        aberto.cleanup()
    # O project.json da pasta temporária também já reflete a exclusão.
    assert '"Passo 2: Clique em OK"' in (review.workspace.root / "project.json").read_text(encoding="utf-8")
