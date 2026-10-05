"""Exportação: PDF, MP4 e GIF, tema com logo e cancelamento."""

import os
import re
import threading
import time
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # nada aparece na tela

import imageio_ffmpeg
import pytest
from PIL import Image, ImageDraw

from app.export import Cancelled, GifOptions, PdfOptions, VideoOptions
from app.export.pdf import export_pdf
from app.export.video import export_gif, export_mp4
from app.project.model import Step
from app.project.storage import ProjectWorkspace, open_passo
from app.render.timeline import Timeline
from app.theme import LOGO_FILE, contrast_ratio, set_logo

TEXTOS = ["Passo 1: Clique no botao Iniciar", "Passo 2: Abra o menu Arquivo", "Passo 3: Clique no campo Nome"]


@pytest.fixture
def ws(tmp_path):
    ws = ProjectWorkspace(root=tmp_path / "ws")
    ws.project.title = "Tutorial de teste"
    for i, text in enumerate(TEXTOS):
        rel, path = ws.next_image_path()
        img = Image.new("RGB", (640, 400), (40 + 60 * i, 90, 160))
        ImageDraw.Draw(img).rectangle((100, 80, 500, 300), fill=(230, 230, 230))
        img.save(path)
        ws.add_step(Step(image=rel, point=(200 + 50 * i, 150), text=text, focus_rect=[100, 80, 400, 220]))
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (300, 100), (229, 57, 53, 255)).save(logo)
    set_logo(ws, logo)
    return ws


def _pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


# --- PDF -------------------------------------------------------------------


@pytest.mark.parametrize("per_page, paginas", [(1, 1 + 3), (2, 1 + 2)])
def test_pdf_paginas_e_textos(ws, tmp_path, per_page, paginas):
    dest = tmp_path / "saida.pdf"
    progresso = []
    opts = PdfOptions(steps_per_page=per_page, font="Helvetica", compress=False)
    export_pdf(ws.project, ws.root, dest, opts, progress=progresso.append)
    data = dest.read_bytes()
    assert data.startswith(b"%PDF")
    assert _pdf_pages(data) == paginas  # capa + passos
    for text in TEXTOS + ["Tutorial de teste"]:
        assert text.encode() in data
    assert progresso[-1] == 1.0


def test_pdf_carta_e_fonte_padrao(ws, tmp_path):
    dest = export_pdf(ws.project, ws.root, tmp_path / "carta.pdf", PdfOptions(page_size="Carta"))
    data = dest.read_bytes()
    assert b"792 612" in data  # Carta em paisagem (automático com 1 passo por página)
    dest = export_pdf(ws.project, ws.root, tmp_path / "carta2.pdf",
                      PdfOptions(page_size="Carta", orientation="retrato", compress=False))
    assert b"612 792" in dest.read_bytes()
    assert _pdf_pages(data) == 4


def test_pdf_cancelado_nao_deixa_arquivo(ws, tmp_path):
    cancel = threading.Event()
    cancel.set()
    dest = tmp_path / "cancelado.pdf"
    with pytest.raises(Cancelled):
        export_pdf(ws.project, ws.root, dest, cancel=cancel)
    assert not dest.exists() and not list(tmp_path.glob("cancelado*"))


# --- Linha do tempo ----------------------------------------------------------


@pytest.mark.parametrize("transition", ["esmaecer", "deslizar", "zoom"])
def test_linha_do_tempo_gera_todos_os_quadros(ws, transition):
    tl = Timeline(ws.project, ws.root, (320, 180), fps=5, seconds_per_step=1.0, transition=transition,
                  transition_seconds=0.4)
    frames = list(tl.frames())
    assert len(frames) == tl.total_frames() == 10 + 3 * 5 + 8
    assert all(f.size == (320, 180) and f.mode == "RGB" for f in frames)
    # O quadro do meio de um passo é diferente da abertura (tem captura e legenda).
    assert frames[10 + 3].tobytes() != frames[0].tobytes()


# --- MP4 e GIF ---------------------------------------------------------------


def test_mp4_duracao_e_resolucao(ws, tmp_path):
    dest = tmp_path / "video.mp4"
    opts = VideoOptions(height=360, fps=10, seconds_per_step=1.0, transition_seconds=0.3)
    export_mp4(ws.project, ws.root, dest, opts)
    frames, secs = imageio_ffmpeg.count_frames_and_secs(str(dest))
    esperado = 20 + 3 * 10 + 15  # abertura 2 s + 3 passos de 1 s + encerramento 1,5 s
    assert frames == esperado
    assert secs == pytest.approx(esperado / 10, abs=0.15)
    reader = imageio_ffmpeg.read_frames(str(dest))
    meta = next(reader)
    reader.close()
    assert tuple(meta["size"]) == (640, 360)
    assert not list(tmp_path.glob("*.parcial.*"))


def test_gif_quadros_tamanho_e_loop(ws, tmp_path):
    dest = tmp_path / "anim.gif"
    opts = GifOptions(width=320, fps=5, seconds_per_step=1.0, transition_seconds=0.4)
    export_gif(ws.project, ws.root, dest, opts)
    with Image.open(dest) as gif:
        assert gif.size == (320, 180)
        assert gif.info.get("loop") == 0  # repetição infinita
        assert gif.n_frames == 10 + 3 * 5 + 8


def test_video_cancelado_remove_arquivo_parcial(ws, tmp_path):
    cancel = threading.Event()
    chamadas = []

    def progress(v):
        chamadas.append(v)
        if len(chamadas) >= 2:
            cancel.set()

    dest = tmp_path / "cancelado.mp4"
    with pytest.raises(Cancelled):
        export_mp4(ws.project, ws.root, dest, VideoOptions(height=360, fps=10), progress=progress, cancel=cancel)
    assert not dest.exists()
    assert not list(tmp_path.glob("cancelado*"))


# --- Tema --------------------------------------------------------------------


def test_tema_e_logo_salvos_e_reabertos(ws, tmp_path):
    theme = ws.project.theme
    theme.highlight_color = "#1E88E5"
    theme.margin_color = "#FFF8E1"
    theme.page_background = "#263238"
    theme.text_color = "#ECEFF1"
    theme.spotlight.mode = "circulo"
    dest = ws.save_to(tmp_path / "com-tema.passo")
    with zipfile.ZipFile(dest) as zf:
        assert LOGO_FILE in zf.namelist()
    aberto = open_passo(dest)
    try:
        assert aberto.project.theme == theme
        with Image.open(aberto.root / LOGO_FILE) as logo:
            assert logo.size == (300, 100)
    finally:
        aberto.cleanup()


def test_logo_svg_vira_png(ws, tmp_path, qapp):
    svg = tmp_path / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
                   '<rect width="200" height="100" fill="#E53935"/></svg>', encoding="utf-8")
    set_logo(ws, svg)
    with Image.open(ws.root / LOGO_FILE) as logo:
        assert logo.size[0] / logo.size[1] == pytest.approx(2, rel=0.02)
        assert logo.convert("RGB").getpixel((10, 10)) == (229, 57, 53)


def test_contraste():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21)
    assert contrast_ratio("#212121", "#212121") == pytest.approx(1)
    assert contrast_ratio("#212121", "#FFFFFF") > 4.5


# --- Interface (offscreen) ----------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_dialogo_exporta_gif(ws, tmp_path, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.ui.export_dialog import ExportDialog

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dialog = ExportDialog(ws, tmp_path)
    assert dialog.path.text().endswith("Tutorial de teste.pdf")
    dialog.format.setCurrentIndex(1)  # GIF
    assert dialog.path.text().endswith(".gif")
    dialog.gif_width.setValue(320)
    dialog.gif_fps.setValue(5)
    dialog.gif_seconds.setValue(1.0)
    dialog.start_export()
    fim = time.monotonic() + 60
    while dialog.worker is not None and time.monotonic() < fim:
        qapp.processEvents()
        time.sleep(0.02)
    assert dialog.result_path is not None and dialog.result_path.exists()
    assert dialog.bar.value() == 1000


def test_painel_aparencia_muda_tema(ws, qapp):
    from app.ui.appearance_panel import AppearancePanel

    panel = AppearancePanel(ws)
    sinais = []
    panel.changed.connect(lambda: sinais.append(1))
    panel.set_color("highlight_color", "#00897b")
    assert ws.project.theme.highlight_color == "#00897B" and sinais
    panel.set_color("text_color", "#EEEEEE")  # texto claro sobre margem branca
    assert panel.contrast_warning.isVisibleTo(panel)
    panel.spotlight.setCurrentIndex(panel.spotlight.findData("desligado"))
    assert ws.project.theme.spotlight.mode == "desligado"
