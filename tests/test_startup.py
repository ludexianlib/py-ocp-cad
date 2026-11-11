"""Startup gates: loading stages, viewport readiness and a subsequent frame."""

import unittest

from PyQt6.QtCore import QCoreApplication, QObject, pyqtProperty, pyqtSignal

from app.application.startup_controller import StartupController


class TestViewport(QObject):
    render_state_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._ready = False
        self._error = ""

    @pyqtProperty(bool)
    def render_ready(self):
        return self._ready

    @pyqtProperty(str)
    def error_text(self):
        return self._error

    def report(self, ready, error=""):
        self._ready, self._error = ready, error
        self.render_state_changed.emit()


class TestWindow(QObject):
    frameSwapped = pyqtSignal()
    sceneGraphError = pyqtSignal(int, str)
    visibleChanged = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.viewport = TestViewport()
        self.hidden = False
        self.activated = False

    def findChild(self, _kind, _name):
        return self.viewport

    def update(self):
        pass

    def hide(self):
        self.hidden = True

    def raise_(self):
        pass

    def requestActivate(self):
        self.activated = True


class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.startup = StartupController()
        self.window = TestWindow()
        self.startup.watch_window(self.window)
        self.addCleanup(self.startup.shutdown)

    def finish_loading(self):
        engine = QObject()

        def steps():
            yield from ()
            return engine, None

        self.startup._steps = steps()
        self.startup._next_stage()

    def swap_frame(self):
        self.window.frameSwapped.emit()
        self.application.processEvents()

    def test_qml_load_and_early_frames_do_not_complete_startup(self):
        self.finish_loading()
        self.swap_frame()
        self.assertFalse(self.startup.ready)
        self.assertEqual(self.startup.progress, 95)
        self.window.viewport.report(True)
        self.assertFalse(self.startup.ready)
        self.swap_frame()
        self.assertTrue(self.startup.ready)
        self.assertEqual(self.startup.progress, 100)

    def test_ready_frame_before_loader_return_still_waits_for_loading(self):
        self.window.viewport.report(True)
        self.swap_frame()
        self.assertFalse(self.startup.ready)
        self.finish_loading()
        self.assertTrue(self.startup.ready)

    def test_progress_is_monotonic_and_cannot_reach_100_early(self):
        self.startup.advance(50, "正在创建模型")
        self.startup.advance(20, "旧的阶段")
        self.assertEqual(self.startup.progress, 50)
        self.assertEqual(self.startup.stage_text, "正在创建模型")
        self.startup.advance(100, "等待首帧")
        self.assertEqual(self.startup.progress, 95)
        self.assertFalse(self.startup.ready)

    def test_render_error_keeps_failure_and_never_completes(self):
        self.finish_loading()
        self.window.viewport.report(False, "图形初始化失败")
        self.assertTrue(self.startup.failed)
        self.assertTrue(self.window.hidden)
        self.window.viewport.report(True)
        self.swap_frame()
        self.startup.advance(100, "完成")
        self.assertFalse(self.startup.ready)
        self.assertEqual(self.startup.error_text, "图形初始化失败")
        exits = []
        self.startup.exit_requested.connect(exits.append)
        self.startup.request_exit()
        self.assertEqual(exits, [1])

    def test_splash_dismissal_requires_completion_and_is_idempotent(self):
        dismissed = []
        self.startup.splash_dismissed.connect(lambda: dismissed.append(True))
        self.startup.finish_splash()
        self.assertEqual(dismissed, [])
        self.finish_loading()
        self.window.viewport.report(True)
        self.swap_frame()
        self.startup.finish_splash()
        self.startup.finish_splash()
        self.assertEqual(dismissed, [True])
        self.assertTrue(self.window.activated)

    def test_cancel_prevents_late_loading_and_readiness(self):
        exits = []
        self.startup.exit_requested.connect(exits.append)
        self.startup.request_exit()
        self.startup.advance(90, "后续阶段")
        self.window.viewport.report(True)
        self.swap_frame()
        self.assertEqual(exits, [0])
        self.assertEqual(self.startup.progress, 0)
        self.assertFalse(self.startup.ready)

    def test_closing_main_window_before_splash_exit_cancels_activation(self):
        self.finish_loading()
        self.window.viewport.report(True)
        self.swap_frame()
        exits = []
        self.startup.exit_requested.connect(exits.append)
        self.window.visibleChanged.emit(False)
        self.startup.finish_splash()
        self.assertEqual(exits, [0])
        self.assertFalse(self.window.activated)


if __name__ == "__main__":
    unittest.main()
