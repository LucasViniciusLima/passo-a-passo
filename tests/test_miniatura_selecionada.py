"""Ajuste 5: miniatura selecionada com contorno na cor de destaque e número em negrito, sem mudar o fundo."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import pytest
from PIL import Image
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.project.model import Step
from app.project.storage import ProjectWorkspace
from app.ui.review_window import SELECTED_BORDER, ReviewWindow, item_html


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def review(qapp, tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    for i in range(3):
        rel, path = ws.next_image_path()
        Image.new("RGB", (320, 200), (20, 20, 20)).save(path)
        ws.add_step(Step(image=rel, point=(50, 60), text=f"Passo {i + 1}: clique aqui"))
    win = ReviewWindow(ws, None)
    win.show()  # plataforma offscreen: nada aparece na tela
    qapp.processEvents()
    yield win
    win.dirty = False
    win.close()


def _perto(a: QColor, b: str, tol=12):
    b = QColor(b)
    return all(abs(x - y) <= tol for x, y in zip((a.red(), a.green(), a.blue()), (b.red(), b.green(), b.blue())))


def _pixels(win, row):
    """Cor da borda (meio da lateral esquerda) e do fundo (canto interno) da miniatura."""
    image = win.list.viewport().grab().toImage()
    rect = win.list.visualItemRect(win.list.item(row))
    borda = image.pixelColor(rect.left() + 1 + SELECTED_BORDER // 2, rect.center().y())
    fundo = image.pixelColor(rect.left() + SELECTED_BORDER + 3, rect.bottom() - SELECTED_BORDER - 3)
    return borda, fundo


def test_numero_em_negrito_so_na_selecionada():
    assert item_html("Passo 2: clique aqui", True) == "<b>Passo 2:</b> clique aqui"
    assert item_html("Passo 2: clique aqui", False) == "Passo 2: clique aqui"
    assert item_html("Abra <o> menu", True) == "<b>Abra &lt;o&gt; menu</b>"


def test_selecionada_tem_borda_na_cor_de_destaque_sem_mudar_fundo_e_sem_foco(review, qapp):
    review.list.setCurrentRow(1)
    review.text.setFocus()  # a lista sem foco
    qapp.processEvents()
    assert not review.list.hasFocus()

    borda, fundo = _pixels(review, 1)
    assert _perto(borda, review.project.theme.highlight_color)
    fundo_lista = review.list.viewport().palette().base().color().name()
    assert _perto(fundo, fundo_lista)  # sem preenchimento: o fundo continua o da lista

    borda, fundo = _pixels(review, 0)  # não selecionada: sem borda, fundo da lista
    assert _perto(borda, fundo_lista) and _perto(fundo, fundo_lista)


def test_borda_acompanha_a_cor_de_destaque_do_tema(review, qapp):
    review.list.setCurrentRow(2)
    review.appearance.set_color("highlight_color", "#1E88E5")
    qapp.processEvents()
    borda, _ = _pixels(review, 2)
    assert _perto(borda, "#1E88E5")


def test_espessura_da_borda():
    assert 2 <= SELECTED_BORDER <= 3
