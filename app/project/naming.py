"""Nomes de arquivo: título automático, nome seguro e sufixo (2), (3) sem sobrescrever."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from app.project.model import Project

DEFAULT_TITLE = "Novo tutorial"


def safe_filename(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip().strip(".")
    return name or "tutorial"


def _recorded_at(project: Project) -> datetime:
    try:
        return datetime.fromisoformat(project.created_at).astimezone()
    except (TypeError, ValueError):
        return datetime.now()


def auto_title(project: Project, when: datetime | None = None) -> str:
    """"Tutorial <app do primeiro passo> AAAA-MM-DD HHhMM" (sem app: só a data)."""
    when = when or _recorded_at(project)
    app = project.steps[0].app_name if project.steps else None
    app = " ".join(app.split()) if app else ""
    parts = ["Tutorial", app, when.strftime("%Y-%m-%d %Hh%M")]
    return safe_filename(" ".join(p for p in parts if p))


def unique_path(folder: str | Path, stem: str, suffix: str) -> Path:
    """folder/stem.suffix, ou "stem (2).suffix", "stem (3).suffix"… se já existir."""
    folder = Path(folder)
    path = folder / f"{stem}{suffix}"
    n = 2
    while path.exists():
        path = folder / f"{stem} ({n}){suffix}"
        n += 1
    return path
