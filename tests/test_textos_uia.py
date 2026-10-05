import threading
import time

import pytest

from app.capture.base import ElementInfo, ElementInspector
from app.capture.uia import UIAElementInspector, _item_kind
from app.project.model import Step, default_text

BLOCO = "No Bloco de Notas"
EXPLORER = "No Explorador de Arquivos"


@pytest.mark.parametrize(
    "action, place, name, kind, esperado",
    [
        ("click", BLOCO, "Salvar", "botão", "Passo 1: Clique no botão Salvar no Bloco de Notas"),
        ("click", None, "Nome do arquivo", "campo", "Passo 1: Clique no campo Nome do arquivo"),
        ("double_click", EXPLORER, "app", "pasta",
         "Passo 1: Clique duas vezes na pasta app no Explorador de Arquivos"),
        ("click", BLOCO, "Arquivo", "menu", "Passo 1: Abra o menu Arquivo no Bloco de Notas"),
        ("click", "No Google Chrome", "Configurações", "aba",
         "Passo 1: Clique na aba Configurações no Google Chrome"),
        ("right_click", "Na Área de Trabalho", "Lixeira", "item",
         "Passo 1: Clique com o botão direito no item Lixeira na Área de Trabalho"),
        ("click", None, "Lembrar senha", "caixa de seleção", "Passo 1: Clique na caixa de seleção Lembrar senha"),
        ("click", None, "Salvar como", "item de menu", "Passo 1: Clique no item de menu Salvar como"),
        ("click", None, "Bem-vindo", "texto", "Passo 1: Clique em Bem-vindo"),
    ],
)
def test_textos_por_tipo_e_acao(action, place, name, kind, esperado):
    assert default_text(action, 1, place, name, kind) == esperado


def test_menu_com_clique_direito_nao_vira_abra():
    assert default_text("right_click", 2, None, "Arquivo", "menu") == "Passo 2: Clique com o botão direito no menu Arquivo"


def test_campo_de_senha_nunca_tem_nome():
    assert default_text("click", 3, "No Google Chrome", "minhaSenha123", "campo de senha") == (
        "Passo 3: Clique no campo de senha no Google Chrome"
    )


def test_nome_longo_e_encurtado():
    texto = default_text("click", 1, None, "Um nome de botão muito comprido que passa do limite", "botão")
    nome = texto.removeprefix("Passo 1: Clique no botão ")
    assert len(nome) == 40 and nome.endswith("…")


@pytest.mark.parametrize("kind", [None, "painel", "janela", "grupo", "documento"])
def test_sem_nome_ou_tipo_generico_cai_para_o_app(kind):
    assert default_text("click", 4, BLOCO, None, "botão") == "Passo 4: No Bloco de Notas, clique aqui"
    assert default_text("click", 4, BLOCO, "Algo", kind) == "Passo 4: No Bloco de Notas, clique aqui"
    assert default_text("click", 4, None, "", "botão") == "Passo 4: clique aqui"


def test_campos_do_elemento_no_json():
    step = Step(image="a.png", point=(0, 0), element_name="Salvar", element_type="botão")
    assert Step.from_dict(step.to_dict()) == step
    antigo = step.to_dict()
    del antigo["element_name"], antigo["element_type"]
    assert Step.from_dict(antigo).element_name is None


def test_tipo_de_item_do_explorer():
    assert _item_kind("Pasta de arquivos") == "pasta"
    assert _item_kind("File folder") == "pasta"
    assert _item_kind("Atalho") == "atalho"
    assert _item_kind("Documento de Texto") == "arquivo"
    assert _item_kind("") == "item"


# --- fallback do inspetor UIA ---------------------------------------------


class _Win32(ElementInspector):
    def inspect(self, x, y):
        return ElementInfo(exe_path=r"C:\Windows\notepad.exe", window_title="nota.txt - Bloco de Notas")


class _FakeUIA(UIAElementInspector):
    """Substitui o COM por funções controladas pelo teste."""

    def __init__(self, query=None, init_error=None, timeout=0.15):
        self._fake_query = query
        self._init_error = init_error
        super().__init__(_Win32(), timeout=timeout)

    def _init_com(self):
        if self._init_error:
            raise self._init_error

    def _query(self, x, y):
        return self._fake_query(x, y)


def _pronto(inspector):
    inspector._pending.exception(timeout=2)  # espera a inicialização


def test_uia_preenche_nome_e_tipo():
    insp = _FakeUIA(lambda x, y: {"element_name": "Salvar", "element_type": "botão", "automation_id": "1"})
    _pronto(insp)
    info = insp.inspect(10, 10)
    assert (info.element_name, info.element_type, info.window_title) == ("Salvar", "botão", "nota.txt - Bloco de Notas")


def test_uia_indisponivel_usa_win32():
    insp = _FakeUIA(init_error=OSError("sem UIA"))
    insp._thread.join(2)
    info = insp.inspect(10, 10)
    assert info.element_name is None and info.exe_path.endswith("notepad.exe")


def test_uia_com_erro_usa_win32():
    def falha(x, y):
        raise RuntimeError("COM")

    insp = _FakeUIA(falha)
    _pronto(insp)
    assert insp.inspect(1, 1).element_name is None
    assert insp.inspect(1, 1).window_title == "nota.txt - Bloco de Notas"  # segue funcionando


def test_uia_lento_nao_trava_o_worker():
    liberar = threading.Event()

    def travado(x, y):
        liberar.wait(5)
        return {"element_name": "Tarde", "element_type": "botão", "automation_id": None}

    insp = _FakeUIA(travado, timeout=0.15)
    _pronto(insp)
    inicio = time.monotonic()
    assert insp.inspect(1, 1).element_name is None
    # Enquanto a consulta anterior não termina, nem espera: responde na hora com o Win32.
    assert insp.inspect(2, 2).element_name is None
    assert time.monotonic() - inicio < 0.5
    liberar.set()
    insp._pending.result(timeout=2)
    # Depois que o app destrava, o UIA volta a ser usado.
    assert insp.inspect(3, 3).element_name == "Tarde"


@pytest.mark.parametrize(
    "bruto, limpo",
    [
        ("Claude - 1 janela em execução fixado", "Claude"),
        ("Explorador de Arquivos - 2 janelas em execução fixado", "Explorador de Arquivos"),
        ("sqldeveloper fixado", "sqldeveloper"),
        ("Planilha de Ponto - Google Planilhas (fixada)", "Planilha de Ponto - Google Planilhas"),
        ("Mostrar Ícones Ocultos Mostrar ícones ocultos", "Mostrar Ícones Ocultos"),
        ("Salvar", "Salvar"),
        ("Speedtest by Ookla - Teste de Velocidade da ... Speedtest by Ookla https://www.speedtest.net › ...",
         "Speedtest by Ookla - Teste de Velocidade da"),
        ("  \n ", None),
        (None, None),
    ],
)
def test_limpeza_de_nomes(bruto, limpo):
    from app.capture.uia import tidy_name

    assert tidy_name(bruto) == limpo
