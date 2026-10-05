from app.capture.apps import AppInfo, describe_app
from app.capture.base import ElementInfo, ElementInspector
from app.capture.coords import Monitor
from app.project.storage import ProjectWorkspace
from app.recorder.worker import CaptureWorker
from app.capture.base import ClickEvent, ScreenGrabber
from PIL import Image


def test_executaveis_conhecidos():
    assert describe_app(r"C:\Windows\System32\notepad.exe", "Notepad", "Sem título - Bloco de Notas") == AppInfo(
        "Bloco de Notas", "No"
    )
    assert describe_app(r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Chrome_WidgetWin_1",
                        "Chamado - Google Chrome").place == "No Google Chrome"
    assert describe_app(r"C:\x\MSEDGE.EXE", None, None).place == "No Microsoft Edge"


def test_explorer_por_classe_da_janela():
    exe = r"C:\Windows\explorer.exe"
    assert describe_app(exe, "Progman", "").place == "Na Área de Trabalho"
    assert describe_app(exe, "WorkerW", "").place == "Na Área de Trabalho"
    assert describe_app(exe, "Shell_TrayWnd", "").place == "Na Barra de Tarefas"
    assert describe_app(exe, "CabinetWClass", "passo-a-passo-desktop").place == (
        "No Explorador de Arquivos (passo-a-passo-desktop)"
    )


def test_contexto_do_titulo_com_moderacao():
    notepad = r"C:\Windows\notepad.exe"
    assert describe_app(notepad, None, "*nota.txt - Bloco de Notas").place == "No Bloco de Notas (nota.txt)"
    assert describe_app(notepad, None, "Sem título - Bloco de Notas").context is None
    exe = r"C:\Windows\explorer.exe"
    assert describe_app(exe, "CabinetWClass", "saida_tutorial \u2013 Explorador de Arquivos").context == "saida_tutorial"
    longo = "x" * 80 + ".txt - Bloco de Notas"
    assert describe_app(notepad, None, longo).context is None
    # Navegador: título da página não entra no texto.
    assert describe_app(r"C:\chrome.exe", None, "Minha conta - Google Chrome").context is None


def test_apps_desconhecidos():
    assert describe_app(None, None, "Algo") is None
    assert describe_app(r"C:\Apps\sistema.exe", None, "Cadastro - Sistema ERP").place == "No app Sistema ERP"
    assert describe_app(r"C:\Apps\sistema.exe", None, "").place == "No app Sistema"
    assert describe_app(r"C:\Windows\ApplicationFrameHost.exe", None, "Calculadora").place == "No app Calculadora"


class _Inspector(ElementInspector):
    def inspect(self, x, y):
        return ElementInfo(r"C:\Windows\notepad.exe", "nota.txt - Bloco de Notas", "Notepad", "RichEditD2DPT")


class _Grabber(ScreenGrabber):
    def monitors(self):
        return [Monitor(1, 0, 0, 200, 100)]

    def grab(self, monitor):
        return Image.new("RGB", (200, 100), "white")


def test_worker_gera_texto_com_app(tmp_path):
    ws = ProjectWorkspace(root=tmp_path)
    worker = CaptureWorker(ws, _Grabber(), t0=0, double_click=(0.5, 4), inspector=_Inspector())
    worker._process(ClickEvent(10, 10, "left", 1.0))
    worker._process(ClickEvent(11, 10, "left", 1.2))  # duplo clique
    worker._process(ClickEvent(50, 50, "right", 3.0))
    a, b = ws.project.steps
    assert a.text == "Passo 1: No Bloco de Notas (nota.txt), clique duas vezes aqui"
    assert b.text == "Passo 2: No Bloco de Notas (nota.txt), clique com o botão direito aqui"
    assert (b.app_name, b.window_title, b.control_class) == (
        "Bloco de Notas", "nota.txt - Bloco de Notas", "RichEditD2DPT"
    )
