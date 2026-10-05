import pytest

from app.capture.base import ClickEvent
from app.capture.coords import (
    Monitor, find_monitor, logical_to_physical, physical_to_logical, rect_contains, to_image_point,
)
from app.recorder.clicks import action_for, is_double_click

# Monitor principal 4K a 150% e um secundário 1080p a 100% à esquerda, um pouco mais baixo.
PRINCIPAL = Monitor(1, 0, 0, 3840, 2160, 1.5)
SECUNDARIO = Monitor(2, -1920, 300, 1920, 1080, 1.0)
MONITORES = [PRINCIPAL, SECUNDARIO]


def test_encontra_monitor_pelo_ponto():
    assert find_monitor(100, 100, MONITORES) is PRINCIPAL
    assert find_monitor(-10, 400, MONITORES) is SECUNDARIO
    assert find_monitor(3839, 2159, MONITORES) is PRINCIPAL


def test_ponto_fora_de_todos_vai_para_o_mais_proximo():
    assert find_monitor(-500, 0, MONITORES) is SECUNDARIO
    assert find_monitor(5000, 10, MONITORES) is PRINCIPAL


def test_sem_monitores():
    with pytest.raises(ValueError):
        find_monitor(0, 0, [])


def test_imagem_fisica_do_mesmo_tamanho():
    assert to_image_point(812, 440, PRINCIPAL, (3840, 2160)) == (812, 440)


def test_monitor_com_origem_negativa():
    assert to_image_point(-1900, 310, SECUNDARIO, (1920, 1080)) == (20, 10)


def test_imagem_em_pixels_logicos():
    # Captura em pixels lógicos (2560x1440) de um monitor físico 4K a 150%.
    assert to_image_point(1218, 660, PRINCIPAL, (2560, 1440)) == (812, 440)


def test_ponto_e_limitado_a_imagem():
    assert to_image_point(4000, -5, PRINCIPAL, (3840, 2160)) == (3839, 0)


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
def test_conversao_logico_fisico(scale):
    fisico = logical_to_physical((400, 300), scale)
    assert fisico == (round(400 * scale), round(300 * scale))
    assert physical_to_logical(fisico, scale) == pytest.approx((400, 300), abs=1)


def test_retangulo_da_barra():
    barra = (100, 10, 500, 50)
    assert rect_contains(barra, 100, 10)
    assert rect_contains(barra, 499, 49)
    assert not rect_contains(barra, 500, 30)
    assert not rect_contains(None, 0, 0)


def test_duplo_clique():
    a = ClickEvent(100, 100, "left", 10.0)
    assert is_double_click(a, ClickEvent(102, 99, "left", 10.3), 0.5, 4)
    assert not is_double_click(a, ClickEvent(102, 99, "left", 10.8), 0.5, 4)
    assert not is_double_click(a, ClickEvent(120, 100, "left", 10.1), 0.5, 4)
    assert not is_double_click(a, ClickEvent(100, 100, "right", 10.1), 0.5, 4)
    assert not is_double_click(None, a, 0.5, 4)


def test_acao_por_botao():
    assert action_for("left") == "click"
    assert action_for("right") == "right_click"
