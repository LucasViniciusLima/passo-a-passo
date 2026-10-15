"""Modelo de dados do projeto .passo (schema 1)."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

SCHEMA_VERSION = 1

ACTIONS = ("click", "double_click", "right_click", "drag", "key")

_ACOES = {
    "click": "clique aqui",
    "double_click": "clique duas vezes aqui",
    "right_click": "clique com o botão direito aqui",
    "drag": "arraste daqui até ali",
}


_VERBOS = {
    "click": "Clique",
    "double_click": "Clique duas vezes",
    "right_click": "Clique com o botão direito",
    "drag": "Arraste",
}

# Tipos de elemento que viram "no <tipo> <nome>" / "na <tipo> <nome>".
_FEMININOS = {
    "caixa de seleção", "lista suspensa", "aba", "pasta", "célula", "lista", "imagem",
    "barra de rolagem", "barra de ferramentas", "barra de status", "barra de menus", "tabela",
}
_NOMEADOS = {
    "botão", "campo", "caixa de seleção", "lista suspensa", "item de menu", "menu", "aba", "link",
    "item", "célula", "pasta", "arquivo", "atalho", "botão de opção", "controle deslizante",
    "cabeçalho", "cabeçalho de coluna", "lista", "seletor numérico", "calendário",
}
# Elementos sem tipo útil no texto, mas cujo nome ajuda: "Clique em <nome>".
_SO_NOME = {"texto", "imagem"}

MAX_NOME = 40


def short_name(name: str, limit: int = MAX_NOME) -> str:
    name = " ".join(name.split())
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def default_text(
    action: str,
    number: int,
    place: str | None = None,
    element_name: str | None = None,
    element_type: str | None = None,
    key: str | None = None,
    count: int = 1,
) -> str:
    """Texto padrão do passo.

    place é o local do clique, ex.: "No Bloco de Notas". Com o elemento (UI Automation)
    o texto fica natural: "Clique no botão Salvar no Bloco de Notas".
    """
    sufixo = f" {place[0].lower()}{place[1:]}" if place else ""
    if action == "key":
        vezes = f" {count} vezes" if count > 1 else ""
        return f"Passo {number}: Pressione {key or 'Enter'}{vezes}{sufixo}"
    verbo = _VERBOS.get(action, _VERBOS["click"])
    nome = short_name(element_name) if element_name else None

    if element_type == "campo de senha":
        return f"Passo {number}: {verbo} no campo de senha{sufixo}"
    if nome and element_type == "menu" and action == "click":
        return f"Passo {number}: Abra o menu {nome}{sufixo}"
    if nome and element_type in _NOMEADOS:
        artigo = "na" if element_type in _FEMININOS else "no"
        return f"Passo {number}: {verbo} {artigo} {element_type} {nome}{sufixo}"
    if nome and element_type in _SO_NOME:
        return f"Passo {number}: {verbo} em {nome}{sufixo}"

    acao = _ACOES.get(action, _ACOES["click"])
    if place:
        return f"Passo {number}: {place}, {acao}"
    return f"Passo {number}: {acao}"


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _now_iso() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


@dataclass
class CircleStyle:
    radius: int = 28
    stroke: int = 4
    fill_opacity: float = 0.15

    @classmethod
    def from_dict(cls, d: dict | None) -> CircleStyle:
        d = d or {}
        return cls(
            radius=int(d.get("radius", 28)),
            stroke=int(d.get("stroke", 4)),
            fill_opacity=float(d.get("fill_opacity", 0.15)),
        )


SPOTLIGHT_MODES = ("janela", "circulo", "desligado")


@dataclass
class SpotlightStyle:
    """Destaque do clique: o que está fora da área em foco fica desfocado e escurecido.

    mode: "janela" (a janela clicada fica nítida), "circulo" (só em volta do clique)
    ou "desligado".
    """

    mode: str = "janela"
    blur: float = 6.0  # raio do GaussianBlur, em px
    dim: float = 0.25  # 0 = sem escurecer, 1 = preto
    margin: int = 40  # modo círculo: área nítida = raio do círculo + margin

    @property
    def enabled(self) -> bool:
        return self.mode in SPOTLIGHT_MODES and self.mode != "desligado"

    @classmethod
    def from_dict(cls, d: dict | None) -> SpotlightStyle:
        d = d or {}
        base = cls()
        mode = d.get("mode")
        if mode not in SPOTLIGHT_MODES:
            # Arquivos da versão anterior tinham só "enabled".
            mode = "desligado" if d.get("enabled") is False else base.mode
        return cls(
            mode=mode,
            blur=float(d.get("blur", base.blur)),
            dim=float(d.get("dim", base.dim)),
            margin=int(d.get("margin", base.margin)),
        )


@dataclass
class Theme:
    logo: str | None = None
    highlight_color: str = "#E53935"
    margin_color: str = "#FFFFFF"
    page_background: str = "#F5F5F5"
    text_color: str = "#212121"
    circle: CircleStyle = field(default_factory=CircleStyle)
    spotlight: SpotlightStyle = field(default_factory=SpotlightStyle)

    @classmethod
    def from_dict(cls, d: dict | None) -> Theme:
        d = d or {}
        base = cls()
        return cls(
            logo=d.get("logo"),
            highlight_color=d.get("highlight_color", base.highlight_color),
            margin_color=d.get("margin_color", base.margin_color),
            page_background=d.get("page_background", base.page_background),
            text_color=d.get("text_color", base.text_color),
            circle=CircleStyle.from_dict(d.get("circle")),
            spotlight=SpotlightStyle.from_dict(d.get("spotlight")),
        )


@dataclass
class Step:
    image: str
    point: tuple[int, int]
    action: str = "click"
    button: str = "left"
    end_point: tuple[int, int] | None = None
    monitor: int = 1
    scale: float = 1.0
    timestamp: float = 0.0
    text: str = ""
    circle_override: CircleStyle | None = None
    crop: list[int] | None = None
    blur_regions: list[list[int]] = field(default_factory=list)
    # Janela clicada (mais a dona, se houver), em pixels da imagem: [x, y, largura, altura].
    focus_rect: list[int] | None = None
    # Onde o clique aconteceu (opcionais: projetos antigos não têm).
    app_name: str | None = None
    window_title: str | None = None
    control_class: str | None = None
    element_name: str | None = None
    element_type: str | None = None
    # Passos de teclado (action "key"): só "Tab", "Shift+Tab" ou "Enter", e quantas vezes seguidas.
    key: str | None = None
    count: int = 1
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "image": self.image,
            "action": self.action,
            "button": self.button,
            "point": list(self.point),
            "end_point": list(self.end_point) if self.end_point else None,
            "monitor": self.monitor,
            "scale": self.scale,
            "timestamp": self.timestamp,
            "text": self.text,
            "circle_override": asdict(self.circle_override) if self.circle_override else None,
            "crop": self.crop,
            "blur_regions": self.blur_regions,
            "focus_rect": self.focus_rect,
            "app_name": self.app_name,
            "window_title": self.window_title,
            "control_class": self.control_class,
            "element_name": self.element_name,
            "element_type": self.element_type,
        }
        if self.action == "key":  # passos de clique continuam com o mesmo formato de antes
            data["key"] = self.key
            data["count"] = self.count
        return data

    @classmethod
    def from_dict(cls, d: dict) -> Step:
        end = d.get("end_point")
        override = d.get("circle_override")
        return cls(
            id=str(d.get("id") or _new_id()),
            image=d["image"],
            action=d.get("action", "click"),
            button=d.get("button", "left"),
            point=(int(d["point"][0]), int(d["point"][1])),
            end_point=(int(end[0]), int(end[1])) if end else None,
            monitor=int(d.get("monitor", 1)),
            scale=float(d.get("scale", 1.0)),
            timestamp=float(d.get("timestamp", 0.0)),
            text=d.get("text", ""),
            circle_override=CircleStyle.from_dict(override) if override else None,
            crop=d.get("crop"),
            blur_regions=list(d.get("blur_regions") or []),
            focus_rect=[int(v) for v in d["focus_rect"]] if d.get("focus_rect") else None,
            app_name=d.get("app_name"),
            window_title=d.get("window_title"),
            control_class=d.get("control_class"),
            element_name=d.get("element_name"),
            element_type=d.get("element_type"),
            key=d.get("key"),
            count=int(d.get("count") or 1),
        )


@dataclass
class Project:
    title: str = "Novo tutorial"
    created_at: str = field(default_factory=_now_iso)
    theme: Theme = field(default_factory=Theme)
    steps: list[Step] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "title": self.title,
            "created_at": self.created_at,
            "theme": asdict(self.theme),
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        d = migrate(d)
        return cls(
            title=d.get("title", "Novo tutorial"),
            created_at=d.get("created_at") or _now_iso(),
            theme=Theme.from_dict(d.get("theme")),
            steps=[Step.from_dict(s) for s in d.get("steps", [])],
        )

    def circle_for(self, step: Step) -> CircleStyle:
        return step.circle_override or self.theme.circle


_NUMERO = re.compile(r"^Passo \d+:")


def renumber_steps(steps: list[Step]) -> None:
    """Refaz o "Passo N:" do começo de cada texto conforme a posição atual."""
    for n, step in enumerate(steps, start=1):
        step.text = _NUMERO.sub(f"Passo {n}:", step.text, count=1)


def migrate(d: dict) -> dict:
    """Atualiza dicionários de versões antigas para o schema atual."""
    schema = int(d.get("schema", 1))
    if schema > SCHEMA_VERSION:
        raise ValueError(f"Projeto criado por uma versão mais nova do app (schema {schema}).")
    # Por enquanto só existe o schema 1; migrações futuras entram aqui.
    return d
