"""Real point cloud IO, immutable records, and staged document adoption."""

import builtins
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from PyQt6.QtCore import QCoreApplication, QUrl
from PyQt6.QtTest import QTest

from app.point_cloud.controllers.point_cloud_controller import PointCloudController
from app.point_cloud.models.point_cloud_io import read_point_cloud, validate_point_cloud_path
from app.point_cloud.views.open3d_renderer import PointCloudCamera


def write_cloud(path, count=3):
    header = ("ply\nformat ascii 1.0\nelement vertex " + str(count) + "\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    rows = ("0 0 0 255 0 0\n", "2 0 0 0 255 0\n", "0 3 4 0 0 255\n")
    path.write_text(header + "".join(rows[:count]), encoding="utf-8")
    return path


class PointCloudIoTests(unittest.TestCase):
    def test_missing_open3d_reports_installation_guidance_and_original_error(self):
        error = ModuleNotFoundError("No module named 'open3d'", name="open3d")
        original_import = builtins.__import__

        def import_without_open3d(name, *args, **kwargs):
            if name == "open3d":
                raise error
            return original_import(name, *args, **kwargs)

        with TemporaryDirectory() as directory:
            source = write_cloud(Path(directory) / "source.ply")
            with patch("builtins.__import__", side_effect=import_without_open3d):
                with self.assertRaises(RuntimeError) as raised:
                    read_point_cloud(source)
            self.assertIn("Open3D 未安装", str(raised.exception))
            self.assertIn("requirements.txt", str(raised.exception))
            self.assertIn(str(error), str(raised.exception))
            self.assertIs(raised.exception.__cause__, error)

    def test_broken_open3d_installation_preserves_specific_import_error(self):
        original_import = builtins.__import__
        failures = (
            (ModuleNotFoundError("No module named 'dash'", name="dash"), "Open3D 依赖缺失"),
            (ModuleNotFoundError("No module named 'open3d.pybind'", name="open3d.pybind"), "Open3D 依赖缺失"),
            (ImportError("DLL load failed while importing pybind: 找不到指定的程序。"), "Open3D 加载失败"),
        )
        with TemporaryDirectory() as directory:
            source = write_cloud(Path(directory) / "source.ply")
            for error, expected_message in failures:
                with self.subTest(error=str(error)):
                    def import_broken_open3d(name, *args, **kwargs):
                        if name == "open3d":
                            raise error
                        return original_import(name, *args, **kwargs)

                    with patch("builtins.__import__", side_effect=import_broken_open3d):
                        with self.assertRaises(RuntimeError) as raised:
                            read_point_cloud(source)
                    self.assertIn(expected_message, str(raised.exception))
                    self.assertIn(str(error), str(raised.exception))
                    self.assertNotIn("Open3D 未安装", str(raised.exception))
                    self.assertIs(raised.exception.__cause__, error)

    def test_colored_ply_preserves_coordinates_and_metadata(self):
        with TemporaryDirectory() as directory:
            source = write_cloud(Path(directory) / "彩色点云.PLY")
            record = read_point_cloud(source)
            self.assertEqual(record.name, "彩色点云")
            np.testing.assert_array_equal(record.points, [[0, 0, 0], [2, 0, 0], [0, 3, 4]])
            np.testing.assert_allclose(record.colors, np.eye(3))
            self.assertEqual(record.to_summary()["dimensions"], [2, 3, 4])
            self.assertTrue(record.to_summary()["has_colors"])
            self.assertEqual(record.to_summary()["removed_count"], 0)
            self.assertFalse(record.points.flags.writeable)
            self.assertFalse(record.colors.flags.writeable)

    def test_xyz_removes_nonfinite_points_and_accepts_flat_clouds(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.xyz"
            source.write_text("0 0 0\n1 2 0\nnan 1 0\ninf 0 0\n")
            record = read_point_cloud(source)
            self.assertEqual(len(record.points), 2)
            self.assertEqual(record.source_count, 4)
            self.assertEqual(record.to_summary()["removed_count"], 2)
            self.assertIsNone(record.colors)
            self.assertEqual(record.to_summary()["dimensions"], [1, 2, 0])

    def test_ascii_pcd_and_binary_ply_are_readable(self):
        import open3d as o3d

        with TemporaryDirectory() as directory:
            record = read_point_cloud(write_cloud(Path(directory) / "source.ply"))
            cloud = o3d.geometry.PointCloud()
            cloud.points = o3d.utility.Vector3dVector(record.points.copy())
            cloud.colors = o3d.utility.Vector3dVector(record.colors.astype(np.float64))
            for extension, ascii_format in (("pcd", True), ("ply", False)):
                with self.subTest(extension=extension):
                    path = Path(directory) / ("copy." + extension)
                    self.assertTrue(o3d.io.write_point_cloud(str(path), cloud, write_ascii=ascii_format))
                    restored = read_point_cloud(path)
                    np.testing.assert_allclose(restored.points, record.points)
                    np.testing.assert_allclose(restored.colors, record.colors)

    def test_empty_malformed_and_all_invalid_clouds_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in (("empty.xyz", ""), ("invalid.ply", "broken"),
                                  ("invalid.xyz", "nan 0 0\ninf 0 0\n")):
                with self.subTest(name=name):
                    path = root / name
                    path.write_text(payload)
                    with self.assertRaises(ValueError):
                        read_point_cloud(path)
            for source in (root / "missing.pcd", root / "source.txt", root / "folder.ply"):
                if source.name == "folder.ply":
                    source.mkdir()
                with self.assertRaises(ValueError):
                    validate_point_cloud_path(source)

    def test_camera_fit_handles_single_point_and_keeps_navigation_finite(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "single.xyz"
            source.write_text("1000000 2000000 3000000\n")
            camera = PointCloudCamera()
            camera.fit(read_point_cloud(source))
            camera.orbit(120, 900)
            camera.pan(20, -30, 400)
            camera.zoom(1200)
            eye, target, up = camera.snapshot()
            self.assertTrue(np.isfinite([eye, target, up]).all())
            self.assertGreater(np.linalg.norm(eye - target), 0)


class PointCloudControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def wait_until(self, predicate):
        deadline = time.monotonic() + 20
        while not predicate():
            self.assertLess(time.monotonic(), deadline, "Point cloud import timed out")
            QTest.qWait(10)

    def test_import_failure_logs_cause_and_interpreter_and_reports_error(self):
        controller = PointCloudController()
        original_popen = subprocess.Popen
        processes = []
        error_message = "DLL load failed while importing pybind: 动态链接库(DLL)初始化例程失败。"
        script = """
import builtins
import sys
from app.point_cloud.models.point_cloud_importer import main
original_import = builtins.__import__
def import_broken_open3d(name, *args, **kwargs):
    if name == 'open3d':
        raise ImportError('DLL load failed while importing pybind: 动态链接库(DLL)初始化例程失败。')
    return original_import(name, *args, **kwargs)
builtins.__import__ = import_broken_open3d
raise SystemExit(main(sys.argv[1:]))
"""

        def start_broken_reader(command, **options):
            process = original_popen([sys.executable, "-X", "utf8", "-u", "-c", script, *command[-2:]], **options)
            processes.append((process, Path(command[-1])))
            return process

        try:
            with TemporaryDirectory() as directory:
                source = write_cloud(Path(directory) / "source.ply")
                notices = []
                controller.notice_requested.connect(lambda message, failed: notices.append((message, failed)))
                with self.assertLogs("app.point_cloud.controllers.point_cloud_import_task", level="ERROR") as logs:
                    with patch("app.point_cloud.controllers.point_cloud_import_task.subprocess.Popen", side_effect=start_broken_reader):
                        self.assertTrue(controller.import_cloud(QUrl.fromLocalFile(str(source))))
                        self.wait_until(lambda: not controller.loading and controller._task is None)
                self.assertFalse(controller.has_cloud)
                self.assertIn("Open3D 加载失败", controller.last_error)
                self.assertIn(error_message, controller.last_error)
                self.assertEqual(notices, [(controller.last_error, True)])
                output = "\n".join(logs.output)
                self.assertIn(str(source.resolve()), output)
                self.assertIn(sys.executable, output)
                self.assertIn("Traceback (most recent call last)", output)
                self.assertIn("ImportError: " + error_message, output)
                self.assertIn("RuntimeError: " + controller.last_error, output)
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0][0].poll())
                self.assertFalse(processes[0][1].exists())
        finally:
            controller.stop()
            controller.deleteLater()

    def test_isolated_reader_preserves_rgb_and_filtered_cloud_metadata(self):
        controller = PointCloudController()
        try:
            with TemporaryDirectory() as directory:
                colored = write_cloud(Path(directory) / "彩色点云.PLY")
                filtered = Path(directory) / "filtered.xyz"
                filtered.write_text("0 0 0\n1 2 0\nnan 1 0\n")
                previews = []
                controller.preview_requested.connect(previews.append)
                for source in (colored, filtered):
                    with self.subTest(source=source.name):
                        count = len(previews)
                        self.assertTrue(controller.import_cloud(QUrl.fromLocalFile(str(source))))
                        self.wait_until(lambda: len(previews) > count and controller._task is None)
                        record = previews[-1]
                        self.assertEqual(record.name, source.stem)
                        self.assertEqual(record.source_path, str(source.resolve()))
                        self.assertFalse(record.points.flags.writeable)
                        self.assertFalse(record.bounds[0].flags.writeable)
                        self.assertFalse(record.bounds[1].flags.writeable)
                        if source == colored:
                            np.testing.assert_array_equal(record.points, [[0, 0, 0], [2, 0, 0], [0, 3, 4]])
                            np.testing.assert_allclose(record.colors, np.eye(3))
                            self.assertFalse(record.colors.flags.writeable)
                            self.assertEqual(record.source_count, 3)
                        else:
                            np.testing.assert_array_equal(record.points, [[0, 0, 0], [1, 2, 0]])
                            self.assertIsNone(record.colors)
                            self.assertEqual(record.to_summary()["removed_count"], 1)
                        controller.report_preview(record)
                        self.assertIs(controller.current_record, record)
        finally:
            controller.stop()
            controller.deleteLater()

    def test_native_reader_crash_preserves_document_and_cleans_temporary_files(self):
        controller = PointCloudController()
        original_popen = subprocess.Popen
        processes = []

        def start_crashing_reader(command, **options):
            process = original_popen([sys.executable, "-c", "import os; os._exit(17)"], **options)
            processes.append((process, Path(command[-1])))
            return process

        try:
            with TemporaryDirectory() as directory:
                source = write_cloud(Path(directory) / "source.ply")
                previews = []
                controller.preview_requested.connect(previews.append)
                self.assertTrue(controller.import_cloud(QUrl.fromLocalFile(str(source))))
                self.wait_until(lambda: previews and controller._task is None)
                controller.report_preview(previews[0])
                previous = controller.current_record
                with self.assertLogs("app.point_cloud.controllers.point_cloud_import_task", level="ERROR"):
                    with patch("app.point_cloud.controllers.point_cloud_import_task.subprocess.Popen", side_effect=start_crashing_reader):
                        self.assertTrue(controller.import_cloud(QUrl.fromLocalFile(str(source))))
                        self.wait_until(lambda: not controller.loading and controller._task is None)
                self.assertIn("异常退出", controller.last_error)
                self.assertIn("17", controller.last_error)
                self.assertIs(controller.current_record, previous)
                self.assertEqual(len(previews), 1)
                self.assertEqual(processes[0][0].poll(), 17)
                self.assertFalse(processes[0][1].exists())
        finally:
            controller.stop()
            controller.deleteLater()

    def test_stop_terminates_reader_and_cleans_temporary_files_without_notices(self):
        controller = PointCloudController()
        original_popen = subprocess.Popen
        processes = []
        script = "import sys, time; from pathlib import Path; Path(sys.argv[1]).touch(); time.sleep(60)"

        def start_slow_reader(command, **options):
            directory = Path(command[-1])
            process = original_popen([sys.executable, "-c", script, str(directory / "started")], **options)
            processes.append((process, directory))
            return process

        try:
            with TemporaryDirectory() as directory:
                source = write_cloud(Path(directory) / "source.ply")
                previews, notices = [], []
                controller.preview_requested.connect(previews.append)
                controller.notice_requested.connect(lambda message, failed: notices.append((message, failed)))
                with patch("app.point_cloud.controllers.point_cloud_import_task.subprocess.Popen", side_effect=start_slow_reader):
                    self.assertTrue(controller.import_cloud(QUrl.fromLocalFile(str(source))))
                    self.wait_until(lambda: processes and (processes[0][1] / "started").exists())
                    task = controller._task
                    started = time.monotonic()
                    controller.stop()
                    self.assertLess(time.monotonic() - started, 5)
                self.assertFalse(task.isRunning())
                self.assertIsNotNone(processes[0][0].poll())
                self.assertFalse(processes[0][1].exists())
                self.wait_until(lambda: controller._task is None)
                self.assertEqual(previews, [])
                self.assertEqual(notices, [])
                self.assertFalse(controller.has_cloud)
        finally:
            controller.stop()
            controller.deleteLater()

    def test_import_waits_for_preview_and_failure_preserves_previous_document(self):
        controller = PointCloudController()
        try:
            with TemporaryDirectory() as directory:
                source = write_cloud(Path(directory) / "source.ply")
                previews = []
                controller.preview_requested.connect(previews.append)
                self.assertTrue(controller.import_cloud(QUrl.fromLocalFile(str(source))))
                self.wait_until(lambda: len(previews) == 1 and controller._task is None)
                self.assertTrue(controller.loading)
                self.assertFalse(controller.has_cloud)
                controller.report_preview(previews[0])
                self.assertFalse(controller.loading)
                self.assertTrue(controller.has_cloud)
                previous = controller.current_record

                self.assertTrue(controller.import_cloud(QUrl.fromLocalFile(str(source))))
                self.wait_until(lambda: len(previews) == 2 and controller._task is None)
                self.assertIs(controller.current_record, previous)
                controller.report_preview(previews[1], "render failure")
                self.assertFalse(controller.loading)
                self.assertIs(controller.current_record, previous)
                controller.report_preview(previews[1])
                self.assertIs(controller.current_record, previous)
                self.assertEqual(controller.last_error, "render failure")

                malformed = Path(directory) / "broken.ply"
                malformed.write_text("invalid")
                self.assertTrue(controller.import_cloud(QUrl.fromLocalFile(str(malformed))))
                self.wait_until(lambda: not controller.loading and controller._task is None)
                self.assertIs(controller.current_record, previous)
                self.assertFalse(controller.import_cloud(QUrl("https://example.com/points.ply")))
                self.assertIs(controller.current_record, previous)
        finally:
            controller.stop()
            controller.deleteLater()


if __name__ == "__main__":
    unittest.main()
