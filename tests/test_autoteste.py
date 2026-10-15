"""Autoteste da build rodando a partir do código-fonte."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import sys

import pytest

from app import autoteste


@pytest.mark.skipif(sys.platform != "win32", reason="captura e UIA só no Windows")
def test_autoteste_passa(tmp_path):
    relatorio = tmp_path / "relatorio.txt"
    assert autoteste.main([f"--relatorio={relatorio}"]) == 0
    texto = relatorio.read_text(encoding="utf-8")
    assert "AUTOTESTE OK" in texto
    assert "exemplo.mp4" in texto and "exemplo.gif" in texto and "exemplo.pdf" in texto
