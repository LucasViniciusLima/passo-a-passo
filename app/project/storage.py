"""Leitura e escrita do arquivo .passo (ZIP com project.json e imagens)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from app.project.model import Project, Step

PROJECT_FILE = "project.json"
IMAGES_DIR = "images"
ASSETS_DIR = "assets"


def _dump(project: Project) -> str:
    return json.dumps(project.to_dict(), ensure_ascii=False, indent=2)


def save_passo(project: Project, source_dir: str | Path, dest: str | Path) -> Path:
    """Grava o projeto e os arquivos que ele referencia (lidos de source_dir) em dest."""
    source_dir = Path(source_dir)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    files = [s.image for s in project.steps]
    if project.theme.logo:
        files.append(project.theme.logo)
    tmp = dest.with_name(dest.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(PROJECT_FILE, _dump(project))
        for rel in dict.fromkeys(files):
            path = source_dir / rel
            if not path.is_file():
                raise FileNotFoundError(f"Arquivo do projeto não encontrado: {rel}")
            # PNG já é comprimido; guardar sem recompressão é mais rápido.
            zf.write(path, rel, compress_type=zipfile.ZIP_STORED)
    os.replace(tmp, dest)
    return dest


def load_passo(path: str | Path, extract_to: str | Path) -> Project:
    """Extrai o .passo em extract_to e devolve o projeto."""
    extract_to = Path(extract_to)
    extract_to.mkdir(parents=True, exist_ok=True)
    root = extract_to.resolve()
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not (root / name).resolve().is_relative_to(root):
                raise ValueError(f"Caminho inválido dentro do arquivo: {name}")
        zf.extractall(extract_to)
    data = json.loads((extract_to / PROJECT_FILE).read_text(encoding="utf-8"))
    return Project.from_dict(data)


class ProjectWorkspace:
    """Pasta temporária onde o projeto vive durante a gravação.

    O project.json é regravado a cada passo, para não perder nada se o app fechar.
    """

    def __init__(self, project: Project | None = None, root: str | Path | None = None):
        self.project = project or Project()
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix="passo-"))
        (self.root / IMAGES_DIR).mkdir(parents=True, exist_ok=True)
        self.flush()

    def next_image_path(self) -> tuple[str, Path]:
        """Caminho relativo e absoluto para a próxima captura."""
        n = len(self.project.steps) + 1
        while True:
            rel = f"{IMAGES_DIR}/step-{n:03d}.png"
            if not (self.root / rel).exists():
                return rel, self.root / rel
            n += 1

    def add_step(self, step: Step) -> None:
        self.project.steps.append(step)
        self.flush()

    def flush(self) -> None:
        target = self.root / PROJECT_FILE
        tmp = target.with_name(PROJECT_FILE + ".tmp")
        tmp.write_text(_dump(self.project), encoding="utf-8")
        os.replace(tmp, target)

    def save_to(self, dest: str | Path) -> Path:
        self.flush()
        return save_passo(self.project, self.root, dest)

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def open_passo(path: str | Path) -> ProjectWorkspace:
    """Abre um .passo salvo numa pasta temporária nova, pronto para revisar."""
    root = Path(tempfile.mkdtemp(prefix="passo-"))
    try:
        project = load_passo(path, root)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return ProjectWorkspace(project, root)
