"""Linha do tempo compartilhada pelo vídeo e pelo GIF: gera os quadros com Pillow.

Sequência: abertura (logo e título) -> para cada passo: transição de entrada, zoom
suave em direção ao clique, círculo surgindo com um pulso e legenda com o texto ->
encerramento.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

from app.project.model import Project
from app.render.annotate import scaled_style, spotlight_step
from app.render.fonts import pil_font, wrap
from app.theme import load_logo

ZOOM_MAX = 1.18  # zoom final em direção ao clique
INTRO_SECONDS = 2.0
OUTRO_SECONDS = 1.5


def smoothstep(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ease_out_back(x: float, overshoot: float = 1.9) -> float:
    """Sobe passando um pouco de 1 e volta: dá o efeito de pulso."""
    x = min(max(x, 0.0), 1.0)
    return 1 + (overshoot + 1) * (x - 1) ** 3 + overshoot * (x - 1) ** 2


@lru_cache(maxsize=256)
def _circle_patch(radius2: int, stroke2: int, fill_alpha: int, color: tuple[int, int, int]) -> Image.Image:
    """Círculo RGBA com borda suave; raio e borda em meios pixels (cache por tamanho)."""
    ss = 4
    r, s = radius2 / 2, stroke2 / 2
    size = math.ceil(2 * r) + 4
    big = Image.new("RGBA", (size * ss, size * ss), color + (0,))
    d = ImageDraw.Draw(big)
    off = (size - 2 * r) / 2 * ss
    box = (off, off, off + 2 * r * ss - 1, off + 2 * r * ss - 1)
    d.ellipse(box, fill=color + (fill_alpha,), outline=color + (255,), width=max(round(s * ss), 1))
    return big.resize((size, size), Image.Resampling.LANCZOS)


def paste_circle(frame: Image.Image, center: tuple[float, float], radius: float, stroke: float,
                 fill_opacity: float, color: str) -> None:
    if radius < 1:
        return
    rgb = ImageColor.getrgb(color)[:3]
    patch = _circle_patch(max(round(radius * 2), 2), max(round(stroke * 2), 1), round(255 * fill_opacity), rgb)
    x = round(center[0] - patch.width / 2)
    y = round(center[1] - patch.height / 2)
    frame.paste(patch, (x, y), patch)


@dataclass
class _StepAssets:
    screen: Image.Image  # captura já com o fundo em destaque, sem círculo
    point: tuple[int, int]
    radius: float  # em pixels da captura
    stroke: float
    fill_opacity: float
    caption: Image.Image


class Timeline:
    def __init__(
        self,
        project: Project,
        root: str | Path,
        size: tuple[int, int],
        fps: int,
        seconds_per_step: float = 3.0,
        transition: str = "esmaecer",
        transition_seconds: float = 0.5,
        intro_seconds: float = INTRO_SECONDS,
        outro_seconds: float = OUTRO_SECONDS,
    ) -> None:
        self.project = project
        self.root = Path(root)
        self.theme = project.theme
        self.W, self.H = size
        self.fps = fps
        self.step_frames = max(round(seconds_per_step * fps), 2)
        self.transition = transition
        self.trans_frames = min(max(round(transition_seconds * fps), 0), self.step_frames - 1)
        self.intro_frames = max(round(intro_seconds * fps), 1)
        self.outro_frames = max(round(outro_seconds * fps), 1)
        self.logo = load_logo(self.root, self.theme)
        self.bg = ImageColor.getrgb(self.theme.page_background)[:3]
        self.caption_h = round(self.H * 0.14)
        pad = round(self.H * 0.035)
        self.frame_w = max(round(self.H * 0.008), 2)  # moldura na cor das margens
        self.area = (pad, pad, self.W - pad, self.H - self.caption_h - pad)

    # --- tamanhos --------------------------------------------------------

    def total_frames(self) -> int:
        return self.intro_frames + len(self.project.steps) * self.step_frames + self.outro_frames

    @property
    def duration(self) -> float:
        return self.total_frames() / self.fps

    # --- peças -----------------------------------------------------------

    def _caption(self, number: int, text: str) -> Image.Image:
        theme = self.theme
        band = Image.new("RGB", (self.W, self.caption_h), theme.margin_color)
        d = ImageDraw.Draw(band)
        line_w = max(round(self.H * 0.005), 2)
        d.rectangle((0, 0, self.W, line_w), fill=theme.highlight_color)
        size = max(round(self.H * 0.034), 10)
        font = pil_font(size)
        badge_r = round(size * 0.95)
        cx, cy = self.area[0] + badge_r, (self.caption_h + line_w) // 2
        d.ellipse((cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r), fill=theme.highlight_color)
        bold = pil_font(round(size * 0.95), bold=True)
        d.text((cx, cy), str(number), fill="white", font=bold, anchor="mm")
        x = cx + badge_r + round(size * 0.8)
        lines = wrap(text, lambda s: d.textlength(s, font=font), self.W - x - self.area[0])[:2]
        line_h = round(size * 1.3)
        y = cy - line_h * len(lines) / 2
        for line in lines:
            d.text((x, y), line, fill=theme.text_color, font=font)
            y += line_h
        return band

    def _assets(self, index: int) -> _StepAssets:
        step = self.project.steps[index]
        with Image.open(self.root / step.image) as img:
            screen = spotlight_step(img, step, self.project)
        style = scaled_style(self.project.circle_for(step), step.scale)
        return _StepAssets(
            screen=screen,
            point=step.point,
            radius=style.radius,
            stroke=style.stroke,
            fill_opacity=style.fill_opacity,
            caption=self._caption(index + 1, step.text),
        )

    def _title_card(self, subtitle: str) -> Image.Image:
        frame = Image.new("RGB", (self.W, self.H), self.bg)
        d = ImageDraw.Draw(frame)
        y = self.H * 0.5
        if self.logo is not None:
            logo = self.logo.copy()
            logo.thumbnail((round(self.W * 0.4), round(self.H * 0.25)))
            frame.paste(logo, ((self.W - logo.width) // 2, round(self.H * 0.42) - logo.height), logo)
            y = self.H * 0.55
        size = round(self.H * 0.065)
        font = pil_font(size, bold=True)
        lines = wrap(self.project.title, lambda s: d.textlength(s, font=font), self.W * 0.85)[:2]
        for line in lines:
            d.text((self.W / 2, y), line, fill=self.theme.text_color, font=font, anchor="mm")
            y += size * 1.2
        d.rectangle((self.W / 2 - self.H * 0.05, y - size * 0.35, self.W / 2 + self.H * 0.05, y - size * 0.35 + 4),
                    fill=self.theme.highlight_color)
        d.text((self.W / 2, y + size * 0.4), subtitle, fill=self.theme.text_color,
               font=pil_font(round(size * 0.45)), anchor="mm")
        return frame

    def _step_frame(self, a: _StepAssets, t: float, seconds: float, trans: float) -> Image.Image:
        """Quadro do passo no instante t (segundos desde o início do passo)."""
        frame = Image.new("RGB", (self.W, self.H), self.bg)
        sw, sh = a.screen.size
        ax0, ay0, ax1, ay1 = self.area
        fw = self.frame_w
        scale = min((ax1 - ax0 - 2 * fw) / sw, (ay1 - ay0 - 2 * fw) / sh)
        dw, dh = round(sw * scale), round(sh * scale)
        dx, dy = ax0 + (ax1 - ax0 - dw) // 2, ay0 + (ay1 - ay0 - dh) // 2

        # Zoom suave em direção ao clique.
        p = smoothstep((t - trans) / max(seconds - trans - 0.3, 0.1))
        z = 1 + (ZOOM_MAX - 1) * p
        cw, ch = sw / z, sh / z
        cx = sw / 2 + (a.point[0] - sw / 2) * p
        cy = sh / 2 + (a.point[1] - sh / 2) * p
        left = min(max(cx - cw / 2, 0), sw - cw)
        top = min(max(cy - ch / 2, 0), sh - ch)
        crop = a.screen.resize((dw, dh), Image.Resampling.BILINEAR, box=(left, top, left + cw, top + ch))

        d = ImageDraw.Draw(frame)
        d.rounded_rectangle((dx - fw, dy - fw, dx + dw + fw - 1, dy + dh + fw - 1), radius=fw * 2,
                            fill=self.theme.margin_color)
        frame.paste(crop, (dx, dy))

        # Círculo surgindo com um pulso e depois "respirando" de leve.
        k = dw / cw
        appear = (t - trans * 0.6) / 0.45
        if appear > 0:
            s = ease_out_back(appear)
            if appear >= 1:
                s = 1 + 0.04 * math.sin(2 * math.pi * (t - trans * 0.6 - 0.45) / 1.2)
            px = dx + (a.point[0] - left) * k
            py = dy + (a.point[1] - top) * k
            paste_circle(frame, (px, py), a.radius * k * s, max(a.stroke * k, 1.5), a.fill_opacity,
                         self.theme.highlight_color)

        frame.paste(a.caption, (0, self.H - self.caption_h))
        return frame

    def _transition(self, prev: Image.Image, cur: Image.Image, q: float) -> Image.Image:
        q = smoothstep(q)
        if self.transition == "deslizar":
            out = Image.new("RGB", (self.W, self.H), self.bg)
            shift = round(self.W * q)
            out.paste(prev, (-shift, 0))
            out.paste(cur, (self.W - shift, 0))
            return out
        if self.transition == "zoom":
            z = 1.12 - 0.12 * q
            w, h = self.W / z, self.H / z
            box = ((self.W - w) / 2, (self.H - h) / 2, (self.W + w) / 2, (self.H + h) / 2)
            cur = cur.resize((self.W, self.H), Image.Resampling.BILINEAR, box=box)
        return Image.blend(prev, cur, q)

    # --- quadros ---------------------------------------------------------

    def frames(self) -> Iterator[Image.Image]:
        fps = self.fps
        n = len(self.project.steps)
        intro = self._title_card(f"{n} passo{'s' if n != 1 else ''}")
        blank = Image.new("RGB", (self.W, self.H), self.bg)
        fade_in = max(round(0.4 * fps), 1)
        for i in range(self.intro_frames):
            yield Image.blend(blank, intro, smoothstep(i / fade_in)) if i < fade_in else intro

        prev = intro
        seconds = self.step_frames / fps
        trans = self.trans_frames / fps
        for index in range(n):
            assets = self._assets(index)
            last = prev
            for i in range(self.step_frames):
                t = i / fps
                frame = self._step_frame(assets, t, seconds, trans)
                if i < self.trans_frames:
                    frame = self._transition(prev, frame, (i + 1) / (self.trans_frames + 1))
                last = frame
                yield frame
            prev = last

        outro = self._title_card("Fim")
        fade = max(min(self.trans_frames, self.outro_frames - 1), 1)
        for i in range(self.outro_frames):
            yield self._transition(prev, outro, (i + 1) / (fade + 1)) if i < fade else outro
