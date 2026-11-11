"""Desktop startup check: python tests/test_splash_screen.py --render-check."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class SplashScreenTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("CAD_RUN_VIEWPORT_TESTS") == "1", "Requires a desktop GPU")
    def test_splash_waits_for_ready_frame_and_handles_failure(self):
        for mode, marker in (("--render-check", "SPLASH_CHECK_OK"), ("--failure-check", "SPLASH_FAILURE_CHECK_OK")):
            with self.subTest(mode=mode):
                completed = subprocess.run(
                    [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), mode],
                    cwd=Path(__file__).resolve().parents[1], capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=45,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn(marker, completed.stdout)


def startup_check(failure=False):
    import json
    import time

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, QTimer, Qt, qInstallMessageHandler
    from PyQt6.QtGui import QGuiApplication, QMouseEvent
    from PyQt6.QtQuick import QQuickItem
    from app.application.startup_controller import StartupController
    from main import _create_engine_steps, configure_fonts, configure_graphics

    configure_graphics()
    application = QGuiApplication([])
    configure_fonts(application)
    messages = []
    qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))
    output = project_root / "out"
    output.mkdir(exist_ok=True)
    startup = StartupController(application)
    startup.exit_requested.connect(application.exit)
    state = {"held": False, "waiting_checked": False, "snapshot": False, "dismissed": False,
             "error": None, "failure_checked": False, "exit_posted": False}
    progress = [0]
    startup.state_changed.connect(lambda: progress.append(startup.progress))
    startup.splash_dismissed.connect(lambda: state.update(dismissed=True))
    deadline = time.monotonic() + 25

    def stages():
        # No workspace dependency has been imported before the splash is visible.
        assert startup._splash_window.isVisible()
        assert startup._splash_window.property("opacity") > 0
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

    startup.start(stages())

    def advance():
        try:
            assert time.monotonic() < deadline, ("Startup timed out", progress, messages)
            if failure:
                if not startup.failed:
                    return
                assert not startup.ready and startup.progress < 100
                assert startup.error_text == "测试模块加载失败"
                splash = startup._splash_window
                assert splash.isVisible()
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
            print("SPLASH_CHECK_OK", json.dumps({"progress": progress, "visible_windows": len(visible)}), flush=True)
            timer.stop()
            application.quit()
        except Exception as error:
            state["error"] = repr(error)
            timer.stop()
            application.exit(2)

    timer = QTimer()
    timer.setInterval(30)
    timer.timeout.connect(advance)
    timer.start()
    try:
        exit_code = application.exec()
    finally:
        timer.stop()
        startup.shutdown()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert state["error"] is None, state["error"]
    if failure:
        assert exit_code == 1 and state["exit_posted"]
        assert not messages, messages
        print("SPLASH_FAILURE_CHECK_OK", flush=True)
    else:
        assert exit_code == 0


if __name__ == "__main__":
    if "--render-check" in sys.argv or "--failure-check" in sys.argv:
        startup_check("--failure-check" in sys.argv)
    else:
        unittest.main()
