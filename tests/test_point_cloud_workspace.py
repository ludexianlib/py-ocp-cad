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
    from unittest.mock import patch

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
    from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, QRect, QUrl, Qt, qInstallMessageHandler
    from PyQt6.QtGui import QGuiApplication, QMouseEvent, QWheelEvent
    from PyQt6.QtQuick import QQuickFramebufferObject, QQuickItem
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
    assert isinstance(viewport, QQuickFramebufferObject)
    cad_view = window.findChild(QQuickItem, "occt_viewport")
    loading_dialog = window.findChild(QObject, "file_loading_dialog")
    assert loading_dialog is not None
    assert len(window.findChildren(QObject, "file_loading_dialog")) == 1
    assert loading_dialog.property("modal")
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
    from app.point_cloud.views.point_cloud_renderer import PointCloudRenderer

    original_upload = PointCloudRenderer._upload_cloud
    original_release = PointCloudRenderer._release_resources
    uploads, uploaded_renderers, released_renderers = [], set(), set()

    def record_upload(renderer, record):
        original_upload(renderer, record)
        uploads.append(record)
        uploaded_renderers.add(id(renderer))

    def record_release(renderer):
        original_release(renderer)
        assert renderer._buffer is None and renderer._depth_buffer == 0
        released_renderers.add(id(renderer))

    upload_patch = patch.object(PointCloudRenderer, "_upload_cloud", new=record_upload)
    release_patch = patch.object(PointCloudRenderer, "_release_resources", new=record_release)
    upload_patch.start()
    release_patch.start()
    checks_passed = False

    def grab_cloud_frame():
        frame = window.grabWindow()
        position = viewport.mapToScene(QPointF(0, 0))
        scale_x, scale_y = frame.width() / window.width(), frame.height() / window.height()
        return frame.copy(QRect(round(position.x() * scale_x), round(position.y() * scale_y),
                                round(viewport.width() * scale_x), round(viewport.height() * scale_y)))

    try:
        wait_until(lambda: cad_view.property("render_ready"))
        mark("cad_ready")
        window.raise_()
        window.requestActivate()
        wait_until(window.isActive)
        # Let the sidebar's initial fade finish before sending desktop input.
        QTest.qWait(220)
        # Navigate through the sidebar, preserving the single main window.
        nav = find_item(window.contentItem(), "nav_point_cloud")
        assert nav is not None, messages
        nav_center = nav.mapToScene(QPointF(nav.width() / 2, nav.height() / 2))
        nav_position = QPoint(round(nav_center.x()), round(nav_center.y()))
        post_mouse(QEvent.Type.MouseButtonPress, nav_position, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        post_mouse(QEvent.Type.MouseButtonRelease, nav_position, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        wait_until(lambda: window.property("active_page") == "point_cloud")
        # Hold the first frame to verify the dialog covers both reading and preview.
        viewport.setProperty("active", False)
        assert cloud_controller.import_cloud(QUrl.fromLocalFile(str(source)))
        mark("import_started")
        wait_until(lambda: loading_dialog.property("opened"))
        assert loading_dialog.property("heading_text") == "正在加载点云"
        assert loading_dialog.property("filename") == source.name
        wait_until(lambda: cloud_controller._pending_record is not None and cloud_controller._task is None)
        assert cloud_controller.loading and loading_dialog.property("opened")
        assert loading_dialog.property("stage_text") == "正在准备点云预览…"
        wait_until(lambda: loading_dialog.property("elapsed_seconds") >= 1)
        cad_nav = find_item(window.contentItem(), "nav_workbench")
        cad_nav_center = cad_nav.mapToScene(QPointF(cad_nav.width() / 2, cad_nav.height() / 2))
        cad_nav_position = QPoint(round(cad_nav_center.x()), round(cad_nav_center.y()))
        post_mouse(QEvent.Type.MouseButtonPress, cad_nav_position, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        post_mouse(QEvent.Type.MouseButtonRelease, cad_nav_position, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        assert window.property("active_page") == "point_cloud", "Modal loading dialog must block navigation"
        assert loading_dialog.property("opened")
        assert window.grabWindow().save(str(output / "point-cloud-loading-preview.png"))
        window.setProperty("active_page", "cad")
        wait_until(lambda: not loading_dialog.property("visible"))
        assert not cloud_controller.has_cloud
        assert not viewport.render_ready and viewport._accepted_serial == -1
        assert uploads == [], "Hidden point clouds must not upload GPU data"
        assert cad_controller.active_shape is previous_cad
        window.setProperty("active_page", "point_cloud")
        mark("waiting_cloud_frame")
        assert loading_dialog.property("loading")
        wait_until(lambda: cloud_controller.has_cloud and not cloud_controller.loading and cloud_controller._task is None)
        wait_until(lambda: not loading_dialog.property("visible"))
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

        wait_for_frame(lambda: setattr(cloud_controller, "point_size", 1.0))
        small_points = grab_cloud_frame()
        wait_for_frame(lambda: setattr(cloud_controller, "point_size", 5.0))
        first_frame = grab_cloud_frame()
        center = QRect(first_frame.width() // 4, first_frame.height() // 4,
                       first_frame.width() // 2, first_frame.height() // 2)
        assert first_frame.copy(center) != small_points.copy(center), "Point size must change the GPU image"
        wait_for_frame(lambda: setattr(cloud_controller, "use_rgb", False))
        assert grab_cloud_frame() != first_frame
        wait_for_frame(lambda: setattr(cloud_controller, "use_rgb", True))
        assert grab_cloud_frame() == first_frame
        assert len(uploads) == 1, "Display settings must reuse the uploaded vertex buffer"
        mark("colors_checked")

        # Coincident projected points must show the near point even when the far
        # point is drawn last. Qt's default color FBO has no depth attachment.
        direction = viewport._camera.snapshot()[0]
        direction = direction / np.linalg.norm(direction) * 10
        depth_source = output / "depth-test-cloud.ply"
        depth_source.write_text(
            "ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" +
            " ".join(str(value) for value in direction) + " 0 255 0\n" +
            " ".join(str(value) for value in -direction) + " 255 0 0\n",
            encoding="utf-8",
        )
        assert cloud_controller.import_cloud(QUrl.fromLocalFile(str(depth_source)))
        wait_until(lambda: not cloud_controller.loading and cloud_controller._task is None)
        wait_until(lambda: not loading_dialog.property("visible"))
        depth_frame = grab_cloud_frame()
        pixel = depth_frame.pixelColor(depth_frame.width() // 2, depth_frame.height() // 2)
        assert pixel.green() > 200 and pixel.red() < 60, (pixel.getRgb(), cloud_controller.last_error)
        assert cloud_controller.import_cloud(QUrl.fromLocalFile(str(source)))
        wait_until(lambda: not cloud_controller.loading and cloud_controller._task is None)
        wait_until(lambda: not loading_dialog.property("visible"))
        assert cloud_controller.active_cloud["point_count"] == len(points)
        mark("depth_checked")

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
        assert len(uploads) == 3, "Camera navigation must reuse GPU point data"
        mark("mouse_checked")

        # Hiding retains the document/camera, and stops scheduling renderer work.
        cloud_record = cloud_controller.current_record
        snapshot = viewport._camera.snapshot()
        window.setProperty("active_page", "cad")
        QTest.qWait(300)
        wait_until(lambda: not viewport.property("active"))
        accepted_serial = viewport._accepted_serial
        viewport.fit_view()
        QTest.qWait(120)
        assert viewport._accepted_serial == accepted_serial
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

        # A failed GPU upload preserves the old document and its rendered data.
        before_failure = grab_cloud_frame()

        def fail_new_upload(renderer, record):
            if record is not cloud_record:
                raise RuntimeError("测试 GPU 上传失败")
            record_upload(renderer, record)

        with patch.object(PointCloudRenderer, "_upload_cloud", new=fail_new_upload):
            assert cloud_controller.import_cloud(QUrl.fromLocalFile(str(source)))
            wait_until(lambda: not cloud_controller.loading and cloud_controller._task is None)
            wait_until(lambda: viewport.render_ready and not loading_dialog.property("visible"))
        assert "测试 GPU 上传失败" in cloud_controller.last_error
        assert cloud_controller.current_record is cloud_record
        after_failure = grab_cloud_frame()
        before_failure.save(str(output / "cloud-before-gpu-failure.png"))
        after_failure.save(str(output / "cloud-after-gpu-failure.png"))
        # Exclude QML labels and notifications at the viewport edge; compare the
        # point-cloud area at the center to verify the GPU data was restored.
        center = QRect(before_failure.width() // 4, before_failure.height() // 4,
                       before_failure.width() // 2, before_failure.height() // 2)
        assert after_failure.copy(center) == before_failure.copy(center)
        mark("gpu_failure_restored")

        # Reading an invalid file must preserve the displayed point cloud.
        bad = output / "invalid-cloud.ply"
        bad.write_text("invalid")
        assert cloud_controller.import_cloud(QUrl.fromLocalFile(str(bad)))
        assert loading_dialog.property("loading") and loading_dialog.property("visible")
        wait_until(lambda: not cloud_controller.loading and cloud_controller._task is None)
        wait_until(lambda: not loading_dialog.property("visible"))
        assert cloud_controller.current_record is cloud_record
        assert cad_controller.active_shape is previous_cad

        # The same popup handles a real STEP import and stays open until its frame is ready.
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

        step_source = output / "loading-dialog-test.step"
        writer = STEPControl_Writer()
        assert writer.Transfer(BRepPrimAPI_MakeBox(10, 15, 20).Shape(), STEPControl_AsIs) == IFSelect_RetDone
        assert writer.Write(str(step_source)) == IFSelect_RetDone
        window.setProperty("active_page", "cad")
        displayed = []
        with patch.object(cad_controller, "report_model_displayed", side_effect=lambda shape, error: displayed.append((shape, error))):
            assert cad_controller.import_step(QUrl.fromLocalFile(str(step_source)))
            wait_until(lambda: loading_dialog.property("opened") and displayed)
            assert loading_dialog.property("heading_text") == "正在加载模型"
            assert loading_dialog.property("filename") == step_source.name
            assert loading_dialog.property("stage_text") == "正在显示模型…"
            assert loading_dialog.property("elapsed_seconds") == cad_controller.loading_elapsed_seconds
            assert len(window.findChildren(QObject, "file_loading_dialog")) == 1
            assert window.findChild(QObject, "file_loading_dialog") is loading_dialog
            assert window.grabWindow().save(str(output / "cad-loading-preview.png"))
        cad_controller.report_model_displayed(*displayed[-1])
        wait_until(lambda: not cad_controller.loading and not loading_dialog.property("visible"))
        assert not cad_controller.last_error
        assert cloud_controller.current_record is cloud_record
        mark("shared_loading_dialog_checked")
        assert not messages, messages
        mark("checks_passed")
        checks_passed = True
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
        upload_patch.stop()
        release_patch.stop()
        if checks_passed:
            assert uploaded_renderers <= released_renderers, "GPU resources must be released with the scene graph"
        faulthandler.cancel_dump_traceback_later()
        stack_log.close()


if __name__ == "__main__":
    if "--render-check" in sys.argv:
        render_check()
    else:
        unittest.main()
