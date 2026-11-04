"""Qt command adapter; geometric operations remain in CadModel."""

from datetime import datetime

from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot

from app.models.cad_model import CadModel


class CadController(QObject):
    state_changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = CadModel()
        self._status_text = "工作空间已就绪。"
        self._last_error = ""
        self._last_export_path = ""
        self._recent_actions: list[dict] = []
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
        return True

    def _failure(self, error: Exception) -> bool:
        self._last_error = str(error) or "操作失败，请重试。"
        self._status_text = self._last_error
        self.state_changed.emit()
        return False

    @pyqtSlot(float, float, float, result=bool)
    def create_box(self, length: float, width: float, height: float) -> bool:
        try:
            record = self._model.create_box(length, width, height)
            self._record_action("创建模型", record.name + " · " + record.to_summary()["dimensions_text"])
            return self._success(f"已创建 {record.name}，体积 {record.volume:,.3f} mm³。")
        except Exception as error:
            return self._failure(error)

    @pyqtSlot(str, result=bool)
    def select_model(self, model_id: str) -> bool:
        try:
            record = self._model.select_model(model_id)
            return self._success(f"当前模型：{record.name}。")
        except Exception as error:
            return self._failure(error)

    @pyqtSlot(QUrl, result=bool)
    def export_step(self, destination: QUrl) -> bool:
        try:
            if not destination.isLocalFile():
                raise ValueError("请选择本地文件保存位置。")
            path = self._model.export_step(destination.toLocalFile())
            self._last_export_path = str(path)
            self._record_action("导出 STEP", path.name)
            return self._success(f"已保存到 {path}。")
        except Exception as error:
            return self._failure(error)
