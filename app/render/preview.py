"""Prévia simples: um PNG por passo com o círculo e o texto numa faixa embaixo."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.project.model import Project, Step
from app.render.annotate import annotate_step

_FONTS = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")


def _font(size: int) -> ImageFont.ImageFont:
    for name in _FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and draw.textlength(candidate, font=font) > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def render_step_preview(image: Image.Image, step: Step, project: Project) -> Image.Image:
    """Captura anotada com uma faixa embaixo contendo o texto do passo."""
    shot = annotate_step(image, step, project).convert("RGB")
    theme = project.theme
    font_size = max(16, shot.width // 60)
    pad = font_size
    font = _font(font_size)
    measure = ImageDraw.Draw(shot)
    lines = _wrap(measure, step.text, font, shot.width - 2 * pad)
    line_h = round(font_size * 1.4)
    band_h = 2 * pad + line_h * len(lines)

    out = Image.new("RGB", (shot.width, shot.height + band_h), theme.margin_color)
    out.paste(shot, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.rectangle((0, shot.height, shot.width, shot.height + 3), fill=theme.highlight_color)
    y = shot.height + pad
    for line in lines:
        draw.text((pad, y), line, fill=theme.text_color, font=font)
        y += line_h
    return out


def export_step_images(project: Project, root: str | Path, out_dir: str | Path) -> list[Path]:
    """Grava passo-001.png, passo-002.png... em out_dir. root é a pasta das capturas."""
    root, out_dir = Path(root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for n, step in enumerate(project.steps, start=1):
        with Image.open(root / step.image) as img:
            preview = render_step_preview(img, step, project)
        path = out_dir / f"passo-{n:03d}.png"
        preview.save(path, "PNG")
        paths.append(path)
    return paths
