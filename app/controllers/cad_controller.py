"""Qt command adapter; geometric operations remain in CadModel."""

from datetime import datetime

from PyQt6.QtCore import QElapsedTimer, QObject, QTimer, Qt, QUrl, pyqtProperty, pyqtSignal, pyqtSlot

from app.controllers.step_import_task import StepImportTask
from app.models.cad_model import CadModel
from app.models.step_importer import validate_step_path


class CadController(QObject):
    state_changed = pyqtSignal()
    loading_changed = pyqtSignal()
    notice_requested = pyqtSignal(str, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = CadModel()
        self._status_text = "工作空间已就绪。"
        self._last_error = ""
        self._last_export_path = ""
        self._recent_actions: list[dict] = []
        self._loading = False
        self._loading_filename = ""
        self._loading_stage = ""
        self._loading_elapsed_seconds = 0
        self._loading_clock = QElapsedTimer()
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(1000)
        self._loading_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._loading_timer.timeout.connect(self._update_loading_elapsed)
        self._import_tasks = set()
        self._pending_import = None
        self.create_box(40, 30, 10)

    @pyqtProperty(int, notify=state_changed)
    def model_count(self) -> int:
        return len(self._model.records)

    @pyqtProperty(bool, notify=state_changed)
    def has_model(self) -> bool:
        return self._model.active_record is not None

    @pyqtProperty("QVariantMap", notify=state_changed)
    def active_model(self) -> dict:
        record = self._model.active_record
        return record.to_summary() if record else {}

    @property
    def active_shape(self):
        """Native shape for Python view adapters; QML keeps using the summary."""
        record = self._model.active_record
        return record.shape if record else None

    @property
    def active_display_shape(self):
        record = self._model.active_record
        return record.display_shape if record else None

    @pyqtProperty(bool, notify=loading_changed)
    def loading(self):
        return self._loading

    @pyqtProperty(str, notify=loading_changed)
    def loading_filename(self):
        return self._loading_filename

    @pyqtProperty(str, notify=loading_changed)
    def loading_stage(self):
        return self._loading_stage

    @pyqtProperty(int, notify=loading_changed)
    def loading_elapsed_seconds(self):
        return self._loading_elapsed_seconds

    @pyqtProperty("QVariantList", notify=state_changed)
    def models(self) -> list[dict]:
        return [record.to_summary() for record in self._model.records]

    @pyqtProperty("QVariantList", notify=state_changed)
    def recent_actions(self) -> list[dict]:
        return self._recent_actions[:5]

    @pyqtProperty(str, notify=state_changed)
    def status_text(self) -> str:
        return self._status_text

    @pyqtProperty(str, notify=state_changed)
    def last_error(self) -> str:
        return self._last_error

    @pyqtProperty(str, notify=state_changed)
    def last_export_path(self) -> str:
        return self._last_export_path

    def _record_action(self, title: str, detail: str) -> None:
        self._recent_actions.insert(0, {
            "title": title,
            "detail": detail,
            "time": datetime.now().strftime("%H:%M"),
        })
        del self._recent_actions[10:]

    def _success(self, message: str) -> bool:
        self._last_error = ""
        self._status_text = message
        self.state_changed.emit()
        self.notice_requested.emit(message, False)
        return True

    def _failure(self, error: Exception) -> bool:
        self._last_error = str(error) or "操作失败，请重试。"
        self._status_text = self._last_error
        self.state_changed.emit()
        self.notice_requested.emit(self._last_error, True)
        return False

    @pyqtSlot(float, float, float, result=bool)
    def create_box(self, length: float, width: float, height: float) -> bool:
        if self._loading:
            return self._failure(ValueError("请等待当前模型加载完成。"))
        try:
            record = self._model.create_box(length, width, height)
            self._record_action("创建模型", record.name + " · " + record.to_summary()["dimensions_text"])
            return self._success(f"已创建 {record.name}，体积 {record.volume:,.3f} mm³。")
        except Exception as error:
            return self._failure(error)

    @pyqtSlot(str, result=bool)
    def select_model(self, model_id: str) -> bool:
        if self._loading:
            return self._failure(ValueError("请等待当前模型加载完成。"))
        try:
            record = self._model.select_model(model_id)
            return self._success(f"当前模型：{record.name}。")
        except Exception as error:
            return self._failure(error)

    @pyqtSlot(QUrl, result=bool)
    def export_step(self, destination: QUrl) -> bool:
        if self._loading:
            return self._failure(ValueError("请等待当前模型加载完成。"))
        try:
            if not destination.isLocalFile():
                raise ValueError("请选择本地文件保存位置。")
            path = self._model.export_step(destination.toLocalFile())
            self._last_export_path = str(path)
            self._record_action("导出 STEP", path.name)
            return self._success(f"已保存到 {path}。")
        except Exception as error:
            return self._failure(error)

    @pyqtSlot(QUrl, result=bool)
    def import_step(self, source: QUrl) -> bool:
        if self._loading:
            return False
        try:
            if not source.isLocalFile():
                raise ValueError("请选择本地 STEP 文件。")
            path = validate_step_path(source.toLocalFile())
            task = StepImportTask(self)
        except Exception as error:
            return self._failure(error)

        previous_record = self._model.active_record
        state = {"task": task, "previous_id": previous_record.model_id if previous_record else "",
                 "model_id": "", "statistics": None}
        self._pending_import = state
        self._loading = True
        self._loading_filename = path.name
        self._loading_stage = "正在读取文件…"
        self._loading_elapsed_seconds = 0
        self._loading_clock.start()
        self._loading_timer.start()
        self.loading_changed.emit()
        self._import_tasks.add(task)
        task.phase_changed.connect(lambda text: self._set_import_stage(state, text))
        task.prepared.connect(lambda result: self._accept_import(state, result))
        task.statistics_ready.connect(lambda statistics: self._accept_statistics(state, statistics))
        task.failed.connect(lambda message: self._import_failed(state, message))
        task.finished.connect(lambda: self._release_import_task(task))
        task.start(path)
        return True

    def _update_loading_elapsed(self):
        self._loading_elapsed_seconds = self._loading_clock.elapsed() // 1000
        self.loading_changed.emit()

    def _set_import_stage(self, state, text):
        if self._pending_import is state:
            self._loading_stage = text
            self.loading_changed.emit()

    def _accept_import(self, state, result):
        if self._pending_import is not state:
            return
        try:
            record = self._model.add_imported_model(result)
            state["model_id"] = record.model_id
            if state["statistics"] is not None:
                self._model.update_statistics(record.model_id, state["statistics"])
            self._loading_stage = "正在显示模型…"
            self.loading_changed.emit()
            self.state_changed.emit()
        except Exception as error:
            self._import_failed(state, str(error))

    def _accept_statistics(self, state, statistics):
        if state.get("discarded"):
            return
        state["statistics"] = statistics
        if state["model_id"]:
            self._model.update_statistics(state["model_id"], statistics)
            self.state_changed.emit()

    def _finish_loading(self):
        self._loading_elapsed_seconds = self._loading_clock.elapsed() // 1000
        self._loading_timer.stop()
        self._loading = False
        self._pending_import = None
        self.loading_changed.emit()

    def report_model_displayed(self, shape, error_text):
        state = self._pending_import
        if state is None or not state["model_id"] or self.active_shape is not shape:
            return
        if error_text:
            self._import_failed(state, error_text)
            return
        name = self._model.active_record.name
        self._finish_loading()
        self._record_action("导入 STEP", name)
        self._success(f"已导入 {name}。")

    def _import_failed(self, state, message):
        if self._pending_import is not state:
            return
        state["discarded"] = True
        if state["model_id"]:
            self._model.remove_model(state["model_id"], state["previous_id"])
        self._finish_loading()
        self._failure(RuntimeError(message))

    def _release_import_task(self, task):
        self._import_tasks.discard(task)
        task.deleteLater()
