"""Exportação para PDF com ReportLab.

A captura vai como imagem (já com o fundo em destaque); o círculo, o selo e os
textos são desenhados em vetor, nítidos em qualquer zoom.
"""

from __future__ import annotations

import io
import threading
from datetime import datetime
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, LETTER, landscape, portrait
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from app.export import Cancelled, PdfOptions, Progress, check_cancel
from app.project.model import Project
from app.render.annotate import scaled_style, spotlight_step
from app.render.fonts import font_path, wrap
from app.theme import load_logo

PAGE_SIZES = {"A4": A4, "Carta": LETTER}
MARGIN = 40  # pt
HEADER_H = 44
FOOTER_H = 30


def _register_fonts(preferred: str | None) -> tuple[str, str]:
    if preferred:
        return preferred, preferred if preferred != "Helvetica" else "Helvetica-Bold"
    regular, bold = font_path(False), font_path(True)
    if regular is None:
        return "Helvetica", "Helvetica-Bold"
    try:
        pdfmetrics.registerFont(TTFont("PassoRegular", str(regular)))
        pdfmetrics.registerFont(TTFont("PassoBold", str(bold or regular)))
    except Exception:
        return "Helvetica", "Helvetica-Bold"
    return "PassoRegular", "PassoBold"


def _format_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y")
    except ValueError:
        return iso[:10]


def _image_reader(image: Image.Image, quality: int) -> ImageReader:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return ImageReader(buf)


class _PdfWriter:
    def __init__(self, project: Project, root: Path, dest: Path, options: PdfOptions) -> None:
        self.project = project
        self.root = root
        self.options = options
        self.theme = project.theme
        size = PAGE_SIZES.get(options.page_size, A4)
        orientation = options.orientation
        if orientation not in ("retrato", "paisagem"):
            # Capturas são largas: com 1 passo por página, paisagem aproveita melhor a folha.
            orientation = "paisagem" if options.steps_per_page != 2 else "retrato"
        self.width, self.height = landscape(size) if orientation == "paisagem" else portrait(size)
        self.font, self.bold = _register_fonts(options.font)
        self.canvas = Canvas(str(dest), pagesize=(self.width, self.height), pageCompression=int(options.compress))
        self.canvas.setTitle(project.title)
        self.canvas.setCreator("Passo a Passo")
        logo = load_logo(root, self.theme)
        self.logo = ImageReader(logo) if logo is not None else None
        self.logo_ratio = (logo.width / logo.height) if logo is not None else 1.0
        self.page = 0

    # --- página ----------------------------------------------------------

    def _begin_page(self, with_header: bool = True) -> None:
        self.page += 1
        c = self.canvas
        c.setFillColor(HexColor(self.theme.page_background))
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        if with_header:
            top = self.height - MARGIN
            x = MARGIN
            if self.logo is not None:
                h = 24
                w = h * self.logo_ratio
                c.drawImage(self.logo, x, top - h, w, h, mask="auto")
                x += w + 10
            c.setFillColor(HexColor(self.theme.text_color))
            c.setFont(self.bold, 11)
            c.drawString(x, top - 16, self.project.title)
            c.setStrokeColor(HexColor(self.theme.highlight_color))
            c.setLineWidth(1.5)
            c.line(MARGIN, top - HEADER_H + 12, self.width - MARGIN, top - HEADER_H + 12)
        if with_header:  # a capa não leva número de página
            c.setFillColor(HexColor(self.theme.text_color))
            c.setFont(self.font, 9)
            c.drawRightString(self.width - MARGIN, MARGIN / 2, f"Página {self.page}")

    def _end_page(self) -> None:
        self.canvas.showPage()

    # --- capa ------------------------------------------------------------

    def cover(self) -> None:
        c = self.canvas
        self._begin_page(with_header=False)
        y = self.height * 0.62
        if self.logo is not None:
            h = 110
            w = min(h * self.logo_ratio, self.width - 2 * MARGIN)
            h = w / self.logo_ratio
            c.drawImage(self.logo, (self.width - w) / 2, y, w, h, mask="auto")
        c.setFillColor(HexColor(self.theme.text_color))
        size = 28
        lines = wrap(self.project.title, lambda s: pdfmetrics.stringWidth(s, self.bold, size), self.width - 2 * MARGIN)
        ty = y - 50
        c.setFont(self.bold, size)
        for line in lines:
            c.drawCentredString(self.width / 2, ty, line)
            ty -= size * 1.25
        c.setStrokeColor(HexColor(self.theme.highlight_color))
        c.setLineWidth(3)
        c.line(self.width / 2 - 40, ty + 8, self.width / 2 + 40, ty + 8)
        c.setFont(self.font, 13)
        n = len(self.project.steps)
        info = f"{_format_date(self.project.created_at)} · {n} passo{'s' if n != 1 else ''}"
        c.drawCentredString(self.width / 2, ty - 22, info)
        self._end_page()

    # --- passos ----------------------------------------------------------

    def step_block(self, index: int, top: float, height: float) -> None:
        """Desenha o passo index na faixa vertical [top - height, top]."""
        c = self.canvas
        theme = self.theme
        step = self.project.steps[index]
        left, right = MARGIN, self.width - MARGIN
        content_w = right - left

        # Selo com o número.
        badge_r = 13
        cx, cy = left + badge_r, top - badge_r
        c.setFillColor(HexColor(theme.highlight_color))
        c.circle(cx, cy, badge_r, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont(self.bold, 12)
        c.drawCentredString(cx, cy - 4.2, str(index + 1))

        # Texto do passo ao lado do selo.
        size = 12.5
        text_x = left + 2 * badge_r + 10
        lines = wrap(step.text, lambda s: pdfmetrics.stringWidth(s, self.font, size), right - text_x)
        c.setFillColor(HexColor(theme.text_color))
        c.setFont(self.font, size)
        ty = top - 17
        for line in lines:
            c.drawString(text_x, ty, line)
            ty -= size * 1.35
        text_bottom = min(ty + size * 1.35 - 6, top - 2 * badge_r - 4)

        # Captura com moldura na cor das margens.
        with Image.open(self.root / step.image) as img:
            shot = spotlight_step(img, step, self.project)
        frame = 6
        avail_w = content_w - 2 * frame
        avail_h = (text_bottom - 12) - (top - height) - 2 * frame
        scale = min(avail_w / shot.width, avail_h / shot.height)
        w, h = shot.width * scale, shot.height * scale
        x = left + (content_w - w) / 2
        y = text_bottom - 12 - frame - h
        c.setFillColor(HexColor(theme.margin_color))
        c.roundRect(x - frame, y - frame, w + 2 * frame, h + 2 * frame, 4, stroke=0, fill=1)
        c.drawImage(_image_reader(shot, self.options.jpeg_quality), x, y, w, h)

        # Círculo em vetor sobre a imagem.
        style = scaled_style(self.project.circle_for(step), step.scale)
        px = x + step.point[0] * scale
        py = y + h - step.point[1] * scale
        r = max(style.radius * scale, 3)
        stroke = max(style.stroke * scale, 0.75)
        color = HexColor(theme.highlight_color)
        c.saveState()
        c.setFillColor(color)
        c.setFillAlpha(style.fill_opacity)
        c.circle(px, py, r - stroke / 2, stroke=0, fill=1)
        c.restoreState()
        c.setStrokeColor(color)
        c.setLineWidth(stroke)
        c.circle(px, py, r - stroke / 2, stroke=1, fill=0)

    def steps(self, progress: Progress | None, cancel: threading.Event | None) -> None:
        per_page = 2 if self.options.steps_per_page == 2 else 1
        n = len(self.project.steps)
        top = self.height - MARGIN - HEADER_H
        usable = top - (MARGIN + FOOTER_H)
        gap = 24
        block_h = (usable - gap * (per_page - 1)) / per_page
        for i in range(n):
            check_cancel(cancel)
            slot = i % per_page
            if slot == 0:
                self._begin_page()
            self.step_block(i, top - slot * (block_h + gap), block_h)
            if slot == per_page - 1 or i == n - 1:
                self._end_page()
            if progress:
                progress((i + 1) / n)

    def save(self) -> None:
        self.canvas.save()


def export_pdf(
    project: Project,
    root: str | Path,
    dest: str | Path,
    options: PdfOptions | None = None,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    dest = Path(dest)
    tmp = dest.with_name(dest.name + ".tmp")
    writer = _PdfWriter(project, Path(root), tmp, options or PdfOptions())
    try:
        writer.cover()
        writer.steps(progress, cancel)
        writer.save()
        tmp.replace(dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest
