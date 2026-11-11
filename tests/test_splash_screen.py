"""Desktop startup check: python tests/test_splash_screen.py --render-check."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class SplashScreenTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("CAD_RUN_VIEWPORT_TESTS") == "1", "Requires a desktop GPU")
    def test_splash_waits_for_ready_frame_and_handles_failure(self):
        for mode, marker in (("--render-check", "SPLASH_CHECK_OK"),
                             ("--secondary-screen-check", "SPLASH_CHECK_OK"),
                             ("--failure-check", "SPLASH_FAILURE_CHECK_OK")):
            with self.subTest(mode=mode):
                completed = subprocess.run(
                    [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), mode],
                    cwd=Path(__file__).resolve().parents[1], capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=45,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn(marker, completed.stdout)


def startup_check(failure=False, secondary=False):
    import json
    import time

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, QTimer, Qt, qInstallMessageHandler
    from PyQt6.QtGui import QCursor, QGuiApplication, QMouseEvent
    from PyQt6.QtQuick import QQuickItem
    from app.application.startup_controller import StartupController
    from main import _create_engine_steps, configure_fonts, configure_graphics

    configure_graphics()
    application = QGuiApplication([])
    configure_fonts(application)
    screens = application.screens()
    launch_screen = screens[min(1, len(screens) - 1)] if secondary else screens[0]
    other_screen = next((screen for screen in screens if screen != launch_screen), None)
    original_cursor_position = QCursor.pos()
    messages = []
    qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))
    output = project_root / "out"
    output.mkdir(exist_ok=True)
    startup = StartupController(application)
    startup.exit_requested.connect(application.exit)
    state = {"held": False, "waiting_checked": False, "snapshot": False, "dismissed": False,
             "error": None, "failure_checked": False, "exit_posted": False, "cursor_crossed": False,
             "ready_hidden_checked": False, "fade_checked": False,
             "animated_targets": [], "final_progress_animated": False, "full_progress_checked": False}
    displayed_progress = [0.0]
    progress = [0]
    startup.state_changed.connect(lambda: progress.append(startup.progress))
    startup.splash_dismissed.connect(lambda: state.update(dismissed=True))
    deadline = time.monotonic() + 25

    def check_screen(window):
        assert window.screen() == launch_screen, (window.screen().name(), launch_screen.name())
        assert launch_screen.availableGeometry().contains(window.frameGeometry().center()), window.frameGeometry()

    def stages():
        # No workspace dependency has been imported before the splash is visible.
        assert startup._splash_window.isVisible()
        assert startup._splash_window.property("opacity") > 0
        check_screen(startup._splash_window)
        if other_screen is not None:
            QCursor.setPos(other_screen.availableGeometry().center())
            assert application.screenAt(QCursor.pos()) == other_screen
            state["cursor_crossed"] = True
        if failure:
            yield 35, "正在加载模块…"
            raise RuntimeError("测试模块加载失败")
        from app.cad.views.occt_viewport import OcctViewport

        original = OcctViewport._set_render_state

        def hold_ready(viewport, ready, error):
            if ready and not error:
                state["held"] = True
                QTimer.singleShot(1400, lambda: original(viewport, ready, error))
            else:
                original(viewport, ready, error)

        OcctViewport._set_render_state = hold_ready
        try:
            steps = _create_engine_steps(application, startup)
            while True:
                assert not startup._splash_window.property("progress_animating")
                try:
                    phase = next(steps)
                except StopIteration as result:
                    return result.value
                if phase[0] == 70:
                    assert startup._splash_window.grabWindow().save(str(output / "splash-preview.png"))
                    state["snapshot"] = True
                yield phase
        finally:
            OcctViewport._set_render_state = original

    def advance():
        try:
            assert time.monotonic() < deadline, ("Startup timed out", progress, messages)
            visible_content = [window for window in application.topLevelWindows()
                               if window.isVisible() and window.opacity() > 0.001]
            assert len(visible_content) <= 1, "Splash and main window must not appear together"
            splash = startup._splash_window
            if not state["dismissed"]:
                displayed = splash.property("displayed_progress")
                assert displayed_progress[-1] - 1e-6 <= displayed <= startup.progress + 1e-6
                displayed_progress.append(displayed)
                bar = splash.findChild(QQuickItem, "startup_progress")
                percentage = splash.findChild(QQuickItem, "startup_percentage")
                assert abs(bar.property("value") - displayed) < 1e-6
                assert percentage.property("text") == f"{int(displayed)}%"
                if 0 < displayed < startup.progress and startup.progress not in state["animated_targets"]:
                    state["animated_targets"].append(startup.progress)
                if startup.ready:
                    if displayed < 100:
                        state["final_progress_animated"] = True
                        assert splash.opacity() >= 0.99, "Splash must stay opaque until progress reaches 100"
                    else:
                        state["full_progress_checked"] = True
            if failure:
                if not startup.failed:
                    return
                assert not startup.ready and startup.progress < 100
                assert not startup.workspace_visible
                assert startup.error_text == "测试模块加载失败"
                splash = startup._splash_window
                assert splash.isVisible()
                check_screen(splash)
                if not state["exit_posted"]:
                    button = splash.findChild(QQuickItem, "startup_exit_button")
                    if not button.isVisible():
                        return
                    # Let the error layout render before capturing and clicking.
                    if not state["failure_checked"]:
                        state["failure_checked"] = True
                        return
                    assert splash.grabWindow().save(str(output / "splash-error-preview.png"))
                    position = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
                    global_position = QPointF(splash.mapToGlobal(position.toPoint()))
                    press = QMouseEvent(QEvent.Type.MouseButtonPress, position, global_position,
                                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                        Qt.KeyboardModifier.NoModifier)
                    QCoreApplication.postEvent(splash, press)

                    def release_button():
                        release = QMouseEvent(QEvent.Type.MouseButtonRelease, position, global_position,
                                              Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                              Qt.KeyboardModifier.NoModifier)
                        QCoreApplication.postEvent(splash, release)

                    QTimer.singleShot(60, release_button)
                    state["exit_posted"] = True
                return
            if startup.failed:
                raise AssertionError(startup.error_text)
            if startup._window is not None:
                check_screen(startup._window)
                if not state["dismissed"]:
                    assert startup._window.opacity() == 0, "Main window must remain transparent until splash is hidden"
                    assert not startup._window.findChild(QQuickItem, "workspace_content").isEnabled()
                    if startup.ready:
                        assert startup._viewport.property("render_ready")
                        state["ready_hidden_checked"] = True
            if state["held"] and not startup.ready:
                assert startup.progress < 100
                assert startup._splash_window.isVisible()
                state["waiting_checked"] = True
                if startup.main_engine is not None:
                    window = startup.main_engine.rootObjects()[0]
                    assert not window.findChild(QQuickItem, "workspace_content").isEnabled()
            if not state["dismissed"]:
                return
            assert startup.ready and startup.progress == 100
            assert startup.workspace_visible
            assert state["ready_hidden_checked"]
            window = startup.main_engine.rootObjects()[0]
            if window.opacity() < 1:
                if window.opacity() > 0:
                    state["fade_checked"] = True
                assert not window.findChild(QQuickItem, "workspace_content").isEnabled()
                return
            assert state["fade_checked"], "Main window must fade in after splash dismissal"
            assert len(state["animated_targets"]) >= 3, state["animated_targets"]
            assert state["final_progress_animated"] and state["full_progress_checked"]
            assert state["waiting_checked"] and state["snapshot"]
            assert progress == sorted(progress)
            visible = [window for window in application.topLevelWindows() if window.isVisible()]
            if len(visible) != 1:
                return
            window = startup.main_engine.rootObjects()[0]
            assert visible == [window]
            viewport = window.findChild(QQuickItem, "occt_viewport")
            assert viewport.property("render_ready") and not viewport.property("error_text")
            assert window.findChild(QQuickItem, "workspace_content").isEnabled()
            assert window.grabWindow().save(str(output / "startup-ready-preview.png"))
            assert not messages, messages
            print("SPLASH_CHECK_OK", json.dumps({"progress": progress, "visible_windows": len(visible),
                  "screen": launch_screen.name(), "screen_count": len(screens),
                  "cursor_crossed": state["cursor_crossed"], "transparent_first_frame": state["ready_hidden_checked"],
                  "main_faded_in": state["fade_checked"], "animated_targets": state["animated_targets"],
                  "full_progress_before_fade": state["full_progress_checked"]}), flush=True)
            timer.stop()
            application.quit()
        except Exception as error:
            state["error"] = repr(error)
            timer.stop()
            application.exit(2)

    timer = QTimer()
    timer.setInterval(30)
    timer.timeout.connect(advance)
    try:
        QCursor.setPos(launch_screen.availableGeometry().center())
        assert application.screenAt(QCursor.pos()) == launch_screen
        startup.start(stages())
        check_screen(startup._splash_window)
        timer.start()
        exit_code = application.exec()
    finally:
        timer.stop()
        startup.shutdown()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QCursor.setPos(original_cursor_position)
    assert state["error"] is None, state["error"]
    if failure:
        assert exit_code == 1 and state["exit_posted"]
        assert state["animated_targets"] == [35], state["animated_targets"]
        assert not messages, messages
        print("SPLASH_FAILURE_CHECK_OK", flush=True)
    else:
        assert exit_code == 0


if __name__ == "__main__":
    if any(mode in sys.argv for mode in ("--render-check", "--secondary-screen-check", "--failure-check")):
        startup_check("--failure-check" in sys.argv, secondary="--secondary-screen-check" in sys.argv)
    else:
        unittest.main()
