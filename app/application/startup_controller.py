"""Stage startup behind a splash and wait for a presented, ready main window."""

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, Qt, pyqtProperty, pyqtSignal, pyqtSlot


class StartupController(QObject):
    state_changed = pyqtSignal()
    splash_dismissed = pyqtSignal()
    exit_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0
        self._stage_text = "正在准备启动…"
        self._error_text = ""
        self._ready = False
        self._steps = None
        self._waiting_for_stage = False
        self._engine_loaded = False
        self._viewport_ready = False
        self._frame_presented = False
        self._window = None
        self._viewport = None
        self._watching_window = False
        self._splash_engine = None
        self._splash_window = None
        self._dismissed = False
        self._cancelled = False
        self.main_engine = None

    @pyqtProperty(int, notify=state_changed)
    def progress(self):
        return self._progress

    @pyqtProperty(str, notify=state_changed)
    def stage_text(self):
        return self._stage_text

    @pyqtProperty(str, notify=state_changed)
    def error_text(self):
        return self._error_text

    @pyqtProperty(bool, notify=state_changed)
    def failed(self):
        return bool(self._error_text)

    @pyqtProperty(bool, notify=state_changed)
    def ready(self):
        return self._ready

    def advance(self, progress, text):
        if self.failed or self._ready or self._cancelled:
            return
        progress = min(95, int(progress))
        if progress < self._progress:
            return
        self._progress = progress
        self._stage_text = text
        self.state_changed.emit()

    def start(self, steps):
        """Show the light QML splash before consuming any heavy loading stages."""
        from PyQt6.QtQml import QQmlApplicationEngine, QQmlEngine

        if self._steps is not None or self._splash_engine is not None:
            raise RuntimeError("启动流程已经开始。")
        self._steps = iter(steps)
        QQmlEngine.setObjectOwnership(self, QQmlEngine.ObjectOwnership.CppOwnership)
        self._splash_engine = QQmlApplicationEngine()
        self._splash_engine.setInitialProperties({"startup_controller": self})
        source = Path(__file__).resolve().parents[2] / "qml" / "SplashScreen.qml"
        self._splash_engine.load(QUrl.fromLocalFile(str(source)))
        if not self._splash_engine.rootObjects():
            raise RuntimeError("启动画面加载失败。")
        self._splash_window = self._splash_engine.rootObjects()[0]
        self._splash_window.frameSwapped.connect(self._on_splash_frame, Qt.ConnectionType.QueuedConnection)
        self._splash_window.sceneGraphError.connect(self._on_splash_error, Qt.ConnectionType.QueuedConnection)
        self._waiting_for_stage = True
        self._splash_window.update()

    @pyqtSlot()
    def _on_splash_frame(self):
        # Display each stage before doing its potentially blocking import/work.
        if self._waiting_for_stage and not self.failed and not self._cancelled:
            if self._progress == 0 and self._splash_window.property("opacity") < 0.99:
                return
            self._waiting_for_stage = False
            QTimer.singleShot(0, self._next_stage)

    @pyqtSlot()
    def _next_stage(self):
        if self.failed or self._cancelled:
            return
        try:
            progress, text = next(self._steps)
        except StopIteration as result:
            self.main_engine, _controller = result.value
            self._engine_loaded = True
            self.advance(95, "正在等待主界面首帧…")
            self._complete_if_ready()
            return
        except Exception as error:
            logging.getLogger(__name__).exception("Workspace startup failed")
            self.fail(str(error) or "主界面加载失败，请查看运行日志。")
            return
        self.advance(progress, text)
        self._waiting_for_stage = True
        self._splash_window.update()

    def watch_window(self, window):
        """Observe existing view signals without adding startup logic to CAD."""
        from PyQt6.QtQuick import QQuickItem

        self._window = window
        self._viewport = window.findChild(QQuickItem, "occt_viewport")
        if self._viewport is None:
            raise RuntimeError("主界面缺少三维预览组件。")
        self._viewport.render_state_changed.connect(self._on_viewport_state)
        window.frameSwapped.connect(self._on_window_frame, Qt.ConnectionType.QueuedConnection)
        window.sceneGraphError.connect(self._on_scene_graph_error, Qt.ConnectionType.QueuedConnection)
        window.visibleChanged.connect(self._on_window_visible)
        self._watching_window = True
        self._on_viewport_state()

    @pyqtSlot()
    def _on_viewport_state(self):
        if self.failed or self._ready or self._cancelled:
            return
        message = self._viewport.property("error_text")
        if message:
            self.fail(message)
            return
        self._viewport_ready = bool(self._viewport.property("render_ready"))
        if not self._viewport_ready:
            self._frame_presented = False
        if self._viewport_ready:
            # Require a swap after readiness, not just QML object creation.
            self._window.update()

    @pyqtSlot()
    def _on_window_frame(self):
        if self._viewport_ready:
            self._frame_presented = True
            self._complete_if_ready()

    def _on_scene_graph_error(self, _error, message):
        self.fail("图形界面初始化失败：" + message)

    @pyqtSlot(bool)
    def _on_window_visible(self, visible):
        if not visible and not self.failed and not self._dismissed:
            self.request_exit()

    def _on_splash_error(self, _error, message):
        logging.getLogger(__name__).error("Splash graphics initialization failed: %s", message)
        self.fail("启动画面初始化失败：" + message)
        self.request_exit()

    def _complete_if_ready(self):
        if (self._engine_loaded and self._viewport_ready and self._frame_presented
                and not self.failed and not self._ready and not self._cancelled):
            self._progress = 100
            self._stage_text = "工作台已就绪"
            self._ready = True
            self.state_changed.emit()
            logging.getLogger(__name__).info("Startup complete: main window frame presented")

    def fail(self, message):
        if self._ready or self.failed or self._cancelled:
            return
        self._error_text = message
        self._stage_text = "启动失败"
        self._waiting_for_stage = False
        if self._window is not None:
            self._window.hide()
        self.state_changed.emit()

    @pyqtSlot()
    def finish_splash(self):
        if not self._ready or self._dismissed or self._cancelled:
            return
        self._dismissed = True
        if self._splash_engine is not None:
            self._splash_engine.deleteLater()
            self._splash_engine = self._splash_window = None
        if self._window is not None:
            self._disconnect_window()
            self._window.raise_()
            self._window.requestActivate()
        self.splash_dismissed.emit()

    def _disconnect_window(self):
        if self._window is None or not self._watching_window:
            return
        self._watching_window = False
        for signal, slot in ((self._window.frameSwapped, self._on_window_frame),
                             (self._window.sceneGraphError, self._on_scene_graph_error),
                             (self._window.visibleChanged, self._on_window_visible),
                             (self._viewport.render_state_changed, self._on_viewport_state)):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    @pyqtSlot()
    def request_exit(self):
        if self._dismissed:
            return
        self._cancelled = True
        self._waiting_for_stage = False
        self.exit_requested.emit(1 if self.failed else 0)

    def shutdown(self):
        self._cancelled = True
        self._disconnect_window()
        if self._steps is not None:
            self._steps.close()
        for engine in (self._splash_engine, self.main_engine):
            if engine is not None:
                engine.deleteLater()
        self._splash_engine = self._splash_window = self.main_engine = None
