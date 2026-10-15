# PyInstaller (onedir, sem console). Na raiz do repositório:
#   .venv\Scripts\pyinstaller packaging\PassoAPasso.spec --noconfirm
# Saída: dist\Passo a Passo\Passo a Passo.exe

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent

# Os wrappers do UI Automation (comtypes.gen) são gerados aqui, na build, e vão
# junto como módulos: o executável não precisa gerá-los nem gravar em disco.
import comtypes.client

comtypes.client.GetModule("UIAutomationCore.dll")
from comtypes.gen import UIAutomationClient  # noqa: E402,F401

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("comtypes.gen")
    + collect_submodules("pynput")
    + ["imageio_ffmpeg.binaries"]
)

# FFmpeg do imageio-ffmpeg (o hook já pega; repetido para não depender dele).
datas = collect_data_files("imageio_ffmpeg", subdir="binaries")
# Assets do app, se um dia existirem (fontes vêm do Windows: Segoe UI/Arial).
assets = ROOT / "app" / "assets"
if assets.is_dir():
    datas.append((str(assets), "app/assets"))

icon = next((str(p) for p in (ROOT / "packaging" / "icone.ico", ROOT / "app" / "assets" / "icone.ico") if p.is_file()), None)

a = Analysis(
    [str(ROOT / "packaging" / "passo_a_passo.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "_pytest", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Passo a Passo",
    console=False,
    icon=icon,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Passo a Passo", upx=False)
