"""Inspetor com UI Automation (comtypes): nome e tipo do botão ou campo clicado.

As consultas rodam numa thread própria, com COM inicializado nela e o objeto
IUIAutomation reutilizado. Quem chama espera no máximo `timeout`; se o app sob o
clique travar, a consulta é abandonada e vale só o resultado Win32.
"""

from __future__ import annotations

import queue
import re
import threading
from concurrent.futures import Future
from dataclasses import replace

from app.capture.base import ElementInfo, ElementInspector

# ControlType do UIA -> nome em pt-BR usado nos textos.
CONTROL_TYPES = {
    50000: "botão",
    50001: "calendário",
    50002: "caixa de seleção",
    50003: "lista suspensa",
    50004: "campo",
    50005: "link",
    50006: "imagem",
    50007: "item",
    50008: "lista",
    50009: "menu",
    50010: "barra de menus",
    50011: "item de menu",
    50012: "barra de progresso",
    50013: "botão de opção",
    50014: "barra de rolagem",
    50015: "controle deslizante",
    50016: "seletor numérico",
    50017: "barra de status",
    50018: "grupo de abas",
    50019: "aba",
    50020: "texto",
    50021: "barra de ferramentas",
    50022: "dica",
    50023: "árvore",
    50024: "item",
    50025: "personalizado",
    50026: "grupo",
    50027: "alça",
    50028: "tabela",
    50029: "célula",
    50030: "documento",
    50031: "botão",
    50032: "janela",
    50033: "painel",
    50034: "cabeçalho",
    50035: "cabeçalho de coluna",
    50036: "tabela",
    50037: "barra de título",
    50038: "separador",
    50039: "zoom semântico",
    50040: "barra de aplicativos",
}

_EDIT, _IMAGE, _TEXT = 50004, 50006, 50020
_LIST_ITEM, _TREE_ITEM, _MENU_ITEM, _MENU_BAR = 50007, 50024, 50011, 50010
# Partes internas (texto, ícone, nome editável) cedem lugar ao item ou botão que as contém.
_LEAVES = {_EDIT, _IMAGE, _TEXT}
_CONTAINERS = {50000, 50002, 50005, 50007, 50011, 50013, 50019, 50024, 50029, 50031}

MAX_STORED_NAME = 200
MAX_FOCUS_AREA = 800 * 600
_RPC_E_CHANGED_MODE = -2147417850


def _clean(name: str | None) -> str | None:
    if not name:
        return None
    first = name.strip().splitlines()[0].strip() if name.strip() else ""
    return first[:MAX_STORED_NAME] or None


# Sufixos de estado que o Windows e os navegadores acrescentam ao nome.
_SUFIXOS = [
    re.compile(r"\s*-\s*\d+\s+janelas?\s+em\s+execução", re.IGNORECASE),
    re.compile(r"\s*-?\s*\d+\s+running\s+windows?", re.IGNORECASE),
    re.compile(r"\s*\((fixad[oa]|pinned)\)\s*$", re.IGNORECASE),
    re.compile(r"\s+(fixad[oa]|pinned)\s*$", re.IGNORECASE),
]


def tidy_name(name: str | None) -> str | None:
    """Tira estados ("fixado", "1 janela em execução") e nomes repetidos ("X X")."""
    name = _clean(name)
    if not name:
        return None
    # Links de resultados de busca trazem a URL junto: "Título https://site › ...".
    name = re.split(r"\s+https?://", name, maxsplit=1)[0].strip()
    # O Chrome junta "Título ... Site": fica só o título.
    name = re.split(r"\s*(?:\.\.\.|…)(?:\s+|$)", name, maxsplit=1)[0].strip()
    for _ in range(2):
        for pattern in _SUFIXOS:
            name = pattern.sub("", name).strip()
    words = name.split()
    half = len(words) // 2
    if len(words) % 2 == 0 and half and [w.lower() for w in words[:half]] == [w.lower() for w in words[half:]]:
        name = " ".join(words[:half])
    return name or None


def _item_kind(item_type: str | None) -> str:
    """Itens do Explorer informam o tipo (ex.: "Pasta de arquivos")."""
    t = (item_type or "").lower()
    if "pasta" in t or "folder" in t:
        return "pasta"
    if "atalho" in t or "shortcut" in t:
        return "atalho"
    return "arquivo" if t else "item"


class UIAElementInspector(ElementInspector):
    def __init__(self, fallback: ElementInspector, timeout: float = 0.15) -> None:
        self.fallback = fallback
        self.timeout = timeout
        self._requests: queue.Queue = queue.Queue()
        # Até a inicialização terminar, as consultas usam só o fallback.
        self._pending: Future = Future()
        self._thread = threading.Thread(target=self._loop, name="uia", daemon=True)
        self._thread.start()

    # --- thread do UIA ---------------------------------------------------

    def _init_com(self) -> None:
        import comtypes
        import comtypes.client

        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError as exc:
            # O import do comtypes já inicializa o COM nesta thread; isso basta.
            if exc.winerror != _RPC_E_CHANGED_MODE:
                raise
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as uia

        self._uia = comtypes.CoCreateInstance(
            uia.CUIAutomation._reg_clsid_, interface=uia.IUIAutomation, clsctx=comtypes.CLSCTX_INPROC_SERVER
        )
        self._walker = self._uia.ControlViewWalker
        self._point = uia.tagPOINT

    def _loop(self) -> None:
        ready = self._pending
        try:
            self._init_com()
        except Exception as exc:  # sem UIA: fica só o Win32
            ready.set_exception(exc)
            return
        ready.set_result({})
        while True:
            query, fut = self._requests.get()
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                fut.set_result(query())
            except Exception as exc:
                fut.set_exception(exc)

    def _parent(self, element):
        try:
            parent = self._walker.GetParentElement(element)
            return parent if parent else None
        except Exception:
            return None

    def _query(self, x: int, y: int) -> dict:
        element = self._uia.ElementFromPoint(self._point(x, y))
        ctype = element.CurrentControlType
        if ctype in _LEAVES:
            parent = self._parent(element)
            if parent is not None and parent.CurrentControlType in _CONTAINERS:
                element, ctype = parent, parent.CurrentControlType

        if ctype == _EDIT and element.CurrentIsPassword:
            # Nunca guardar nada de um campo de senha além do tipo.
            return {"element_name": None, "element_type": "campo de senha", "automation_id": None}

        kind = CONTROL_TYPES.get(ctype)
        if ctype == _MENU_ITEM:
            parent = self._parent(element)
            if parent is not None and parent.CurrentControlType == _MENU_BAR:
                kind = "menu"
        elif ctype == _LIST_ITEM:
            kind = _item_kind(element.CurrentItemType)
        return {
            "element_name": tidy_name(element.CurrentName),
            "element_type": kind,
            "automation_id": _clean(element.CurrentAutomationId),
        }

    def _focused_center(self) -> tuple[int, int] | None:
        rect = self._uia.GetFocusedElement().CurrentBoundingRectangle
        w, h = rect.right - rect.left, rect.bottom - rect.top
        # Elementos sem tamanho ou do tamanho da tela (documento, janela) não dizem onde está o foco.
        if w <= 0 or h <= 0 or w * h > MAX_FOCUS_AREA:
            return None
        return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2

    def _ask(self, query):
        """Roda a consulta na thread do UIA; None se não respondeu a tempo ou falhou."""
        if not self._pending.done() or not self._thread.is_alive():
            return None  # ainda iniciando, travado numa consulta anterior ou sem UIA
        fut: Future = Future()
        self._pending = fut
        self._requests.put((query, fut))
        try:
            return fut.result(timeout=self.timeout)
        except Exception:
            return None

    # --- chamado pelo worker ---------------------------------------------

    def inspect(self, x: int, y: int) -> ElementInfo:
        base = self.fallback.inspect(x, y)
        result = self._ask(lambda: self._query(x, y))
        return replace(base, **result) if result else base

    def focus_point(self) -> tuple[int, int] | None:
        return self._ask(self._focused_center) or self.fallback.focus_point()
