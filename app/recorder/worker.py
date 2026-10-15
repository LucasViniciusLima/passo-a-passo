"""Worker que transforma cliques enfileirados em passos com captura."""

from __future__ import annotations

import queue
import traceback

from PySide6.QtCore import QThread, Signal

from app.capture.apps import describe_app
from app.capture.base import ClickEvent, ElementInfo, ElementInspector, KeyEvent, NullInspector, ScreenGrabber
from app.capture.coords import find_monitor, rect_to_image, to_image_point
from app.project.model import Step, default_text
from app.project.storage import ProjectWorkspace
from app.recorder.clicks import action_for, is_double_click
from app.registro import registrar

_STOP = object()
# Tab ou Enter repetido em menos que isso (ou segurado) soma no mesmo passo.
KEY_REPEAT_GAP = 1.0


class CaptureWorker(QThread):
    stepAdded = Signal(object)  # Step
    stepUpdated = Signal(object)  # Step
    failed = Signal(str)

    def __init__(
        self,
        workspace: ProjectWorkspace,
        grabber: ScreenGrabber,
        t0: float,
        double_click: tuple[float, int] = (0.5, 4),
        inspector: ElementInspector | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.queue: queue.Queue = queue.Queue()
        self.workspace = workspace
        self.grabber = grabber
        self.t0 = t0
        self.dc_interval, self.dc_distance = double_click
        self.inspector = inspector or NullInspector()
        self._last_click: ClickEvent | None = None
        self._last_place: str | None = None
        self._last_key: KeyEvent | None = None
        self._key_place: str | None = None

    def submit(self, event: ClickEvent | KeyEvent) -> None:
        self.queue.put(event)

    def stop(self) -> None:
        """Processa o que ainda está na fila e encerra."""
        self.queue.put(_STOP)

    def run(self) -> None:
        try:
            while True:
                item = self.queue.get()
                if item is _STOP:
                    break
                try:
                    if isinstance(item, KeyEvent):
                        self._process_key(item)
                    else:
                        self._process(item)
                except Exception as exc:  # um clique com erro não derruba a gravação
                    registrar(f"Passo descartado ({item}): {exc}\n{traceback.format_exc()}")
                    self.failed.emit(f"Falha ao capturar o passo: {exc}")
        finally:
            self.grabber.close()

    def _inspect(self, x: int, y: int):
        """Janela e app sob o ponto. Falhas aqui nunca custam o passo: fica o texto padrão."""
        try:
            info = self.inspector.inspect(x, y)
        except Exception as exc:
            registrar(f"Inspeção do elemento falhou em ({x}, {y}); passo gravado com texto padrão: {exc}")
            info = ElementInfo()
        try:
            app = describe_app(info.exe_path, info.root_class, info.window_title)
        except Exception as exc:
            registrar(f"Nome do app indisponível ({info.exe_path}): {exc}")
            app = None
        return info, app

    def _process(self, event: ClickEvent) -> None:
        self._last_key = None
        steps = self.workspace.project.steps
        if (
            steps
            and steps[-1].action == "click"
            and is_double_click(self._last_click, event, self.dc_interval, self.dc_distance)
        ):
            # Mantém a captura do primeiro clique e só muda a ação.
            step = steps[-1]
            step.action = "double_click"
            step.text = default_text(
                "double_click", len(steps), self._last_place, step.element_name, step.element_type
            )
            self.workspace.flush()
            self._last_click = None
            self.stepUpdated.emit(step)
            return
        self._last_click = event

        # Janela sob o clique, lida antes da captura para pegar o estado mais próximo do clique.
        info, app = self._inspect(event.x, event.y)
        self._last_place = app.place if app else None

        monitor = find_monitor(event.x, event.y, self.grabber.monitors())
        image = self.grabber.grab(monitor)
        rel, path = self.workspace.next_image_path()
        image.save(path, "PNG", compress_level=3)

        action = action_for(event.button)
        step = Step(
            image=rel,
            point=to_image_point(event.x, event.y, monitor, image.size),
            action=action,
            button=event.button,
            monitor=monitor.index,
            scale=monitor.scale,
            timestamp=round(max(event.time - self.t0, 0.0), 2),
            text=default_text(action, len(steps) + 1, self._last_place, info.element_name, info.element_type),
            app_name=app.name if app else None,
            window_title=info.window_title,
            control_class=info.control_class,
            element_name=info.element_name,
            element_type=info.element_type,
            focus_rect=rect_to_image(info.window_rect, monitor, image.size),
        )
        self.workspace.add_step(step)
        self.stepAdded.emit(step)

    def _process_key(self, event: KeyEvent) -> None:
        steps = self.workspace.project.steps
        last = self._last_key
        self._last_key = event
        self._last_click = None
        if (
            last is not None
            and steps
            and steps[-1].action == "key"
            and steps[-1].key == event.key
            and 0 <= event.time - last.time <= KEY_REPEAT_GAP
        ):
            # Tab segurado ou vários seguidos: um passo só, com a contagem.
            step = steps[-1]
            step.count += 1
            step.text = default_text("key", len(steps), self._key_place, key=step.key, count=step.count)
            self.workspace.flush()
            self.stepUpdated.emit(step)
            return

        try:
            point = self.inspector.focus_point()
        except Exception as exc:
            registrar(f"Foco do teclado indisponível; usando o centro da tela: {exc}")
            point = None
        monitors = self.grabber.monitors()
        if point is None:
            m = monitors[0]
            point = (m.left + m.width // 2, m.top + m.height // 2)
        x, y = point
        info, app = self._inspect(x, y)
        self._key_place = app.place if app else None

        monitor = find_monitor(x, y, monitors)
        image = self.grabber.grab(monitor)
        rel, path = self.workspace.next_image_path()
        image.save(path, "PNG", compress_level=3)
        step = Step(
            image=rel,
            point=to_image_point(x, y, monitor, image.size),
            action="key",
            button="",
            monitor=monitor.index,
            scale=monitor.scale,
            timestamp=round(max(event.time - self.t0, 0.0), 2),
            text=default_text("key", len(steps) + 1, self._key_place, key=event.key),
            app_name=app.name if app else None,
            window_title=info.window_title,
            control_class=info.control_class,
            focus_rect=rect_to_image(info.window_rect, monitor, image.size),
            key=event.key,
        )
        self.workspace.add_step(step)
        self.stepAdded.emit(step)
