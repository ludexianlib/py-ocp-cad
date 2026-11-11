"""Startup gates: loading stages, viewport readiness and a subsequent frame."""

import unittest
from unittest.mock import Mock, call, patch

from PyQt6.QtCore import QCoreApplication, QObject, QPoint, QRect, pyqtProperty, pyqtSignal

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

    def __init__(self, width=1360, height=900):
        super().__init__()
        self.viewport = TestViewport()
        self.hidden = False
        self.activated = False
        self._width, self._height = width, height
        self.selected_screen = None
        self.position = None
        self.placement_events = []
        self.persistent_graphics = True
        self.persistent_scene_graph = True
        self.graphics_when_hidden = None

    def findChild(self, _kind, _name):
        return self.viewport

    def update(self):
        pass

    def setPersistentGraphics(self, persistent):
        self.persistent_graphics = persistent

    def setPersistentSceneGraph(self, persistent):
        self.persistent_scene_graph = persistent

    def hide(self):
        self.graphics_when_hidden = (self.persistent_graphics, self.persistent_scene_graph)
        self.hidden = True

    def close(self):
        self.hide()

    def width(self):
        return self._width

    def height(self):
        return self._height

    def setScreen(self, screen):
        self.selected_screen = screen
        self.placement_events.append("screen")

    def setPosition(self, x, y):
        self.position = QPoint(x, y)
        self.placement_events.append("position")

    def show(self):
        self.hidden = False
        self.placement_events.append("show")

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

    def test_launch_screen_is_reused_after_cursor_moves_before_main_creation(self):
        primary, secondary = Mock(), Mock()
        primary.availableGeometry.return_value = QRect(0, 0, 1920, 1040)
        secondary.availableGeometry.return_value = QRect(-2560, 40, 2560, 1400)
        splash = TestWindow(540, 330)
        main_window = TestWindow()
        engine = Mock()
        engine.rootObjects.return_value = [splash]
        with patch("app.application.startup_controller.QGuiApplication") as application, \
                patch("app.application.startup_controller.QCursor") as cursor, \
                patch("PyQt6.QtQml.QQmlApplicationEngine", return_value=engine):
            application.screenAt.return_value = secondary
            application.screens.return_value = [primary, secondary]
            application.primaryScreen.return_value = primary
            cursor.pos.return_value = QPoint(-1200, 600)
            self.startup.start(step for step in [])
            application.screenAt.return_value = primary
            cursor.pos.return_value = QPoint(800, 600)
            self.startup._disconnect_window()
            self.startup.watch_window(main_window)
            application.screenAt.assert_called_once_with(QPoint(-1200, 600))
            cursor.pos.assert_called_once()
            application.primaryScreen.assert_not_called()
        self.assertIs(splash.selected_screen, secondary)
        self.assertIs(main_window.selected_screen, secondary)
        self.assertEqual(splash.position, QPoint(-1550, 575))
        self.assertEqual(main_window.position, QPoint(-1960, 290))
        self.assertEqual(splash.placement_events, ["screen", "position", "show"])
        self.assertEqual(main_window.placement_events, ["screen", "position", "show"])

    def test_cursor_outside_screens_uses_primary_available_area(self):
        primary = Mock()
        primary.availableGeometry.return_value = QRect(0, 40, 800, 560)
        splash = TestWindow(540, 330)
        engine = Mock()
        engine.rootObjects.return_value = [splash]
        with patch("app.application.startup_controller.QGuiApplication") as application, \
                patch("app.application.startup_controller.QCursor") as cursor, \
                patch("PyQt6.QtQml.QQmlApplicationEngine", return_value=engine):
            application.screenAt.return_value = None
            application.primaryScreen.return_value = primary
            application.screens.return_value = [primary]
            cursor.pos.return_value = QPoint(9000, 9000)
            self.startup.start(step for step in [])
            self.startup._show_on_launch_screen(self.window)
        self.assertIs(splash.selected_screen, primary)
        self.assertEqual(splash.position, QPoint(130, 155))
        self.assertEqual(self.window.position, QPoint(0, 40))

    def test_removed_launch_screen_falls_back_to_primary_without_rereading_cursor(self):
        primary, removed = Mock(), Mock()
        primary.availableGeometry.return_value = QRect(100, -1000, 1920, 1040)
        removed.availableGeometry.return_value = QRect(-1920, 0, 1920, 1040)
        splash = TestWindow(540, 330)
        engine = Mock()
        engine.rootObjects.return_value = [splash]
        with patch("app.application.startup_controller.QGuiApplication") as application, \
                patch("app.application.startup_controller.QCursor") as cursor, \
                patch("PyQt6.QtQml.QQmlApplicationEngine", return_value=engine):
            application.screenAt.return_value = removed
            application.primaryScreen.return_value = primary
            application.screens.return_value = [primary, removed]
            self.startup.start(step for step in [])
            application.screens.return_value = [primary]
            self.startup._show_on_launch_screen(self.window)
            cursor.pos.assert_called_once()
            application.screenAt.assert_called_once()
        self.assertIs(self.window.selected_screen, primary)
        self.assertEqual(self.window.position, QPoint(380, -930))

    def test_loading_waits_for_progress_animation_and_schedules_only_once(self):
        splash = TestWindow(540, 330)
        splash.setProperty("progress_animating", True)
        self.startup._splash_window = splash
        self.startup._waiting_for_stage = True
        self.startup.advance(35, "Loading modules")

        with patch("app.application.startup_controller.QTimer.singleShot") as schedule:
            self.startup._on_splash_frame()
            self.startup._on_splash_frame()
            schedule.assert_not_called()
            self.assertTrue(self.startup._waiting_for_stage)

            splash.setProperty("progress_animating", False)
            self.startup._on_splash_frame()
            self.startup._on_splash_frame()
            schedule.assert_called_once_with(0, self.startup._next_stage)
            self.assertFalse(self.startup._waiting_for_stage)

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
        self.assertFalse(self.startup.workspace_visible)

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
        self.assertFalse(self.startup.workspace_visible)
        self.assertEqual(self.startup.error_text, "图形初始化失败")
        exits = []
        self.startup.exit_requested.connect(exits.append)
        self.startup.request_exit()
        self.assertEqual(exits, [1])

    def test_splash_dismissal_requires_completion_and_is_idempotent(self):
        dismissed = []
        splash = TestWindow(540, 330)
        engine = Mock()
        self.startup._splash_window = splash
        self.startup._splash_engine = engine
        self.startup.splash_dismissed.connect(
            lambda: dismissed.append((self.startup.workspace_visible, splash.hidden, self.window.activated))
        )
        self.startup.finish_splash()
        self.assertEqual(dismissed, [])
        self.assertFalse(self.startup.workspace_visible)
        self.assertFalse(splash.hidden)
        self.finish_loading()
        self.window.viewport.report(True)
        self.swap_frame()
        self.assertTrue(self.startup.ready)
        self.assertFalse(self.startup.workspace_visible)
        self.startup.finish_splash()
        self.startup.finish_splash()
        self.assertEqual(dismissed, [(True, True, True)])
        engine.deleteLater.assert_not_called()
        self.assertEqual(splash.graphics_when_hidden, (False, False))
        self.assertIs(self.startup._splash_engine, engine)
        self.assertIs(self.startup._splash_window, splash)
        self.assertTrue(self.window.activated)

    def test_shutdown_releases_main_before_splash_and_is_idempotent(self):
        cleanup = Mock()
        main_engine, splash_engine = Mock(), Mock()
        cleanup.attach_mock(main_engine.deleteLater, "main")
        cleanup.attach_mock(splash_engine.deleteLater, "splash")
        self.startup.main_engine = main_engine
        self.startup._splash_engine = splash_engine
        splash = TestWindow(540, 330)
        self.startup._splash_window = splash

        self.startup.shutdown()
        self.startup.shutdown()

        self.assertEqual(cleanup.mock_calls, [call.main(), call.splash()])
        self.assertTrue(self.window.hidden)
        self.assertTrue(splash.hidden)
        self.assertEqual(splash.graphics_when_hidden, (False, False))
        self.assertIsNone(self.startup.main_engine)
        self.assertIsNone(self.startup._splash_engine)
        self.assertIsNone(self.startup._splash_window)

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
        self.assertFalse(self.startup.workspace_visible)

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
        self.assertFalse(self.startup.workspace_visible)


if __name__ == "__main__":
    unittest.main()
