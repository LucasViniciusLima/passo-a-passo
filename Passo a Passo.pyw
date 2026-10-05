"""Lançador sem console: abre a barra de gravação (ou um .passo passado como argumento).

Use com o pythonw da .venv, como faz o atalho da Área de Trabalho.
"""

import ctypes
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Sem console, erros vão para um arquivo de log.
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "PassoAPasso"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "erros.log"
if sys.stderr is None or sys.stdout is None:
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)

try:
    from app.main import main

    sys.exit(main())
except SystemExit:
    raise
except BaseException:
    detail = traceback.format_exc()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(detail)
    ctypes.windll.user32.MessageBoxW(
        None, f"O Passo a Passo encontrou um erro e foi fechado.\n\nDetalhes em:\n{LOG}", "Passo a Passo", 0x10
    )
    sys.exit(1)
