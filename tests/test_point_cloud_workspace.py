"""Desktop check: python tests/test_point_cloud_workspace.py --render-check."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class PointCloudWorkspaceTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("CAD_RUN_VIEWPORT_TESTS") == "1", "Requires a desktop GPU")
    def test_shared_window_and_independent_renderers(self):
        try:
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), "--render-check"],
                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=90,
            )
        except subprocess.TimeoutExpired as error:
            self.fail(f"Desktop check timed out: {error.output!r}\n{error.stderr!r}")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("POINT_CLOUD_CHECK_OK", completed.stdout)


def render_check():
    import faulthandler
    import json
    import time

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    output = project_root / "out"
    output.mkdir(exist_ok=True)
    stack_log = (output / "point-cloud-check-stacks.log").open("w")
    faulthandler.dump_traceback_later(40, repeat=True, file=stack_log)

    def mark(stage):
        with (output / "point-cloud-check.log").open("a", encoding="utf-8") as log:
            log.write(stage + "\n")

    (output / "point-cloud-check.log").write_text("")
    mark("create_engine")
    import numpy as np
    from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QUrl, Qt, qInstallMessageHandler
    from PyQt6.QtGui import QGuiApplication, QMouseEvent, QWheelEvent
    from PyQt6.QtQuick import QQuickItem
    from PyQt6.QtTest import QTest
    from main import configure_graphics, create_engine

    configure_graphics()
    application = QGuiApplication([])
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    engine, cad_controller = create_engine(application)
    assert "open3d" not in sys.modules, "CAD process must not load Open3D"
    mark("engine_created")
    assert engine.rootObjects(), messages
    window = engine.rootObjects()[0]
    cloud_controller = window.property("cloud_controller")
    viewport = window.findChild(QQuickItem, "point_cloud_viewport")
    cad_view = window.findChild(QQuickItem, "occt_viewport")
    previous_cad = cad_controller.active_shape
    output = project_root / "out"
    output.mkdir(exist_ok=True)

    def wait_until(predicate, timeout=45):
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, ("Preview timeout", messages, cloud_controller.last_error)
            QTest.qWait(20)

    def find_item(parent, name):
        if parent.objectName() == name:
            return parent
        for child in parent.childItems():
            result = find_item(child, name)
            if result is not None:
                return result
        return None

    def post_mouse(event_type, position, button, buttons):
        # Synchronous QTest mouse delivery can hold the GIL while Qt Quick waits
        # for Python render callbacks. Posting uses the normal event-loop route.
        event = QMouseEvent(event_type, QPointF(position), QPointF(window.mapToGlobal(position)),
                            button, buttons, Qt.KeyboardModifier.NoModifier)
        QCoreApplication.postEvent(window, event)
        QTest.qWait(30)

    # A colored torus demonstrates the true point-cloud renderer without CAD geometry.
    angle, ring = np.meshgrid(np.linspace(0, 2 * np.pi, 240), np.linspace(0, 2 * np.pi, 70))
    x = (30 + 10 * np.cos(ring)) * np.cos(angle)
    y = (30 + 10 * np.cos(ring)) * np.sin(angle)
    z = 10 * np.sin(ring)
    points = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    colors = np.column_stack(((np.cos(angle).ravel() + 1) * 127.5,
                              (np.sin(angle).ravel() + 1) * 127.5,
                              (np.sin(ring).ravel() + 1) * 127.5)).astype(int)
    source = output / "sample-point-cloud.ply"
    source.write_text(
        f"ply\nformat ascii 1.0\nelement vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" +
        "\n".join(f"{p[0]} {p[1]} {p[2]} {c[0]} {c[1]} {c[2]}" for p, c in zip(points, colors)) + "\n",
        encoding="utf-8",
    )
    try:
        wait_until(lambda: cad_view.property("render_ready"))
        mark("cad_ready")
        window.raise_()
        window.requestActivate()
        # Navigate through the sidebar, preserving the single main window.
        nav = find_item(window.contentItem(), "nav_point_cloud")
        assert nav is not None, messages
        nav_center = nav.mapToScene(QPointF(nav.width() / 2, nav.height() / 2))
        nav_position = QPoint(round(nav_center.x()), round(nav_center.y()))
        post_mouse(QEvent.Type.MouseButtonPress, nav_position, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        post_mouse(QEvent.Type.MouseButtonRelease, nav_position, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        wait_until(lambda: window.property("active_page") == "point_cloud")
        assert cloud_controller.import_cloud(QUrl.fromLocalFile(str(source)))
        mark("import_started")
        window.setProperty("active_page", "cad")
        wait_until(lambda: cloud_controller._pending_record is not None and cloud_controller._task is None)
        assert not cloud_controller.has_cloud
        assert viewport._worker is None
        assert cad_controller.active_shape is previous_cad
        window.setProperty("active_page", "point_cloud")
        mark("waiting_cloud_frame")
        wait_until(lambda: cloud_controller.has_cloud and not cloud_controller.loading and cloud_controller._task is None)
        assert viewport.property("render_ready") and not viewport.property("error_text"), messages
        assert len(application.topLevelWindows()) == 1
        assert cloud_controller.active_cloud["point_count"] == len(points)
        assert cad_controller.active_shape is previous_cad
        mark("cloud_ready")
        assert "open3d" not in sys.modules, "Point cloud reading must stay in the isolated process"

        def wait_for_frame(action):
            before = viewport._accepted_serial
            action()
            wait_until(lambda: viewport._accepted_serial > before)

        wait_for_frame(lambda: setattr(cloud_controller, "point_size", 5.0))
        first_frame = viewport._image.copy()
        wait_for_frame(lambda: setattr(cloud_controller, "use_rgb", False))
        assert viewport._image != first_frame
        wait_for_frame(lambda: setattr(cloud_controller, "use_rgb", True))
        mark("colors_checked")
        # The rendering process may be restarted without losing the document.
        old_process_id = viewport._worker._process.pid
        viewport._worker._process.terminate()
        viewport._worker._process.join(3)
        wait_for_frame(viewport.fit_view)
        assert viewport._worker._process.pid != old_process_id
        mark("process_restarted")

        # Exercise real mouse input, then restore the fitted camera for the screenshot.
        start = viewport.mapToScene(QPointF(viewport.width() / 2, viewport.height() / 2))
        start = QPoint(round(start.x()), round(start.y()))
        yaw = viewport._camera.yaw
        post_mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        post_mouse(QEvent.Type.MouseMove, start + QPoint(55, 15), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
        post_mouse(QEvent.Type.MouseButtonRelease, start + QPoint(55, 15), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        assert viewport._camera.yaw != yaw
        center = viewport._camera.center.copy()
        post_mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.RightButton, Qt.MouseButton.RightButton)
        post_mouse(QEvent.Type.MouseMove, start + QPoint(25, 20), Qt.MouseButton.NoButton, Qt.MouseButton.RightButton)
        post_mouse(QEvent.Type.MouseButtonRelease, start + QPoint(25, 20), Qt.MouseButton.RightButton, Qt.MouseButton.NoButton)
        assert not np.array_equal(viewport._camera.center, center)
        distance = viewport._camera.distance
        wheel = QWheelEvent(QPointF(start), QPointF(start), QPoint(), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QCoreApplication.postEvent(window, wheel)
        QTest.qWait(30)
        assert viewport._camera.distance < distance
        wait_for_frame(viewport.reset_camera)
        mark("mouse_checked")

        # Hiding retains the document/camera, and stops scheduling renderer work.
        cloud_record = cloud_controller.current_record
        snapshot = viewport._camera.snapshot()
        window.setProperty("active_page", "cad")
        QTest.qWait(300)
        wait_until(lambda: not viewport.property("active"))
        assert not viewport._render_timer.isActive()
        assert not viewport._worker._active
        assert not cad_view.property("error_text")
        assert window.grabWindow().save(str(output / "cad-module-preview.png"))
        window.setProperty("active_page", "point_cloud")
        wait_for_frame(viewport.fit_view)
        mark("pages_switched")
        assert cloud_controller.current_record is cloud_record
        np.testing.assert_allclose(viewport._camera.snapshot(), snapshot)
        window.setWidth(window.width() - 100)
        wait_for_frame(viewport.fit_view)
        window.setWidth(1360)
        wait_for_frame(viewport.fit_view)
        mark("resized")
        QTest.qWait(300)
        assert window.grabWindow().save(str(output / "point-cloud-preview.png"))
        toolbar = window.findChild(QQuickItem, "cloud_toolbar")
        import_button = window.findChild(QQuickItem, "cloud_import_button")
        assert toolbar.width() > 700
        assert import_button.x() > toolbar.width() - import_button.width() - 2

        # Reading an invalid file must preserve the displayed point cloud.
        bad = output / "invalid-cloud.ply"
        bad.write_text("invalid")
        assert cloud_controller.import_cloud(QUrl.fromLocalFile(str(bad)))
        wait_until(lambda: not cloud_controller.loading and cloud_controller._task is None)
        assert cloud_controller.current_record is cloud_record
        assert cad_controller.active_shape is previous_cad
        assert not messages, messages
        mark("checks_passed")
        print("POINT_CLOUD_CHECK_OK", json.dumps({"points": len(points), "windows": len(application.topLevelWindows()),
              "qt_messages": messages}), flush=True)
    finally:
        mark("stopping")
        if messages:
            print("QT_MESSAGES", json.dumps(messages, ensure_ascii=False), flush=True)
        cloud_controller.stop()
        viewport.stop()
        mark("viewport_stopped")
        window.close()
        engine.deleteLater()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        mark("engine_destroyed")
        faulthandler.cancel_dump_traceback_later()
        stack_log.close()


if __name__ == "__main__":
    if "--render-check" in sys.argv:
        render_check()
    else:
        unittest.main()
