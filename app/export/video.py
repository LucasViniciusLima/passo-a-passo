"""Exportação para MP4 (H.264) e GIF: quadros da linha do tempo enviados ao FFmpeg por pipe."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import imageio_ffmpeg

from app.export import Cancelled, GifOptions, Progress, VideoOptions, check_cancel
from app.project.model import Project
from app.render.timeline import Timeline

# pythonw não tem console; sem isso o FFmpeg abriria uma janela preta.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _even(x: float) -> int:
    """H.264 com yuv420p exige largura e altura pares."""
    return max(int(round(x / 2)) * 2, 2)


def _run(timeline: Timeline, output_args: list[str], dest: Path,
         progress: Progress | None, cancel: threading.Event | None) -> Path:
    dest = Path(dest)
    partial = dest.with_name(dest.stem + ".parcial" + dest.suffix)
    cmd = [
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{timeline.W}x{timeline.H}", "-r", str(timeline.fps),
        "-i", "-", *output_args, str(partial),
    ]
    total = timeline.total_frames()
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
                                creationflags=_NO_WINDOW)
        try:
            for i, frame in enumerate(timeline.frames()):
                check_cancel(cancel)
                proc.stdin.write(frame.tobytes())
                if progress and (i % 5 == 0 or i == total - 1):
                    progress(min((i + 1) / total, 1.0) * 0.98)
            proc.stdin.close()
            code = proc.wait()
        except (Cancelled, BrokenPipeError, OSError) as exc:
            proc.kill()
            proc.wait()
            partial.unlink(missing_ok=True)
            if isinstance(exc, Cancelled):
                raise
            log.seek(0)
            raise RuntimeError(f"O FFmpeg parou com erro: {log.read().decode(errors='replace')[-800:]}") from exc
        except BaseException:
            proc.kill()
            proc.wait()
            partial.unlink(missing_ok=True)
            raise
        if code != 0:
            partial.unlink(missing_ok=True)
            log.seek(0)
            raise RuntimeError(f"O FFmpeg terminou com código {code}: {log.read().decode(errors='replace')[-800:]}")
    partial.replace(dest)
    if progress:
        progress(1.0)
    return dest


def export_mp4(
    project: Project,
    root: str | Path,
    dest: str | Path,
    options: VideoOptions | None = None,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    o = options or VideoOptions()
    height = _even(o.height)
    timeline = Timeline(project, root, (_even(height * 16 / 9), height), o.fps,
                        o.seconds_per_step, o.transition, o.transition_seconds)
    args = ["-c:v", "libx264", "-preset", "medium", "-crf", str(o.crf), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart"]
    return _run(timeline, args, Path(dest), progress, cancel)


def export_gif(
    project: Project,
    root: str | Path,
    dest: str | Path,
    options: GifOptions | None = None,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    o = options or GifOptions()
    width = _even(o.width)
    timeline = Timeline(project, root, (width, _even(width * 9 / 16)), o.fps,
                        o.seconds_per_step, o.transition, o.transition_seconds)
    # Duas passadas no mesmo comando: palettegen monta a paleta, paletteuse aplica.
    graph = (f"split[a][b];[a]palettegen=max_colors={o.max_colors}:stats_mode=diff[p];"
             "[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle")
    args = ["-filter_complex", graph, "-loop", "0"]
    return _run(timeline, args, Path(dest), progress, cancel)
