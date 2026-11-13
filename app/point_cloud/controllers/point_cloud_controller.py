"""Qt controller for point cloud documents; no rendering implementation here."""

import math

from PyQt6.QtCore import QCoreApplication, QElapsedTimer, QObject, QTimer, Qt, QUrl, pyqtProperty, pyqtSignal, pyqtSlot

from app.point_cloud.controllers.point_cloud_import_task import PointCloudImportTask
from app.point_cloud.models.point_cloud_io import validate_point_cloud_path
from app.point_cloud.models.point_cloud_model import PointCloudModel
from app.point_cloud.models.point_cloud_frame import PointCloudFrame, unit_scale
from app.point_cloud.services.point_cloud_stream import PointCloudStream


class PointCloudController(QObject):
    state_changed = pyqtSignal()
    loading_changed = pyqtSignal()
    display_settings_changed = pyqtSignal()
    notice_requested = pyqtSignal(str, bool)
    preview_requested = pyqtSignal(object)
    stream_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = PointCloudModel()
        self._task = None
        self._pending_record = None
        self._loading = False
        self._loading_filename = ""
        self._loading_elapsed_seconds = 0
        self._loading_clock = QElapsedTimer()
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(1000)
        self._loading_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._loading_timer.timeout.connect(self._update_loading_elapsed)
        self._stage_text = ""
        self._last_error = ""
        self._point_size = 3.0
        self._use_rgb = True
        self._color_mode = "rgb"
        self._stream = PointCloudStream()
        self._stream_running = False
        self._stream_session = None
        self._stream_generation = 0
        self._stream_status = self._stream.snapshot()
        self._stream_timer = QTimer(self)
        self._stream_timer.setInterval(33)
        self._stream_timer.timeout.connect(self._poll_stream)
        self._stopped = False
        QCoreApplication.instance().aboutToQuit.connect(self.stop)

    @property
    def current_record(self):
        return self._model.active_record

    @pyqtProperty(bool, notify=state_changed)
    def has_cloud(self):
        return self.current_record is not None and len(self.current_record.points) > 0

    @pyqtProperty("QVariantMap", notify=state_changed)
    def active_cloud(self):
        return self.current_record.to_summary() if self.current_record is not None else {}

    @pyqtProperty(bool, notify=stream_changed)
    def stream_running(self):
        return self._stream_running

    @pyqtProperty("QVariantMap", notify=stream_changed)
    def stream_status(self):
        return self._stream_status

    @property
    def stream_session(self):
        return self._stream_session

    @pyqtProperty(str, notify=display_settings_changed)
    def color_mode(self):
        return self._color_mode

    @color_mode.setter
    def color_mode(self, value):
        if value in ("uniform", "rgb", "height", "intensity") and value != self._color_mode:
            self._color_mode = value
            self._use_rgb = value == "rgb"
            self.display_settings_changed.emit()

    @pyqtProperty(bool, notify=loading_changed)
    def loading(self):
        return self._loading

    @pyqtProperty(str, notify=loading_changed)
    def loading_filename(self):
        return self._loading_filename

    @pyqtProperty(int, notify=loading_changed)
    def loading_elapsed_seconds(self):
        return self._loading_elapsed_seconds

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
        self.color_mode = "rgb" if value else "uniform"

    @pyqtSlot(str, int, result=bool)
    def start_stream(self, host, port):
        if self._stopped or self._loading or self._task is not None or self._stream_running:
            return False
        try:
            self._stream.start(host, port)
        except (ValueError, OSError, RuntimeError) as error:
            self._last_error = str(error)
            self.state_changed.emit()
            self.notice_requested.emit(self._last_error, True)
            return False
        self._stream_running = True
        self._stream_generation += 1
        self._stream_session = None
        self._last_error = ""
        self._stream_status = self._stream.snapshot()
        self._stream_timer.start()
        self.stream_changed.emit()
        self.state_changed.emit()
        return True

    @pyqtSlot()
    def stop_stream(self):
        self._stream_timer.stop()
        self._stream.stop()
        self._stream_running = False
        self._stream_status = self._stream.snapshot()
        self.stream_changed.emit()

    def _poll_stream(self):
        status = self._stream.snapshot()
        if status != self._stream_status:
            self._stream_status = status
            self.stream_changed.emit()
        if status["state"] == "failed":
            self._last_error = status["error"]
            self.stop_stream()
            self.state_changed.emit()
            self.notice_requested.emit(self._last_error, True)
            return
        # Wait for the outstanding preview to be acknowledged. The receiver
        # keeps just one newer frame while a hidden page or GPU is unavailable.
        if self._pending_record is not None:
            return
        latest = self._stream.take_latest()
        if latest is not None:
            session, frame = latest
            self._stream_session = (self._stream_generation, session)
            self._pending_record = frame
            self.preview_requested.emit(frame)

    @pyqtSlot(QUrl, str, result=bool)
    def import_cloud(self, source, unit):
        if self._loading or self._task is not None or self._stopped or self._stream_running:
            return False
        try:
            unit_scale(unit)
            if not source.isLocalFile():
                raise ValueError("请选择本地点云文件。")
            path = validate_point_cloud_path(source.toLocalFile())
        except Exception as error:
            self._fail(str(error))
            return False
        self._loading = True
        self._loading_filename = path.name
        self._loading_elapsed_seconds = 0
        self._loading_clock.start()
        self._loading_timer.start()
        self._stage_text = "正在读取点云…"
        self._last_error = ""
        self.state_changed.emit()
        self.loading_changed.emit()
        task = PointCloudImportTask(path, self, unit=unit)
        self._task = task
        task.loaded.connect(self._loaded)
        task.failed.connect(self._fail)
        task.finished.connect(self._release_task)
        task.start()
        return True

    def _update_loading_elapsed(self):
        if self._loading:
            self._loading_elapsed_seconds = self._loading_clock.elapsed() // 1000
            self.loading_changed.emit()

    def _finish_loading(self):
        if self._loading:
            self._loading_elapsed_seconds = self._loading_clock.elapsed() // 1000
        self._loading_timer.stop()
        self._loading = False

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
        self._finish_loading()
        self._last_error = ""
        self.state_changed.emit()
        if isinstance(record, PointCloudFrame):
            return
        self.loading_changed.emit()
        self.notice_requested.emit(f"已导入 {record.name}，共 {len(record.points):,} 个有效点。", False)

    def _fail(self, message):
        if self._stopped:
            return
        self._pending_record = None
        self._finish_loading()
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
        was_loading = self._loading
        self._finish_loading()
        if was_loading:
            self.loading_changed.emit()
        if self._task is not None:
            self._task.requestInterruption()
            self._task.wait()
        self.stop_stream()
        self._pending_record = None
