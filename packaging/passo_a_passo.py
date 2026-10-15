"""Entrada do executável (PyInstaller): "Passo a Passo.exe" [arquivo.passo | --autoteste]

Sem console: erros vão para %LOCALAPPDATA%\\PassoAPasso\\erros.log, nunca para a
pasta do executável.
"""

import ctypes
import os
import sys
import traceback
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # rodando do código-fonte

LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PassoAPasso"
LOG = LOG_DIR / "erros.log"


def _redirect_output() -> None:
    if sys.stderr is None or sys.stdout is None:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
        except OSError:
            sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")


if __name__ == "__main__":
    if "--autoteste" in sys.argv[1:]:
        # Sem caixas de mensagem: o resultado vai no código de saída e no relatório.
        from app.autoteste import main as autoteste

        sys.exit(autoteste(sys.argv[1:]))

    _redirect_output()
    try:
        from app.main import main

        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        ctypes.windll.user32.MessageBoxW(
            None, f"O Passo a Passo encontrou um erro e foi fechado.\n\nDetalhes em:\n{LOG}", "Passo a Passo", 0x10
        )
        sys.exit(1)
