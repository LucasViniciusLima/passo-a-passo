from PIL import Image

from app.project.model import CircleStyle, Project, Step
from app.render.annotate import annotate_step, draw_circle, scaled_style

VERMELHO = (0xE5, 0x39, 0x35)
FUNDO = (255, 255, 255)
ESTILO = CircleStyle(radius=28, stroke=4, fill_opacity=0.15)


def _perto(a, b, tol=3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _misturado(fundo, cor, alpha):
    return tuple(round(f * (1 - alpha) + c * alpha) for f, c in zip(fundo, cor))


def test_circulo_borda_preenchimento_e_fora():
    img = Image.new("RGB", (200, 200), FUNDO)
    out = draw_circle(img, (100, 100), ESTILO, "#E53935")

    assert out.size == img.size and out.mode == "RGB"
    assert img.getpixel((100, 100)) == FUNDO  # original intacta
    # Centro: preenchimento a 15%.
    assert _perto(out.getpixel((100, 100)), _misturado(FUNDO, VERMELHO, 0.15))
    # Meio da borda (raio externo 28, borda de 4 px para dentro).
    for p in [(126, 100), (74, 100), (100, 126), (100, 74)]:
        assert _perto(out.getpixel(p), VERMELHO), p
    # Fora do círculo nada muda.
    for p in [(100, 131), (131, 100), (0, 0), (199, 199)]:
        assert out.getpixel(p) == FUNDO, p


def test_circulo_na_borda_da_imagem_nao_quebra():
    img = Image.new("RGB", (50, 50), FUNDO)
    out = draw_circle(img, (0, 0), ESTILO, "#E53935")
    assert _perto(out.getpixel((0, 26)), VERMELHO)
    assert out.getpixel((49, 49)) == FUNDO


def test_preserva_rgba():
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 255))
    assert draw_circle(img, (50, 50), ESTILO, "#E53935").mode == "RGBA"


def test_escala_hidpi():
    s = scaled_style(ESTILO, 1.5)
    assert (s.radius, s.stroke, s.fill_opacity) == (42, 6, 0.15)
    assert scaled_style(ESTILO, 0) == ESTILO


def _xadrez(w=400, h=300):
    """Imagem com detalhes finos, para o desfoque fazer diferença."""
    img = Image.new("RGB", (w, h))
    img.putdata([(255, 255, 255) if (x // 4 + y // 4) % 2 else (30, 60, 90) for y in range(h) for x in range(w)])
    return img


def test_spotlight_desfoca_fora_e_preserva_dentro():
    img = _xadrez()
    project = Project()
    project.theme.spotlight.mode = "circulo"  # blur 6, escurece 25%, margem 40
    step = Step(image="x.png", point=(200, 150))
    out = annotate_step(img, step, project)
    # Dentro da área nítida (raio 28 + 40), fora do círculo vermelho: igual ao original.
    for p in [(200 + 40, 150), (200, 150 - 45), (200 - 50, 150)]:
        assert out.getpixel(p) == img.getpixel(p), p
    # Longe do clique: desfocado e escurecido.
    for p in [(10, 10), (390, 290), (20, 280)]:
        orig, novo = img.getpixel(p), out.getpixel(p)
        assert novo != orig, p
        assert max(novo) <= 255 * 0.75 + 1, p  # 25% mais escuro, no máximo


def test_spotlight_desligado_so_desenha_circulo():
    img = _xadrez()
    project = Project()
    project.theme.spotlight.mode = "desligado"
    out = annotate_step(img, Step(image="x.png", point=(200, 150)), project)
    assert out.getpixel((10, 10)) == img.getpixel((10, 10))


def test_annotate_step_usa_tema_e_escala():
    project = Project()
    project.theme.spotlight.mode = "desligado"
    project.theme.highlight_color = "#1E88E5"
    step = Step(image="x.png", point=(100, 100), scale=2.0)
    out = annotate_step(Image.new("RGB", (300, 300), FUNDO), step, project)
    # Raio 56 a 200%: a borda fica perto de x = 100 + 56 - 4.
    assert _perto(out.getpixel((152, 100)), (0x1E, 0x88, 0xE5))
    assert out.getpixel((100, 160)) == FUNDO
