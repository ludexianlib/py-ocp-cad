"""QML image viewport with coalesced requests to an isolated GPU process."""

import multiprocessing
import threading

from PyQt6.QtCore import QCoreApplication, QObject, QRectF, QThread, QTimer, Qt, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtQuick import QQuickPaintedItem

from app.point_cloud.views.open3d_renderer import PointCloudCamera
from app.point_cloud.views.render_process import render_point_cloud


class PointCloudRenderThread(QThread):
    frame_ready = pyqtSignal(int, object, object)
    failed = pyqtSignal(int, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._condition = threading.Condition()
        self._pending = None
        self._stopping = False
        self._active = True
        self._process = None
        self._connection = None
        self._loaded_record = None

    def submit(self, request):
        with self._condition:
            self._pending = request
            self._condition.notify()

    def set_active(self, active):
        with self._condition:
            self._active = active
            self._condition.notify()

    def stop(self):
        with self._condition:
            self._stopping = True
            self._pending = None
            self._condition.notify()
        if not self.wait(5000):
            # Recover even when a native driver call in the GPU process is stuck.
            process = self._process
            try:
                if process is not None and process.is_alive():
                    process.terminate()
            except (ValueError, OSError):
                pass
            self.wait()

    def _close_process(self):
        process, connection = self._process, self._connection
        if process is not None:
            if process.is_alive():
                try:
                    connection.send(None)
                except (BrokenPipeError, EOFError, OSError):
                    pass
                process.join(3)
                if process.is_alive():
                    process.terminate()
                    process.join(3)
            else:
                process.join()
            connection.close()
            process.close()
        self._process = self._connection = self._loaded_record = None

    def _render(self, record, width, height, camera, point_size, use_rgb):
        if self._process is None or not self._process.is_alive():
            self._close_process()
            context = multiprocessing.get_context("spawn")
            self._connection, child = context.Pipe()
            self._process = context.Process(target=render_point_cloud, args=(child,), daemon=True)
            self._process.start()
            child.close()
        self._connection.send({
            "record": record if record is not self._loaded_record else None,
            "size": (width, height), "camera": camera, "point_size": point_size, "use_rgb": use_rgb,
        })
        if not self._connection.poll(30):
            self._process.terminate()
            raise RuntimeError("点云渲染响应超时，请检查显卡驱动后重试。")
        success, result = self._connection.recv()
        if not success:
            raise RuntimeError(result)
        self._loaded_record = record
        return result

    def run(self):
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._stopping or self._active and self._pending is not None)
                    if self._stopping:
                        break
                    request, self._pending = self._pending, None
                serial, record, width, height, camera, point_size, use_rgb = request
                try:
                    pixels = self._render(record, width, height, camera, point_size, use_rgb)
                    image_format = QImage.Format.Format_RGBA8888 if pixels.shape[2] == 4 else QImage.Format.Format_RGB888
                    frame = QImage(pixels.data, width, height, pixels.strides[0], image_format).copy()
                    self.frame_ready.emit(serial, record, frame)
                except Exception as error:
                    self._loaded_record = None
                    if not self._stopping:
                        self.failed.emit(serial, record, str(error) or "点云渲染失败。")
        finally:
            self._close_process()


class PointCloudViewport(QQuickPaintedItem):
    controller_changed = pyqtSignal()
    active_changed = pyqtSignal()
    render_state_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controller = None
        self._active = False
        self._record = None
        self._camera = PointCloudCamera()
        self._image = QImage()
        self._error_text = ""
        self._worker = None
        self._serial = 0
        self._accepted_serial = -1
        self._position = None
        self._drag_button = Qt.MouseButton.NoButton
        self._stopped = False
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(16)
        self._render_timer.timeout.connect(self._submit_frame)
        self.widthChanged.connect(self._schedule_frame)
        self.heightChanged.connect(self._schedule_frame)
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
            if self._worker is not None:
                self._worker.set_active(value)
            if value:
                self._schedule_frame()
            else:
                self._render_timer.stop()
            self.active_changed.emit()

    @pyqtProperty(str, notify=render_state_changed)
    def error_text(self):
        return self._error_text

    @pyqtProperty(bool, notify=render_state_changed)
    def render_ready(self):
        return not self._image.isNull()

    def _preview(self, record):
        self._record = record
        self._camera.fit(record)
        self._error_text = ""
        self.render_state_changed.emit()
        self._schedule_frame()

    def _schedule_frame(self):
        if self._active and self._record is not None and not self._stopped:
            self._serial += 1
            if not self._render_timer.isActive():
                self._render_timer.start()

    def _submit_frame(self):
        if not self._active or self._record is None or self._stopped or self._controller is None:
            return
        if self.width() < 2 or self.height() < 2:
            return
        if self._worker is None:
            self._worker = PointCloudRenderThread(self)
            self._worker.frame_ready.connect(self._accept_frame)
            self._worker.failed.connect(self._render_failed)
            self._worker.start()
        ratio = self.window().devicePixelRatio() if self.window() else 1
        self._worker.submit((
            self._serial, self._record, max(2, round(self.width() * ratio)), max(2, round(self.height() * ratio)),
            self._camera.snapshot(), self._controller.point_size * ratio, self._controller.use_rgb,
        ))

    def _accept_frame(self, serial, record, frame):
        if self._stopped or serial <= self._accepted_serial or record is not self._record:
            return
        self._accepted_serial = serial
        self._image = frame
        self._error_text = ""
        self.update()
        self.render_state_changed.emit()
        self._controller.report_preview(record)

    def _render_failed(self, serial, record, message):
        if self._stopped or serial != self._serial or record is not self._record:
            return
        self._error_text = message
        self._controller.report_preview(record, message)
        self._record = self._controller.current_record
        if self._record is not None:
            self._camera.fit(self._record)
        self.render_state_changed.emit()

    @pyqtSlot()
    def fit_view(self):
        if self._record is not None:
            self._camera.fit(self._record)
            self._schedule_frame()

    @pyqtSlot()
    def reset_camera(self):
        self._camera = PointCloudCamera()
        self.fit_view()

    def paint(self, painter):
        target = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(target, QColor("#efedfa"))
        if not self._image.isNull():
            painter.drawImage(target, self._image, QRectF(self._image.rect()))

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
        self._render_timer.stop()
        if self._worker is not None:
            self._worker.stop()
