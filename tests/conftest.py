import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(autouse=True)
def _config_isolada(tmp_path, monkeypatch):
    """Nenhum teste lê ou grava o config.json e a logo padrão reais do usuário."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
