from PIL import Image

from app.project.model import Project, Step
from app.project.storage import ProjectWorkspace, open_passo
from app.render.preview import export_step_images, render_step_preview

VERMELHO = (0xE5, 0x39, 0x35)


def _perto(a, b, tol=3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _tutorial(tmp_path, n=3):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    for i in range(n):
        rel, path = ws.next_image_path()
        Image.new("RGB", (800, 450), (200, 220, 240)).save(path)
        ws.add_step(Step(image=rel, point=(100 + 50 * i, 200), text=f"Passo {i + 1}: clique aqui"))
    return ws


def test_reabre_passo_salvo(tmp_path):
    ws = _tutorial(tmp_path)
    dest = ws.save_to(tmp_path / "tutorial.passo")
    ws.cleanup()

    aberto = open_passo(dest)
    try:
        assert aberto.project.to_dict() == ws.project.to_dict()
        for step in aberto.project.steps:
            assert (aberto.root / step.image).is_file()
        # Editar e salvar de novo preserva as imagens.
        aberto.project.steps[0].text = "Passo 1: abra o menu"
        aberto.save_to(dest)
    finally:
        aberto.cleanup()
    de_novo = open_passo(dest)
    assert de_novo.project.steps[0].text == "Passo 1: abra o menu"
    de_novo.cleanup()


def test_previa_tem_circulo_e_faixa_de_texto():
    project = Project()
    step = Step(image="x.png", point=(100, 100), text="Passo 1: clique aqui")
    out = render_step_preview(Image.new("RGB", (800, 450), (0, 0, 0)), step, project)
    assert out.width == 800 and out.height > 450
    assert _perto(out.getpixel((126, 100)), VERMELHO)  # borda do círculo
    faixa = out.crop((0, 455, 800, out.height))
    cores = {c for _, c in faixa.getcolors(1_000_000)}
    assert (255, 255, 255) in cores  # fundo da faixa na cor da margem
    assert any(sum(c) < 300 for c in cores)  # texto escuro desenhado


def test_exporta_um_png_por_passo(tmp_path):
    ws = _tutorial(tmp_path, 3)
    paths = export_step_images(ws.project, ws.root, tmp_path / "saida")
    assert [p.name for p in paths] == ["passo-001.png", "passo-002.png", "passo-003.png"]
    with Image.open(paths[2]) as img:
        assert _perto(img.getpixel((200 + 26, 200)), VERMELHO)
