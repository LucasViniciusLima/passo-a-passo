"""Anotações desenhadas sobre as capturas (as imagens originais nunca são alteradas)."""

from __future__ import annotations

from PIL import Image, ImageColor, ImageDraw, ImageFilter

from app.project.model import CircleStyle, Project, SpotlightStyle, Step

_SUPERSAMPLE = 4  # desenha maior e reduz, para bordas suaves


def draw_circle(
    image: Image.Image, center: tuple[int, int], style: CircleStyle, color: str
) -> Image.Image:
    """Devolve uma cópia da imagem com o círculo de destaque.

    style.radius é o raio externo; a borda (style.stroke) cresce para dentro e o
    interior recebe a mesma cor com opacidade style.fill_opacity.
    """
    r, g, b = ImageColor.getrgb(color)[:3]
    radius = max(int(style.radius), 1)
    stroke = max(int(style.stroke), 0)
    fill_alpha = round(255 * min(max(style.fill_opacity, 0.0), 1.0))

    pad = 2
    size = (radius + pad) * 2
    ss = _SUPERSAMPLE
    patch = Image.new("RGBA", (size * ss, size * ss), (r, g, b, 0))
    draw = ImageDraw.Draw(patch)
    box = (pad * ss, pad * ss, (pad + 2 * radius) * ss - 1, (pad + 2 * radius) * ss - 1)
    draw.ellipse(box, fill=(r, g, b, fill_alpha), outline=(r, g, b, 255), width=stroke * ss)
    patch = patch.resize((size, size), Image.Resampling.LANCZOS)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay.paste(patch, (center[0] - radius - pad, center[1] - radius - pad))
    out = Image.alpha_composite(image.convert("RGBA"), overlay)
    return out.convert(image.mode if image.mode in ("RGB", "RGBA") else "RGB")


def scaled_style(style: CircleStyle, scale: float) -> CircleStyle:
    """Ajusta o círculo à escala do monitor, para ter o mesmo tamanho visual em HiDPI."""
    scale = scale if scale > 0 else 1.0
    return CircleStyle(
        radius=round(style.radius * scale),
        stroke=max(round(style.stroke * scale), 1) if style.stroke else 0,
        fill_opacity=style.fill_opacity,
    )


# Janela que ocupa quase o monitor todo (maximizada): nada a desfocar.
FULL_SCREEN_FRACTION = 0.95


def _background(base: Image.Image, style: SpotlightStyle, scale: float) -> Image.Image:
    background = base
    if style.blur > 0:
        background = background.filter(ImageFilter.GaussianBlur(style.blur * scale))
    dim = min(max(style.dim, 0.0), 1.0)
    if dim > 0:
        background = Image.blend(background, Image.new("RGB", base.size, (0, 0, 0)), dim)
    return background


def _compose(base: Image.Image, background: Image.Image, mask: Image.Image, scale: float) -> Image.Image:
    # Borda suave: a máscara é desfocada (transição de ~8 px).
    mask = mask.filter(ImageFilter.GaussianBlur(max(2.5 * scale, 1.0)))
    return Image.composite(base, background, mask)


def apply_spotlight(
    image: Image.Image, center: tuple[int, int], clear_radius: int, style: SpotlightStyle, scale: float = 1.0
) -> Image.Image:
    """Modo círculo: desfoca e escurece tudo, menos um círculo de raio clear_radius."""
    base = image.convert("RGB")
    mask = Image.new("L", base.size, 0)
    x, y = center
    ImageDraw.Draw(mask).ellipse(
        (x - clear_radius, y - clear_radius, x + clear_radius, y + clear_radius), fill=255
    )
    return _compose(base, _background(base, style, scale), mask, scale)


def apply_window_spotlight(
    image: Image.Image, rect: list[int], style: SpotlightStyle, scale: float = 1.0
) -> Image.Image:
    """Modo janela: o retângulo [x, y, w, h] fica nítido; o resto, desfocado e escurecido."""
    base = image.convert("RGB")
    x, y, w, h = rect
    if w * h >= FULL_SCREEN_FRACTION * base.width * base.height:
        return base
    mask = Image.new("L", base.size, 0)
    corner = max(round(8 * scale), 1)
    ImageDraw.Draw(mask).rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=corner, fill=255)
    return _compose(base, _background(base, style, scale), mask, scale)


def spotlight_step(image: Image.Image, step: Step, project: Project) -> Image.Image:
    """Só o destaque do fundo (sem o círculo), conforme o modo do tema."""
    style = scaled_style(project.circle_for(step), step.scale)
    spot = project.theme.spotlight
    scale = step.scale if step.scale > 0 else 1.0
    if spot.mode == "janela" and step.focus_rect:
        return apply_window_spotlight(image, step.focus_rect, spot, scale)
    if spot.mode == "circulo":
        clear = style.radius + round(spot.margin * scale)
        return apply_spotlight(image, step.point, clear, spot, scale)
    # Modo janela sem focus_rect (tutoriais antigos, Área de Trabalho): sem desfoque.
    return image.convert("RGB")


def annotate_step(image: Image.Image, step: Step, project: Project) -> Image.Image:
    """Captura anotada: destaque conforme o tema e o círculo por cima."""
    style = scaled_style(project.circle_for(step), step.scale)
    return draw_circle(spotlight_step(image, step, project), step.point, style, project.theme.highlight_color)