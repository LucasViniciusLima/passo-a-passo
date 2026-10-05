"""Fontes para os quadros (Pillow) e para o PDF (ReportLab)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_WIN_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
REGULAR = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
BOLD = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")


def font_path(bold: bool = False) -> Path | None:
    for name in BOLD if bold else REGULAR:
        for candidate in (_WIN_FONTS / name, Path(name)):
            if candidate.is_file():
                return candidate
    return None


@lru_cache(maxsize=64)
def pil_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    path = font_path(bold)
    if path is not None:
        return ImageFont.truetype(str(path), size)
    for name in BOLD if bold else REGULAR:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def wrap(text: str, width_of, max_width: float) -> list[str]:
    """Quebra o texto em linhas que caibam em max_width (width_of mede uma string)."""
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and width_of(candidate) > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines
