"""Regras para transformar cliques em passos."""

from __future__ import annotations

from app.capture.base import ClickEvent


def is_double_click(prev: ClickEvent | None, cur: ClickEvent, interval: float, distance: int) -> bool:
    """O segundo clique esquerdo rápido e no mesmo lugar completa um duplo clique."""
    if prev is None or prev.button != "left" or cur.button != "left":
        return False
    return (
        0 <= cur.time - prev.time <= interval
        and abs(cur.x - prev.x) <= distance
        and abs(cur.y - prev.y) <= distance
    )


def action_for(button: str) -> str:
    return "right_click" if button == "right" else "click"
