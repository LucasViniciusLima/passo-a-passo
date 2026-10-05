"""Ponto de entrada: python -m app [arquivo.passo]"""

from __future__ import annotations

import os
import sys
import traceback
import zipfile
from pathlib import Path

from app import capture

LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PassoAPasso"
LOG_FILE = LOG_DIR / "erros.log"


def install_error_handler() -> None:
    """Exceções não tratadas (inclusive em slots Qt) vão para o log e viram um aviso."""

    def handler(exc_type, exc, tb) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(detail + "\n")
        except OSError:
            pass
        sys.__stderr__ and sys.__stderr__.write(detail)
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is not None:
            QMessageBox.critical(
                None, "Passo a Passo",
                f"Ocorreu um erro inesperado:\n{exc}\n\nDetalhes em:\n{LOG_FILE}",
            )

    sys.excepthook = handler


class PassoApp:
    """Liga a barra de gravação, o controlador e as janelas de revisão."""

    def __init__(self, app) -> None:
        from app.recorder.controller import RecordingController
        from app.ui.recording_bar import RecordingBar

        self.app = app
        # Janelas abertas precisam de referência; sem ela o Python as descarta e o app fecha.
        self.reviews: list = []
        self.controller = RecordingController()
        self.bar = RecordingBar(self.controller)
        self.bar.btn_close.clicked.connect(app.quit)
        self.bar.openRequested.connect(self.ask_and_open)
        self.controller.error.connect(lambda message: print(message, file=sys.stderr))
        self.controller.finished.connect(self.on_finished)

    def show_bar(self) -> None:
        screen = self.app.primaryScreen().availableGeometry()
        self.bar.adjustSize()
        self.bar.move(screen.center().x() - self.bar.width() // 2, screen.top() + 16)
        self.bar.show()

    def show_review(self, workspace, saved: Path | None):
        from PySide6.QtCore import Qt

        from app.ui.review_window import ReviewWindow

        review = ReviewWindow(workspace, saved)
        review.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.reviews.append(review)
        review.destroyed.connect(lambda *_: self._review_closed(review))
        review.show()
        review.raise_()
        review.activateWindow()
        return review

    def _review_closed(self, review) -> None:
        if review in self.reviews:
            self.reviews.remove(review)
        if not self.reviews:
            self.app.quit()

    def open_file(self, path: Path):
        from PySide6.QtWidgets import QMessageBox

        from app.project.storage import open_passo

        try:
            workspace = open_passo(path)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            QMessageBox.critical(None, "Erro ao abrir", f"Não foi possível abrir {path.name}:\n{exc}")
            return None
        return self.show_review(workspace, path.resolve())

    def ask_and_open(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        start = str(Path.home() / "Documents")
        path, _ = QFileDialog.getOpenFileName(self.bar, "Abrir tutorial", start, "Projeto Passo a Passo (*.passo)")
        if path and self.open_file(Path(path)) is not None:
            self.bar.hide()

    def on_finished(self, workspace) -> None:
        from PySide6.QtWidgets import QMessageBox

        from app.ui.review_window import ask_save_path

        self.bar.hide()
        if not workspace.project.steps:
            QMessageBox.information(None, "Passo a Passo", "Nenhum passo foi gravado.")
            workspace.cleanup()
            self.app.quit()
            return
        saved = None
        path = ask_save_path(None)
        if path is not None:
            try:
                saved = workspace.save_to(path)
            except OSError as exc:
                QMessageBox.critical(None, "Erro ao salvar", str(exc))
        self.show_review(workspace, saved)


def main(argv: list[str] | None = None) -> int:
    # Precisa vir antes de criar o QApplication para as coordenadas baterem em HiDPI.
    capture.enable_dpi_awareness()
    install_error_handler()

    from PySide6.QtWidgets import QApplication

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Passo a Passo")
    # O app encerra explicitamente: ao fechar a barra ociosa ou a última revisão.
    app.setQuitOnLastWindowClosed(False)
    shell = PassoApp(app)

    # python -m app arquivo.passo: abre direto a revisão de um tutorial salvo.
    files = [a for a in app.arguments()[1:] if a.lower().endswith(".passo")]
    if files:
        if shell.open_file(Path(files[0])) is None:
            return 1
    else:
        shell.show_bar()
    return app.exec()
