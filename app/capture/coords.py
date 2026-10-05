"""Conversão de coordenadas entre a área de trabalho, os monitores e as imagens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Monitor:
    """Monitor em pixels físicos. index segue a numeração do mss (1 = primeiro)."""

    index: int
    left: int
    top: int
    width: int
    height: int
    scale: float = 1.0  # escala do Windows (1.0 = 100%, 1.5 = 150%)

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


def find_monitor(x: float, y: float, monitors: list[Monitor]) -> Monitor:
    """Monitor que contém o ponto; se nenhum contiver, o mais próximo."""
    if not monitors:
        raise ValueError("Nenhum monitor disponível.")
    for m in monitors:
        if m.contains(x, y):
            return m

    def distance(m: Monitor) -> float:
        dx = max(m.left - x, 0, x - (m.right - 1))
        dy = max(m.top - y, 0, y - (m.bottom - 1))
        return dx * dx + dy * dy

    return min(monitors, key=distance)


def to_image_point(
    x: float, y: float, monitor: Monitor, image_size: tuple[int, int]
) -> tuple[int, int]:
    """Converte um ponto da área de trabalho para pixels da captura do monitor.

    A captura pode ter tamanho diferente do monitor (ex.: backend que entrega
    pixels lógicos), por isso a conversão usa a proporção entre os dois.
    """
    img_w, img_h = image_size
    ix = (x - monitor.left) * img_w / monitor.width
    iy = (y - monitor.top) * img_h / monitor.height
    return (
        min(max(int(round(ix)), 0), img_w - 1),
        min(max(int(round(iy)), 0), img_h - 1),
    )


def logical_to_physical(point: tuple[float, float], scale: float) -> tuple[int, int]:
    return int(round(point[0] * scale)), int(round(point[1] * scale))


def physical_to_logical(point: tuple[float, float], scale: float) -> tuple[float, float]:
    return point[0] / scale, point[1] / scale


def rect_contains(rect: tuple[int, int, int, int] | None, x: float, y: float) -> bool:
    """rect = (esquerda, topo, direita, baixo), com direita e baixo exclusivos."""
    if rect is None:
        return False
    left, top, right, bottom = rect
    return left <= x < right and top <= y < bottom


def rect_to_image(
    rect: tuple[int, int, int, int] | None, monitor: Monitor, image_size: tuple[int, int]
) -> list[int] | None:
    """Retângulo da área de trabalho (esq, topo, dir, baixo) -> [x, y, w, h] na imagem do monitor.

    O retângulo é recortado ao monitor; se não sobrar nada, devolve None.
    """
    if rect is None:
        return None
    img_w, img_h = image_size
    sx, sy = img_w / monitor.width, img_h / monitor.height
    left = min(max(round((rect[0] - monitor.left) * sx), 0), img_w)
    top = min(max(round((rect[1] - monitor.top) * sy), 0), img_h)
    right = min(max(round((rect[2] - monitor.left) * sx), 0), img_w)
    bottom = min(max(round((rect[3] - monitor.top) * sy), 0), img_h)
    if right - left < 2 or bottom - top < 2:
        return None
    return [left, top, right - left, bottom - top]
