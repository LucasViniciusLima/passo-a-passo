import json
import zipfile

import pytest
from PIL import Image

from app.project.model import SCHEMA_VERSION, CircleStyle, Project, Step, Theme, default_text
from app.project.storage import PROJECT_FILE, ProjectWorkspace, load_passo, save_passo

EXEMPLO = {
    "schema": 1,
    "title": "Como emitir uma nota",
    "created_at": "2026-10-02T13:30:00Z",
    "theme": {
        "logo": None,
        "highlight_color": "#E53935",
        "margin_color": "#FFFFFF",
        "page_background": "#F5F5F5",
        "text_color": "#212121",
        "circle": {"radius": 28, "stroke": 4, "fill_opacity": 0.15},
    },
    "steps": [
        {
            "id": "8f1c",
            "image": "images/step-001.png",
            "action": "click",
            "button": "left",
            "point": [812, 440],
            "end_point": None,
            "monitor": 1,
            "scale": 1.5,
            "timestamp": 1.84,
            "text": "Passo 1: clique aqui",
            "circle_override": None,
            "crop": None,
            "blur_regions": [],
        }
    ],
}


def test_textos_padrao():
    assert default_text("click", 1) == "Passo 1: clique aqui"
    assert default_text("double_click", 2) == "Passo 2: clique duas vezes aqui"
    assert default_text("right_click", 3) == "Passo 3: clique com o botão direito aqui"


def test_ida_e_volta_do_exemplo_do_plano():
    project = Project.from_dict(EXEMPLO)
    assert project.title == "Como emitir uma nota"
    assert project.steps[0].point == (812, 440)
    assert project.steps[0].scale == 1.5
    # Campos novos entram com o valor padrão; o resto fica igual ao arquivo.
    data = project.to_dict()
    assert data["theme"].pop("spotlight") == {"mode": "janela", "blur": 6.0, "dim": 0.25, "margin": 40}
    for campo in ("focus_rect", "app_name", "window_title", "control_class", "element_name", "element_type"):
        assert data["steps"][0].pop(campo) is None
    assert data == EXEMPLO
    # E a ida e volta com os campos novos preserva tudo.
    assert Project.from_dict(project.to_dict()).to_dict() == project.to_dict()


def test_campos_de_app_sao_salvos():
    step = Step(image="a.png", point=(1, 1), app_name="Bloco de Notas",
                window_title="nota.txt - Bloco de Notas", control_class="RichEditD2DPT")
    assert Step.from_dict(step.to_dict()) == step


def test_tema_sem_spotlight_ou_desligado():
    assert Theme.from_dict({}).spotlight.mode == "janela"
    # Formato da versão anterior, só com "enabled".
    theme = Theme.from_dict({"spotlight": {"enabled": False, "blur": 3}})
    assert (theme.spotlight.mode, theme.spotlight.blur, theme.spotlight.dim) == ("desligado", 3.0, 0.25)
    assert Theme.from_dict({"spotlight": {"enabled": True}}).spotlight.mode == "janela"
    assert Theme.from_dict({"spotlight": {"mode": "circulo"}}).spotlight.mode == "circulo"
    assert Theme.from_dict({"spotlight": {"mode": "invalido"}}).spotlight.mode == "janela"


def test_texto_com_local_do_clique():
    assert default_text("click", 2, "No Bloco de Notas") == "Passo 2: No Bloco de Notas, clique aqui"
    assert default_text("double_click", 3, "Na Área de Trabalho") == (
        "Passo 3: Na Área de Trabalho, clique duas vezes aqui"
    )
    assert default_text("right_click", 4, "No Google Chrome") == (
        "Passo 4: No Google Chrome, clique com o botão direito aqui"
    )
    assert default_text("click", 5, None) == "Passo 5: clique aqui"


def test_valores_padrao_do_tema():
    theme = Theme.from_dict({})
    assert theme.highlight_color == "#E53935"
    assert theme.circle == CircleStyle(28, 4, 0.15)


def test_circle_override_por_passo():
    project = Project()
    step = Step(image="images/a.png", point=(1, 2), circle_override=CircleStyle(40, 6, 0.3))
    assert project.circle_for(step).radius == 40
    data = Step.from_dict(step.to_dict())
    assert data.circle_override == CircleStyle(40, 6, 0.3)


def test_schema_mais_novo_e_recusado():
    with pytest.raises(ValueError):
        Project.from_dict({**EXEMPLO, "schema": SCHEMA_VERSION + 1})


def _workspace_com_passos(tmp_path, n=2):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    for i in range(n):
        rel, path = ws.next_image_path()
        Image.new("RGB", (64, 48), (i * 40, 0, 0)).save(path)
        ws.add_step(Step(image=rel, point=(10 + i, 20), text=default_text("click", i + 1)))
    return ws


def test_workspace_salva_a_cada_passo(tmp_path):
    ws = _workspace_com_passos(tmp_path, 2)
    data = json.loads((ws.root / PROJECT_FILE).read_text(encoding="utf-8"))
    assert [s["image"] for s in data["steps"]] == ["images/step-001.png", "images/step-002.png"]


def test_escrita_e_leitura_do_passo(tmp_path):
    ws = _workspace_com_passos(tmp_path, 3)
    ws.project.steps[1].text = "Passo 2: clique em Salvar"
    dest = ws.save_to(tmp_path / "saida" / "tutorial.passo")

    with zipfile.ZipFile(dest) as zf:
        names = set(zf.namelist())
    assert names == {PROJECT_FILE, "images/step-001.png", "images/step-002.png", "images/step-003.png"}

    loaded = load_passo(dest, tmp_path / "aberto")
    assert loaded.to_dict() == ws.project.to_dict()
    with Image.open(tmp_path / "aberto" / "images/step-002.png") as img:
        assert img.getpixel((0, 0)) == (40, 0, 0)  # PNG original, sem anotação


def test_salvar_falha_se_imagem_sumiu(tmp_path):
    project = Project(steps=[Step(image="images/nao-existe.png", point=(0, 0))])
    with pytest.raises(FileNotFoundError):
        save_passo(project, tmp_path, tmp_path / "x.passo")


def test_leitura_recusa_caminho_fora_da_pasta(tmp_path):
    ruim = tmp_path / "ruim.passo"
    with zipfile.ZipFile(ruim, "w") as zf:
        zf.writestr(PROJECT_FILE, json.dumps(EXEMPLO))
        zf.writestr("../fora.txt", "x")
    with pytest.raises(ValueError):
        load_passo(ruim, tmp_path / "destino")
