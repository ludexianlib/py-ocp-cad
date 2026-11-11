"""Qt controller for point cloud documents; no rendering implementation here."""

import math

from PyQt6.QtCore import QCoreApplication, QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot

from app.point_cloud.controllers.point_cloud_import_task import PointCloudImportTask
from app.point_cloud.models.point_cloud_io import validate_point_cloud_path
from app.point_cloud.models.point_cloud_model import PointCloudModel


class PointCloudController(QObject):
    state_changed = pyqtSignal()
    loading_changed = pyqtSignal()
    display_settings_changed = pyqtSignal()
    notice_requested = pyqtSignal(str, bool)
    preview_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = PointCloudModel()
        self._task = None
        self._pending_record = None
        self._loading = False
        self._stage_text = ""
        self._last_error = ""
        self._point_size = 3.0
        self._use_rgb = True
        self._stopped = False
        QCoreApplication.instance().aboutToQuit.connect(self.stop)

    @property
    def current_record(self):
        return self._model.active_record

    @pyqtProperty(bool, notify=state_changed)
    def has_cloud(self):
        return self.current_record is not None

    @pyqtProperty("QVariantMap", notify=state_changed)
    def active_cloud(self):
        return self.current_record.to_summary() if self.has_cloud else {}

    @pyqtProperty(bool, notify=loading_changed)
    def loading(self):
        return self._loading

    @pyqtProperty(str, notify=loading_changed)
    def stage_text(self):
        return self._stage_text

    @pyqtProperty(str, notify=state_changed)
    def last_error(self):
        return self._last_error

    @pyqtProperty(float, notify=display_settings_changed)
    def point_size(self):
        return self._point_size

    @point_size.setter
    def point_size(self, value):
        if math.isfinite(value) and 1 <= value <= 12 and value != self._point_size:
            self._point_size = value
            self.display_settings_changed.emit()

    @pyqtProperty(bool, notify=display_settings_changed)
    def use_rgb(self):
        return self._use_rgb

    @use_rgb.setter
    def use_rgb(self, value):
        if value != self._use_rgb:
            self._use_rgb = value
            self.display_settings_changed.emit()

    @pyqtSlot(QUrl, result=bool)
    def import_cloud(self, source):
        if self._loading or self._task is not None or self._stopped:
            return False
        try:
            if not source.isLocalFile():
                raise ValueError("请选择本地点云文件。")
            path = validate_point_cloud_path(source.toLocalFile())
        except Exception as error:
            self._fail(str(error))
            return False
        self._loading = True
        self._stage_text = "正在读取点云…"
        self._last_error = ""
        self.state_changed.emit()
        self.loading_changed.emit()
        task = PointCloudImportTask(path, self)
        self._task = task
        task.loaded.connect(self._loaded)
        task.failed.connect(self._fail)
        task.finished.connect(self._release_task)
        task.start()
        return True

    def _loaded(self, record):
        if self._stopped:
            return
        self._pending_record = record
        self._stage_text = "正在准备点云预览…"
        self.loading_changed.emit()
        self.preview_requested.emit(record)

    def report_preview(self, record, error_text=""):
        if self._stopped or record is not self._pending_record:
            return
        if error_text:
            self._fail(error_text)
            return
        self._model.adopt(record)
        self._pending_record = None
        self._loading = False
        self._last_error = ""
        self.state_changed.emit()
        self.loading_changed.emit()
        self.notice_requested.emit(f"已导入 {record.name}，共 {len(record.points):,} 个有效点。", False)

    def _fail(self, message):
        if self._stopped:
            return
        self._pending_record = None
        self._loading = False
        self._last_error = message or "点云导入失败。"
        self.state_changed.emit()
        self.loading_changed.emit()
        self.notice_requested.emit(self._last_error, True)

    def _release_task(self):
        task, self._task = self._task, None
        if task is not None:
            task.deleteLater()

    def stop(self):
        self._stopped = True
        if self._task is not None:
            self._task.requestInterruption()
            self._task.wait()
        self._pending_record = None
