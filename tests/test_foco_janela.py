"""Destaque no modo janela: a janela clicada fica nítida, o resto desfocado."""

import sys

import pytest
from PIL import Image

from app.capture.coords import Monitor, rect_to_image
from app.project.model import Project, Step
from app.render.annotate import annotate_step

FUNDO_ESCURO_MAX = 255 * 0.75 + 1


def _xadrez(w=600, h=400):
    img = Image.new("RGB", (w, h))
    img.putdata([(255, 255, 255) if (x // 4 + y // 4) % 2 else (30, 60, 90) for y in range(h) for x in range(w)])
    return img


def test_janela_fica_nitida_e_fora_desfoca():
    img = _xadrez()
    janela = [100, 80, 300, 200]  # x, y, w, h
    step = Step(image="x.png", point=(150, 300), focus_rect=janela)  # clique fora do miolo da janela
    out = annotate_step(img, step, Project())  # modo "janela" é o padrão
    # Dentro da janela (longe da borda suave e do círculo): igual ao original.
    for p in [(120, 100), (380, 100), (250, 180), (120, 260), (380, 260)]:
        assert out.getpixel(p) == img.getpixel(p), p
    # Fora: desfocado e escurecido.
    for p in [(10, 10), (590, 10), (500, 380), (50, 200)]:
        assert out.getpixel(p) != img.getpixel(p), p
        assert max(out.getpixel(p)) <= FUNDO_ESCURO_MAX, p


def test_circulo_continua_por_cima_da_janela():
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    step = Step(image="x.png", point=(200, 150), focus_rect=[50, 50, 300, 200])
    out = annotate_step(img, step, Project())
    r, g, b = out.getpixel((226, 150))  # borda do círculo
    assert r > 200 and g < 90 and b < 90


def test_sem_focus_rect_nao_desfoca_nada():
    """Tutoriais antigos e cliques na Área de Trabalho não têm focus_rect."""
    img = _xadrez()
    out = annotate_step(img, Step(image="x.png", point=(300, 200)), Project())
    assert out.getpixel((10, 10)) == img.getpixel((10, 10))
    assert out.getpixel((590, 390)) == img.getpixel((590, 390))


def test_janela_maximizada_nao_desfoca():
    img = _xadrez()
    step = Step(image="x.png", point=(300, 200), focus_rect=[0, 0, 600, 392])  # quase a tela toda
    out = annotate_step(img, step, Project())
    assert out.getpixel((5, 396)) == img.getpixel((5, 396))


def test_barra_de_tarefas_nitida_resto_desfocado():
    img = _xadrez()
    barra = [0, 360, 600, 40]
    out = annotate_step(img, Step(image="x.png", point=(300, 380), focus_rect=barra), Project())
    assert out.getpixel((100, 385)) == img.getpixel((100, 385))
    assert out.getpixel((100, 100)) != img.getpixel((100, 100))


def test_modo_desligado_ignora_focus_rect():
    img = _xadrez()
    project = Project()
    project.theme.spotlight.mode = "desligado"
    out = annotate_step(img, Step(image="x.png", point=(300, 200), focus_rect=[100, 80, 300, 200]), project)
    assert out.getpixel((10, 10)) == img.getpixel((10, 10))


def test_focus_rect_no_json_e_compatibilidade():
    step = Step(image="a.png", point=(1, 1), focus_rect=[10, 20, 300, 200])
    assert Step.from_dict(step.to_dict()).focus_rect == [10, 20, 300, 200]
    antigo = step.to_dict()
    del antigo["focus_rect"]
    assert Step.from_dict(antigo).focus_rect is None


# --- conversão do retângulo para a imagem -----------------------------------

PRINCIPAL = Monitor(1, 0, 0, 1920, 1080)
SECUNDARIO = Monitor(2, 1920, 0, 1600, 900)


def test_retangulo_convertido_e_recortado_ao_monitor():
    assert rect_to_image((100, 50, 900, 650), PRINCIPAL, (1920, 1080)) == [100, 50, 800, 600]
    # Janela no segundo monitor.
    assert rect_to_image((2000, 100, 2400, 500), SECUNDARIO, (1600, 900)) == [80, 100, 400, 400]
    # Janela que passa da borda: só a parte dentro do monitor.
    assert rect_to_image((1800, -20, 2100, 300), PRINCIPAL, (1920, 1080)) == [1800, 0, 120, 300]
    # Imagem em escala diferente do monitor (ex.: pixels lógicos).
    assert rect_to_image((0, 0, 960, 540), PRINCIPAL, (960, 540)) == [0, 0, 480, 270]


def test_retangulo_fora_do_monitor_ou_ausente():
    assert rect_to_image((2000, 0, 2100, 100), PRINCIPAL, (1920, 1080)) is None
    assert rect_to_image(None, PRINCIPAL, (1920, 1080)) is None


@pytest.mark.skipif(sys.platform != "win32", reason="só Windows")
def test_uniao_de_menu_ou_dialogo_com_a_janela_dona():
    from app.capture.windows import _union

    dialogo = (600, 300, 1300, 800)
    dona = (100, 100, 1000, 700)
    assert _union(dialogo, dona) == (100, 100, 1300, 800)
    assert _union(None, dona) == dona
    assert _union(dialogo, None) == dialogo
