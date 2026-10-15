"""Autoteste da build: Passo a Passo.exe --autoteste [--relatorio=arquivo.txt]

Importa todos os módulos, cria as janelas (use QT_QPA_PLATFORM=offscreen para
nada aparecer na tela) e exporta PDF, GIF e MP4 de um tutorial de exemplo numa
pasta temporária. Sai com código 0 se tudo funcionou.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys
import tempfile
import time
import traceback
from pathlib import Path


def _bundle_dir() -> Path | None:
    """Pasta da build (_internal) quando rodando congelado pelo PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base).resolve() if base else None


def _inside(path: str | Path, folder: Path) -> bool:
    return Path(path).resolve().is_relative_to(folder)


def _check_imports(log) -> None:
    import app

    # app.__main__ abriria o app de verdade.
    names = [m.name for m in pkgutil.walk_packages(app.__path__, "app.") if m.name != "app.__main__"]
    for name in names:
        importlib.import_module(name)
    log(f"módulos do app importados: {len(names)}")
    from pynput import keyboard, mouse  # noqa: F401  (backends win32 escolhidos no import)

    keyboard.GlobalHotKeys({"<ctrl>+<shift>+<f9>": lambda: None})
    log(f"pynput: {keyboard.Listener.__module__}, {mouse.Listener.__module__}")


def _check_uia(log, bundle: Path | None) -> None:
    from app.capture.uia import UIAElementInspector
    from app.capture.windows import Win32ElementInspector

    inspector = UIAElementInspector(Win32ElementInspector())
    inspector._pending.result(timeout=20)  # levanta a exceção se o UIA não iniciou
    from comtypes.gen import UIAutomationClient

    origem = getattr(UIAutomationClient, "__file__", None) or "(em memória)"
    log(f"UI Automation ok, módulo comtypes.gen de: {origem}")
    if bundle is not None and not (origem != "(em memória)" and _inside(origem, bundle)):
        raise RuntimeError("os módulos comtypes.gen deveriam vir de dentro da build")
    info = inspector.inspect(10, 10)
    log(f"inspeção UIA em (10, 10): {info.element_type!r}; foco do teclado: {inspector.focus_point()}")


def _check_hooks(log) -> None:
    """Liga e desliga os hooks de mouse e teclado e lê a integridade das janelas (nada aparece)."""
    from app import capture

    for hook, callback in ((capture.create_input_hook(), lambda e: None), (capture.create_key_hook(), lambda e: None)):
        hook.start(callback)
        hook.stop()
    window = capture.elevated_window_in_use()
    log(f"hooks de mouse e teclado ok; administrador: {capture.is_admin()}; "
        f"janela de administrador em uso: {window.name if window else 'nenhuma'}")


def _check_ffmpeg(log, bundle: Path | None) -> None:
    from app.export.video import ffmpeg_exe

    exe = ffmpeg_exe()
    log(f"FFmpeg: {exe}")
    if bundle is not None and not _inside(exe, bundle):
        raise RuntimeError("o FFmpeg deveria vir de dentro da build")


def _sample_workspace(tmp: Path):
    from PIL import Image, ImageDraw

    from app.project.model import Step
    from app.project.storage import ProjectWorkspace
    from app.theme import set_logo

    ws = ProjectWorkspace(root=tmp / "ws")
    ws.project.title = "Tutorial de exemplo"
    textos = ["Passo 1: Clique no botão Iniciar", "Passo 2: Abra o menu Arquivo", "Passo 3: Clique em Salvar"]
    for i, text in enumerate(textos):
        rel, path = ws.next_image_path()
        img = Image.new("RGB", (1280, 720), (40 + 60 * i, 90, 160))
        ImageDraw.Draw(img).rectangle((200, 160, 1000, 560), fill=(235, 235, 235))
        img.save(path)
        ws.add_step(Step(image=rel, point=(400 + 120 * i, 300), text=text, focus_rect=[200, 160, 800, 400]))
    # Logo em SVG: exercita o plugin/módulo QtSvg da build.
    svg = tmp / "logo.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">'
        '<rect width="300" height="100" rx="12" fill="#e53935"/></svg>',
        encoding="utf-8",
    )
    set_logo(ws, svg)
    return ws


def _check_windows(log, ws) -> None:
    from PySide6.QtWidgets import QApplication

    from app.main import PassoApp
    from app.ui.export_dialog import ExportDialog

    app = QApplication.instance()
    shell = PassoApp(app)
    shell.show_bar()
    review = shell.show_review(ws, None)
    dialog = ExportDialog(ws, ws.root.parent, review)
    dialog.show()
    for _ in range(5):
        app.processEvents()
        time.sleep(0.05)
    log(f"janelas criadas: barra, revisão ({review.list.count()} passos) e exportação")
    dialog.hide()
    review.hide()
    shell.bar.hide()
    app.processEvents()


def _check_exports(log, ws, out: Path) -> None:
    from app.export import GifOptions, VideoOptions
    from app.export.pdf import export_pdf
    from app.export.video import export_gif, export_mp4

    pdf = export_pdf(ws.project, ws.root, out / "exemplo.pdf")
    gif = export_gif(ws.project, ws.root, out / "exemplo.gif", GifOptions(width=480, fps=8, seconds_per_step=1.0))
    mp4 = export_mp4(ws.project, ws.root, out / "exemplo.mp4", VideoOptions(height=360, seconds_per_step=1.0))
    checks = [(pdf, b"%PDF"), (gif, b"GIF8"), (mp4, None)]
    for path, magic in checks:
        data = path.read_bytes()
        if len(data) < 1000 or (magic and not data.startswith(magic)) or (magic is None and b"ftyp" not in data[:64]):
            raise RuntimeError(f"arquivo exportado inválido: {path.name}")
        log(f"exportado {path.name}: {len(data):,} bytes".replace(",", "."))


def run(report: Path | None = None) -> int:
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)
        if sys.stdout is not None:
            print(msg, flush=True)

    bundle = _bundle_dir()
    code = 0
    with tempfile.TemporaryDirectory(prefix="passo-autoteste-") as tmp_name:
        tmp = Path(tmp_name)
        # Config e logo padrão do autoteste não tocam nas preferências reais.
        os.environ["LOCALAPPDATA"] = str(tmp / "localappdata")
        try:
            from app import capture, settings

            capture.enable_dpi_awareness()
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance() or QApplication([sys.argv[0]])
            log(f"executável: {sys.executable}")
            log(f"build congelada: {bundle or 'não'}; plataforma Qt: {app.platformName()}")
            _check_imports(log)
            if bundle is not None and _inside(settings.config_dir(), Path(sys.executable).parent):
                raise RuntimeError("config não pode ficar na pasta do executável")
            log(f"config em: {settings.config_dir()}")
            _check_ffmpeg(log, bundle)
            _check_uia(log, bundle)
            _check_hooks(log)
            ws = _sample_workspace(tmp)
            _check_windows(log, ws)
            out = tmp / "saida"
            out.mkdir()
            _check_exports(log, ws, out)
            log("AUTOTESTE OK")
        except BaseException:
            log(traceback.format_exc())
            log("AUTOTESTE FALHOU")
            code = 1
    if report is not None:
        Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


def main(argv: list[str]) -> int:
    report = next((a.split("=", 1)[1] for a in argv if a.startswith("--relatorio=")), None)
    return run(Path(report) if report else None)
