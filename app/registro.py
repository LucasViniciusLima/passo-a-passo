"""Registro de ocorrências em %LOCALAPPDATA%\\PassoAPasso\\erros.log."""

from __future__ import annotations

from datetime import datetime

from app import settings

LOG_NAME = "erros.log"


def log_path():
    return settings.config_dir() / LOG_NAME


def registrar(message: str) -> None:
    """Acrescenta uma linha com data e hora; falhas de disco são ignoradas."""
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except OSError:
        pass
