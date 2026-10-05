"""Nomes amigáveis de aplicativos para os textos dos passos."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PureWindowsPath

# executável -> (nome, preposição usada no texto)
APPS: dict[str, tuple[str, str]] = {
    "explorer.exe": ("Explorador de Arquivos", "No"),
    "notepad.exe": ("Bloco de Notas", "No"),
    "chrome.exe": ("Google Chrome", "No"),
    "msedge.exe": ("Microsoft Edge", "No"),
    "firefox.exe": ("Mozilla Firefox", "No"),
    "brave.exe": ("Brave", "No"),
    "opera.exe": ("Opera", "No"),
    "winword.exe": ("Microsoft Word", "No"),
    "excel.exe": ("Microsoft Excel", "No"),
    "powerpnt.exe": ("Microsoft PowerPoint", "No"),
    "outlook.exe": ("Microsoft Outlook", "No"),
    "olk.exe": ("Microsoft Outlook", "No"),
    "onenote.exe": ("Microsoft OneNote", "No"),
    "ms-teams.exe": ("Microsoft Teams", "No"),
    "teams.exe": ("Microsoft Teams", "No"),
    "code.exe": ("Visual Studio Code", "No"),
    "mspaint.exe": ("Paint", "No"),
    "calculatorapp.exe": ("Calculadora", "Na"),
    "calc.exe": ("Calculadora", "Na"),
    "windowsterminal.exe": ("Terminal", "No"),
    "cmd.exe": ("Prompt de Comando", "No"),
    "powershell.exe": ("PowerShell", "No"),
    "pwsh.exe": ("PowerShell", "No"),
    "taskmgr.exe": ("Gerenciador de Tarefas", "No"),
    "systemsettings.exe": ("Configurações", "Nas"),
    "control.exe": ("Painel de Controle", "No"),
    "mmc.exe": ("Console de Gerenciamento", "No"),
    "whatsapp.exe": ("WhatsApp", "No"),
    "whatsapp.root.exe": ("WhatsApp", "No"),
    "slack.exe": ("Slack", "No"),
    "acrobat.exe": ("Adobe Acrobat", "No"),
    "acrord32.exe": ("Adobe Acrobat Reader", "No"),
    "snippingtool.exe": ("Ferramenta de Captura", "Na"),
    "photos.exe": ("Fotos", "No app"),
    "searchhost.exe": ("Pesquisa do Windows", "Na"),
    "startmenuexperiencehost.exe": ("Menu Iniciar", "No"),
    "shellexperiencehost.exe": ("Central de Ações", "Na"),
}

# Partes do Explorer que não são o Explorador de Arquivos, pela classe da janela raiz.
EXPLORER_CLASSES: dict[str, tuple[str, str]] = {
    "Progman": ("Área de Trabalho", "Na"),
    "WorkerW": ("Área de Trabalho", "Na"),
    "Shell_TrayWnd": ("Barra de Tarefas", "Na"),
    "Shell_SecondaryTrayWnd": ("Barra de Tarefas", "Na"),
    "NotifyIconOverflowWindow": ("Bandeja do sistema", "Na"),
}

# Apps cujo título "documento - App" traz o nome do arquivo aberto.
DOCUMENT_APPS = {"notepad.exe", "winword.exe", "excel.exe", "powerpnt.exe", "code.exe", "mspaint.exe"}

_SEM_NOME = {"sem título", "sem titulo", "untitled", "documento1", "pasta1", "apresentação1", "new tab", "nova guia"}
_MAX_CONTEXTO = 40
# O Windows 11 separa "documento – App" com travessão; versões antigas usam hífen.
_SEPARADOR = re.compile(r"\s[-\u2013\u2014]\s")


@dataclass(frozen=True)
class AppInfo:
    name: str
    preposition: str
    context: str | None = None

    @property
    def place(self) -> str:
        """Local do clique pronto para o texto, ex.: "No Bloco de Notas (nota.txt)"."""
        base = f"{self.preposition} {self.name}"
        return f"{base} ({self.context})" if self.context else base


def _document_from_title(title: str) -> str | None:
    doc = _SEPARADOR.split(title)[0].strip().lstrip("*").strip()
    if not doc or doc.lower() in _SEM_NOME or len(doc) > _MAX_CONTEXTO:
        return None
    return doc


def describe_app(exe_path: str | None, root_class: str | None, title: str | None) -> AppInfo | None:
    """Nome amigável do app a partir do executável, da classe da janela e do título."""
    title = (title or "").strip()
    exe = PureWindowsPath(exe_path).name.lower() if exe_path else ""
    if not exe:
        return None

    if exe == "explorer.exe":
        if root_class in EXPLORER_CLASSES:
            return AppInfo(*EXPLORER_CLASSES[root_class])
        folder = _document_from_title(title) if root_class == "CabinetWClass" else None
        return AppInfo(*APPS[exe], context=folder)

    if exe in APPS:
        context = _document_from_title(title) if exe in DOCUMENT_APPS else None
        return AppInfo(*APPS[exe], context=context)

    # Apps da loja rodam dentro do ApplicationFrameHost; o título é o nome do app.
    if exe == "applicationframehost.exe":
        return AppInfo(title, "No app") if title and len(title) <= _MAX_CONTEXTO else None

    stem = PureWindowsPath(exe).stem
    name = _SEPARADOR.split(title)[-1].strip() if title else ""
    if not name or len(name) > _MAX_CONTEXTO:
        name = stem[:1].upper() + stem[1:]
    return AppInfo(name, "No app")
