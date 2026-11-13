"""QML input adapter for a point cloud drawn directly into a Qt OpenGL FBO."""

import copy

from PyQt6.QtCore import QCoreApplication, QObject, Qt, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtQuick import QQuickFramebufferObject

from app.point_cloud.views.point_cloud_camera import PointCloudCamera
from app.point_cloud.views.point_cloud_renderer import PointCloudRenderer
from app.point_cloud.models.point_cloud_frame import PointCloudFrame


class PointCloudViewport(QQuickFramebufferObject):
    controller_changed = pyqtSignal()
    active_changed = pyqtSignal()
    render_state_changed = pyqtSignal()
    _frame_result = pyqtSignal(int, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controller = None
        self._active = False
        self._record = None
        self._camera = PointCloudCamera()
        self._stream_session = None
        self._stream_has_points = False
        self._rollback_camera = None
        self._rollback_stream_state = (None, False)
        self._render_ready = False
        self._error_text = ""
        self._serial = 0
        self._accepted_serial = -1
        self._position = None
        self._drag_button = Qt.MouseButton.NoButton
        self._stopped = False
        self._frame_result.connect(self._accept_frame, Qt.ConnectionType.QueuedConnection)
        self.widthChanged.connect(self._schedule_frame)
        self.heightChanged.connect(self._schedule_frame)
        self.setMirrorVertically(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton)
        QCoreApplication.instance().aboutToQuit.connect(self.stop)

    @pyqtProperty(QObject, notify=controller_changed)
    def controller(self):
        return self._controller

    @controller.setter
    def controller(self, value):
        if value is self._controller:
            return
        if self._controller is not None:
            self._controller.preview_requested.disconnect(self._preview)
            self._controller.display_settings_changed.disconnect(self._schedule_frame)
        self._controller = value
        if value is not None:
            value.preview_requested.connect(self._preview)
            value.display_settings_changed.connect(self._schedule_frame)
            if value.current_record is not None:
                self._preview(value.current_record)
        self.controller_changed.emit()

    @pyqtProperty(bool, notify=active_changed)
    def active(self):
        return self._active

    @active.setter
    def active(self, value):
        if value != self._active:
            self._active = value
            if value:
                self._schedule_frame()
            self.update()
            self.active_changed.emit()

    @pyqtProperty(str, notify=render_state_changed)
    def error_text(self):
        return self._error_text

    @pyqtProperty(bool, notify=render_state_changed)
    def render_ready(self):
        return self._render_ready

    def _preview(self, record):
        self._rollback_camera = copy.deepcopy(self._camera)
        self._rollback_stream_state = (self._stream_session, self._stream_has_points)
        self._record = record
        if isinstance(record, PointCloudFrame):
            session = self._controller.stream_session
            if session != self._stream_session:
                self._stream_session = session
                self._stream_has_points = False
            if len(record.points) and not self._stream_has_points:
                self._camera.fit(record)
                self._stream_has_points = True
            else:
                self._camera.update_bounds(record)
        else:
            self._stream_session = None
            self._stream_has_points = False
            self._camera.fit(record)
        self._render_ready = False
        self._error_text = ""
        self.render_state_changed.emit()
        self._schedule_frame()

    def _schedule_frame(self):
        if self._active and self._record is not None and not self._stopped:
            self._serial += 1
            self.update()

    def createRenderer(self):  # Qt virtual method name.
        return PointCloudRenderer(self._frame_result.emit)

    @pyqtSlot(int, object, str)
    def _accept_frame(self, serial, record, error_text):
        if self._stopped or record is not self._record or serial < self._accepted_serial:
            return
        if error_text:
            if serial != self._serial:
                return
            self._error_text = error_text
            self._render_ready = False
            self._controller.report_preview(record, error_text)
            previous_record = self._controller.current_record
            self._record = previous_record
            if previous_record is not record and self._rollback_camera is not None:
                self._camera = self._rollback_camera
                self._stream_session, self._stream_has_points = self._rollback_stream_state
            if previous_record is not None and previous_record is not record:
                if isinstance(previous_record, PointCloudFrame):
                    self._camera.update_bounds(previous_record)
                self._schedule_frame()
            elif previous_record is None:
                self.update()
            self.render_state_changed.emit()
            return
        if serial <= self._accepted_serial:
            return
        self._accepted_serial = serial
        self._render_ready = record is not None
        self._error_text = ""
        self.render_state_changed.emit()
        self._controller.report_preview(record)

    @pyqtSlot()
    def fit_view(self):
        if self._record is not None:
            origin = self._camera.origin if isinstance(self._record, PointCloudFrame) else None
            self._camera.fit(self._record, origin)
            self._schedule_frame()

    @pyqtSlot()
    def reset_camera(self):
        origin = self._camera.origin.copy()
        self._camera = PointCloudCamera()
        if isinstance(self._record, PointCloudFrame):
            self._camera.origin = origin
        self.fit_view()

    def mousePressEvent(self, event):
        if self._record is None:
            event.ignore()
            return
        self._position = event.position()
        self._drag_button = event.button()
        self.setKeepMouseGrab(True)
        self.forceActiveFocus()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._position is None:
            event.ignore()
            return
        delta = event.position() - self._position
        if self._drag_button == Qt.MouseButton.LeftButton:
            self._camera.orbit(delta.x(), delta.y())
        else:
            self._camera.pan(delta.x(), delta.y(), self.height())
        self._position = event.position()
        self._schedule_frame()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._position = None
        self.setKeepMouseGrab(False)
        event.accept()

    def mouseUngrabEvent(self):
        self._position = None
        self.setKeepMouseGrab(False)
        super().mouseUngrabEvent()

    def wheelEvent(self, event):
        if self._record is None:
            event.ignore()
            return
        self._camera.zoom(event.angleDelta().y())
        self._schedule_frame()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.fit_view()
        event.accept()

    @pyqtSlot()
    def stop(self):
        self._stopped = True
        self._active = False
        self._position = None
        self.setKeepMouseGrab(False)
        self.update()
