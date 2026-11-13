"""Supervise an isolated reader without loading Open3D in the CAD process."""

import json
import logging
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from PyQt6.QtCore import QThread, pyqtSignal

from app.point_cloud.models.point_cloud_importer import load_prepared_cloud


class PointCloudImportTask(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, source, parent=None, *, unit):
        super().__init__(parent)
        self._source = source
        self._unit = unit

    def run(self):
        try:
            if self.isInterruptionRequested():
                return
            with TemporaryDirectory(prefix="point-cloud-") as directory:
                command = [sys.executable, "-X", "utf8", "-u", "-m",
                           "app.point_cloud.models.point_cloud_importer", "--unit", self._unit,
                           str(self._source), directory]
                with subprocess.Popen(
                    command, cwd=Path(__file__).resolve().parents[3],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                ) as process:
                    try:
                        while not self.isInterruptionRequested():
                            try:
                                output, error_output = process.communicate(timeout=0.1)
                                break
                            except subprocess.TimeoutExpired:
                                continue
                        else:
                            return
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.communicate()
                if self.isInterruptionRequested():
                    return
                if process.returncode:
                    logging.getLogger(__name__).error(
                        "Point cloud reader exited: code=%s source=%s executable=%s\n%s\n%s",
                        process.returncode, self._source, sys.executable, output, error_output,
                    )
                    error_path = Path(directory) / "error.json"
                    if error_path.is_file():
                        message = json.loads(error_path.read_text(encoding="utf-8"))["message"]
                    else:
                        message = f"点云读取进程异常退出（退出码 {process.returncode}），请查看运行日志。"
                    raise RuntimeError(message)
                record = load_prepared_cloud(directory)
                if not self.isInterruptionRequested():
                    self.loaded.emit(record)
        except Exception as error:
            if not self.isInterruptionRequested():
                logging.getLogger(__name__).exception(
                    "Point cloud import failed: source=%s executable=%s",
                    self._source, sys.executable,
                )
                self.failed.emit(str(error) or "点云读取失败。")
