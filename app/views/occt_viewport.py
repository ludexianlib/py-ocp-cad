"""QML-facing viewport. OCCT rendering stays on Qt's render thread."""

import math

from PyQt6.QtCore import QObject, Qt, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQuick import QQuickFramebufferObject

from app.views.occt_renderer import OcctRenderer


class OcctViewport(QQuickFramebufferObject):
    controller_changed = pyqtSignal()
    view_mode_changed = pyqtSignal()
    render_state_changed = pyqtSignal()
    orbit_started = pyqtSignal()
    context_menu_requested = pyqtSignal(float, float)
    _render_result = pyqtSignal(bool, str)
    _shape_result = pyqtSignal(object, str)
    _navigation_started = pyqtSignal()
    _pick_result = pyqtSignal(object, str, bool, bool, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controller = None
        self._shape = None
        self._display_shape = None
        self._appearance = None
        self._entity_snapshot = ()
        self._view_mode = "iso"
        self._pending_commands = []
        self._render_ready = False
        self._error_text = ""
        self._drag_mode = ""
        self._press_position = None
        self._last_position = None
        self._drag_button = Qt.MouseButton.NoButton
        self._drag_started = False
        self.setMirrorVertically(True)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.MiddleButton | Qt.MouseButton.RightButton
        )
        self._render_result.connect(self._set_render_state, Qt.ConnectionType.QueuedConnection)
        self._shape_result.connect(self._set_shape_state, Qt.ConnectionType.QueuedConnection)
        self._navigation_started.connect(self.orbit_started, Qt.ConnectionType.QueuedConnection)
        self._pick_result.connect(self._apply_pick, Qt.ConnectionType.QueuedConnection)

    @pyqtProperty(QObject, notify=controller_changed)
    def controller(self):
        return self._controller

    @controller.setter
    def controller(self, value):
        if self._controller is value:
            return
        if self._controller is not None:
            self._controller.state_changed.disconnect(self._refresh_shape)
            self._controller.entity_state_changed.disconnect(self._refresh_entities)
        self._controller = value
        if value is not None:
            value.state_changed.connect(self._refresh_shape)
            value.entity_state_changed.connect(self._refresh_entities)
        self._refresh_shape()
        self.controller_changed.emit()

    @pyqtProperty(str, notify=view_mode_changed)
    def view_mode(self):
        return self._view_mode

    @view_mode.setter
    def view_mode(self, value):
        if value not in {"iso", "front", "top", "free"} or value == self._view_mode:
            return
        self._view_mode = value
        if value != "free":
            self._queue_command("view", value)
        self.view_mode_changed.emit()

    @pyqtProperty(bool, notify=render_state_changed)
    def render_ready(self):
        return self._render_ready

    @pyqtProperty(str, notify=render_state_changed)
    def error_text(self):
        return self._error_text

    @pyqtSlot()
    def _refresh_shape(self):
        shape = self._controller.active_shape if self._controller is not None else None
        if shape is not self._shape:
            self._shape = shape
            self._display_shape = self._controller.active_display_shape if self._controller is not None else None
            self._appearance = self._controller.active_appearance if self._controller is not None else None
            self._refresh_entities()
            self._pending_commands.clear()
            self._reset_drag()
            self.update()

    @pyqtSlot()
    def _refresh_entities(self):
        tree = self._controller.active_entities if self._controller is not None else None
        self._entity_snapshot = tree.snapshot() if tree is not None else ()
        self.update()

    @pyqtSlot(object, str, bool, bool, float, float)
    def _apply_pick(self, shape, node_id, additive, context, x, y):
        if self._controller is None or shape is not self._shape or self._controller.loading:
            return
        self._controller.select_entity(node_id, additive, context)
        if context:
            self.context_menu_requested.emit(x, y)

    @pyqtSlot(object, str)
    def _set_shape_state(self, shape, error_text):
        if self._controller is not None and shape is self._shape:
            self._controller.report_model_displayed(shape, error_text)

    @pyqtSlot(bool, str)
    def _set_render_state(self, ready, error_text):
        if (ready, error_text) != (self._render_ready, self._error_text):
            self._render_ready = ready
            self._error_text = error_text
            self.render_state_changed.emit()

    def _queue_command(self, command, *arguments):
        # Only the newest position matters between two rendered frames.
        if command == "hover" and self._pending_commands and self._pending_commands[-1][0] == "hover":
            self._pending_commands[-1] = (command, *arguments)
            self.update()
            return
        self._pending_commands.append((command, *arguments))
        self.update()

    @pyqtSlot()
    def fit_view(self):
        self._queue_command("fit")

    def createRenderer(self):  # Qt virtual method names follow the Qt API.
        return OcctRenderer(self._render_result.emit, self._shape_result.emit,
                            self._navigation_started.emit, self._pick_result.emit)

    def _reset_drag(self):
        self._drag_mode = ""
        self._press_position = None
        self._last_position = None
        self._drag_button = Qt.MouseButton.NoButton
        self._drag_started = False
        self.setKeepMouseGrab(False)

    def _handle_hover(self, event):
        if self._shape is None or not self._render_ready or self._drag_mode:
            event.ignore()
            return
        position = event.position()
        self._queue_command("hover", position.x(), position.y())
        event.accept()

    def hoverEnterEvent(self, event):
        self._handle_hover(event)

    def hoverMoveEvent(self, event):
        self._handle_hover(event)

    def hoverLeaveEvent(self, event):
        self._queue_command("hover_clear")
        event.accept()

    def mousePressEvent(self, event):
        if self._shape is None or not self._render_ready:
            event.ignore()
            return
        if self._drag_mode:
            event.accept()
            return
        position = event.position()
        self._press_position = (position.x(), position.y())
        self._last_position = self._press_position
        self._drag_button = event.button()
        self._drag_started = False
        self._drag_mode = "pan"
        if event.button() == Qt.MouseButton.LeftButton and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self._drag_mode = "rotate"
        self.setKeepMouseGrab(True)
        self.forceActiveFocus()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._drag_mode or self._last_position is None:
            event.ignore()
            return
        position = (event.position().x(), event.position().y())
        if not self._drag_started:
            distance = sum(abs(value - origin) for value, origin in zip(position, self._press_position))
            if distance < QGuiApplication.styleHints().startDragDistance():
                event.accept()
                return
            self._drag_started = True
            self._queue_command("hover_clear")
            if self._drag_mode == "rotate":
                self._queue_command("rotate_start", *self._press_position)
        if self._drag_mode == "rotate":
            self._queue_command("rotate", *position)
        else:
            self._queue_command(
                "pan", position[0] - self._last_position[0], self._last_position[1] - position[1]
            )
        self._last_position = position
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != self._drag_button:
            event.ignore()
            return
        position = event.position()
        if not self._drag_started and self._drag_button in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            context = self._drag_button == Qt.MouseButton.RightButton
            self._queue_command("pick", position.x(), position.y(), additive, context)
        elif self.contains(position):
            self._queue_command("hover", position.x(), position.y())
        self._reset_drag()
        event.accept()

    def mouseUngrabEvent(self):
        self._reset_drag()
        self._queue_command("hover_clear")
        super().mouseUngrabEvent()

    def mouseDoubleClickEvent(self, event):
        if self._shape is None or not self._render_ready:
            event.ignore()
            return
        self._reset_drag()
        self._queue_command("hover_clear")
        position = event.position()
        self._queue_command("double_click", position.x(), position.y())
        event.accept()

    def wheelEvent(self, event):
        if self._shape is None or not self._render_ready:
            event.ignore()
            return
        steps = event.angleDelta().y() / 120.0
        if not steps:
            steps = event.pixelDelta().y() / 40.0
        if not math.isfinite(steps) or not steps:
            event.ignore()
            return
        self._queue_command("zoom", 1.15 ** max(-4.0, min(4.0, steps)))
        event.accept()
