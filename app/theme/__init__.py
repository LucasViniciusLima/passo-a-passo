"""Identidade visual: logo e cores do tema, guardados dentro do projeto."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageColor

from app.project.model import Theme
from app.project.storage import ASSETS_DIR, ProjectWorkspace

LOGO_FILE = f"{ASSETS_DIR}/logo.png"
LOGO_MAX = 1024  # px no maior lado; logo maior que isso só pesa no arquivo
LOGO_FORMATS = "Imagens (*.png *.jpg *.jpeg *.svg)"

__all__ = ["Theme", "LOGO_FILE", "LOGO_FORMATS", "set_logo", "remove_logo", "contrast_ratio", "load_logo"]


def _svg_to_image(path: Path) -> Image.Image:
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ValueError("SVG inválido.")
    size = renderer.defaultSize()
    if size.isEmpty():
        size = QSize(512, 512)
    size.scale(LOGO_MAX, LOGO_MAX, Qt.AspectRatioMode.KeepAspectRatio)
    qimg = QImage(size, QImage.Format.Format_RGBA8888)
    qimg.fill(0)
    painter = QPainter(qimg)
    renderer.render(painter)
    painter.end()
    data = bytes(qimg.constBits())
    return Image.frombytes("RGBA", (qimg.width(), qimg.height()), data, "raw", "RGBA", qimg.bytesPerLine())


def set_logo(workspace: ProjectWorkspace, source: str | Path) -> str:
    """Copia a logo para dentro do projeto (assets/logo.png) e a define no tema.

    O projeto continua íntegro mesmo se o arquivo original for apagado depois.
    """
    source = Path(source)
    if source.suffix.lower() == ".svg":
        image = _svg_to_image(source)
    else:
        with Image.open(source) as img:
            image = img.convert("RGBA")
    image.thumbnail((LOGO_MAX, LOGO_MAX))
    dest = workspace.root / LOGO_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, "PNG")
    workspace.project.theme.logo = LOGO_FILE
    workspace.flush()
    return LOGO_FILE


def remove_logo(workspace: ProjectWorkspace) -> None:
    logo = workspace.project.theme.logo
    workspace.project.theme.logo = None
    workspace.flush()
    if logo:
        (workspace.root / logo).unlink(missing_ok=True)


def load_logo(project_root: str | Path, theme: Theme) -> Image.Image | None:
    if not theme.logo:
        return None
    path = Path(project_root) / theme.logo
    if not path.is_file():
        return None
    with Image.open(path) as img:
        return img.convert("RGBA")


def _luminance(color: str) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = ImageColor.getrgb(color)[:3]
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float:
    """Contraste WCAG entre duas cores (1 a 21). Abaixo de 4,5 o texto fica difícil de ler."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
