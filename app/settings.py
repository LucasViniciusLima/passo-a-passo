"""Preferências do usuário em %LOCALAPPDATA%\\PassoAPasso\\config.json.

Guarda a última pasta de cada diálogo, a pasta padrão dos tutoriais e as cores
de marca. A logo padrão fica ao lado, em logo_padrao.png.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

CONFIG_NAME = "config.json"
DEFAULT_LOGO_NAME = "logo_padrao.png"

# Diálogos que lembram a última pasta usada.
DIALOGS = ("salvar", "abrir", "exportar", "logo", "imagens")


def config_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PassoAPasso"


def config_path() -> Path:
    return config_dir() / CONFIG_NAME


def default_logo_path() -> Path:
    return config_dir() / DEFAULT_LOGO_NAME


def load() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict) -> None:
    """Grava a configuração; falhas de disco não podem derrubar o app."""
    target = config_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(CONFIG_NAME + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        pass


def _update(key: str, value) -> None:
    data = load()
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    save(data)


# --- pastas ---------------------------------------------------------------


def _existing_dir(value) -> Path | None:
    if isinstance(value, str) and value and Path(value).is_dir():
        return Path(value)
    return None


def default_dir() -> Path:
    """Pasta padrão dos tutoriais; sem configuração, a pasta Documentos."""
    return _existing_dir(load().get("default_dir")) or Path.home() / "Documents"


def set_default_dir(folder: str | Path | None) -> None:
    _update("default_dir", str(Path(folder)) if folder else None)


def last_dir(dialog: str) -> Path:
    """Última pasta usada neste diálogo ou, se ainda não houver, a pasta padrão."""
    return _existing_dir(load().get("last_dirs", {}).get(dialog)) or default_dir()


def remember_dir(dialog: str, folder: str | Path) -> None:
    data = load()
    last = data.get("last_dirs")
    if not isinstance(last, dict):
        last = {}
    last[dialog] = str(Path(folder))
    data["last_dirs"] = last
    save(data)


# --- marca -----------------------------------------------------------------

BRAND_COLORS = ("highlight_color", "margin_color", "page_background", "text_color")


def brand_colors() -> dict[str, str]:
    colors = load().get("brand_colors")
    if not isinstance(colors, dict):
        return {}
    return {k: v for k, v in colors.items() if k in BRAND_COLORS and isinstance(v, str)}


def remember_color(attr: str, value: str) -> None:
    if attr not in BRAND_COLORS:
        return
    colors = brand_colors()
    colors[attr] = value
    _update("brand_colors", colors)


def default_logo() -> Path | None:
    path = default_logo_path()
    return path if path.is_file() else None


def remember_logo(source: str | Path) -> None:
    """Copia a logo (já convertida para PNG) como padrão dos próximos tutoriais."""
    try:
        default_logo_path().parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, default_logo_path())
    except OSError:
        pass


def forget_logo() -> None:
    try:
        default_logo_path().unlink(missing_ok=True)
    except OSError:
        pass


# --- gravação ----------------------------------------------------------------


def keyboard_steps() -> bool:
    """Tab e Enter viram passos? Ligado por padrão."""
    value = load().get("keyboard_steps", True)
    return value if isinstance(value, bool) else True


def set_keyboard_steps(enabled: bool) -> None:
    _update("keyboard_steps", bool(enabled))
