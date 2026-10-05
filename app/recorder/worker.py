"""Worker que transforma cliques enfileirados em passos com captura."""

from __future__ import annotations

import queue

from PySide6.QtCore import QThread, Signal

from app.capture.apps import describe_app
from app.capture.base import ClickEvent, ElementInfo, ElementInspector, NullInspector, ScreenGrabber
from app.capture.coords import find_monitor, rect_to_image, to_image_point
from app.project.model import Step, default_text
from app.project.storage import ProjectWorkspace
from app.recorder.clicks import action_for, is_double_click

_STOP = object()


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

    def submit(self, event: ClickEvent) -> None:
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
                    self._process(item)
                except Exception as exc:  # um clique com erro não derruba a gravação
                    self.failed.emit(f"Falha ao capturar o clique: {exc}")
        finally:
            self.grabber.close()

    def _process(self, event: ClickEvent) -> None:
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
        try:
            info = self.inspector.inspect(event.x, event.y)
        except Exception:  # nunca perder o passo por causa do inspetor
            info = ElementInfo()
        app = describe_app(info.exe_path, info.root_class, info.window_title)
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
