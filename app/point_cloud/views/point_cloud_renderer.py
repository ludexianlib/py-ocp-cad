"""Draw immutable point data directly into Qt Quick's OpenGL framebuffer."""

import ctypes
import logging
import sys
import weakref

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMatrix4x4, QOpenGLContext
from PyQt6.QtOpenGL import QOpenGLBuffer, QOpenGLFunctions_4_1_Core, QOpenGLShader, QOpenGLShaderProgram, QOpenGLVertexArrayObject
from PyQt6.QtQuick import QQuickFramebufferObject

from app.point_cloud.models.point_cloud_frame import PointCloudFrame


_VERTEX_SHADER = """#version 410 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec3 color;
layout(location = 2) in float intensity;
uniform mat4 view_projection;
uniform float point_size;
uniform int color_mode;
uniform float height_min;
uniform float height_span;
out vec3 point_color;
void main() {
    gl_Position = view_projection * vec4(position, 1.0);
    gl_PointSize = point_size;
    float scalar = color_mode == 2 ? (position.z - height_min) / height_span : intensity;
    float t = clamp(scalar, 0.0, 1.0);
    vec3 gradient = mix(vec3(0.15, 0.30, 0.85), vec3(1.0, 0.75, 0.10), t);
    point_color = color_mode == 1 ? color : color_mode >= 2 ? gradient : vec3(0.40, 0.30, 0.80);
}
"""
_FRAGMENT_SHADER = """#version 410 core
in vec3 point_color;
out vec4 fragment_color;
void main() {
    vec2 offset = 2.0 * gl_PointCoord - 1.0;
    if (dot(offset, offset) > 1.0) discard;
    fragment_color = vec4(point_color, 1.0);
}
"""


class PointCloudRenderer(QQuickFramebufferObject.Renderer):
    def __init__(self, report_frame):
        super().__init__()
        self._report_frame = report_frame
        self._quick_window = None
        self._release_callback = None
        self._functions = None
        self._program = None
        self._buffer = None
        self._vertex_array = None
        self._depth_buffer = 0
        self._depth_size = None
        self._delete_renderbuffers = None
        self._record = None
        self._uploaded_record = None
        self._serial = -1
        self._notified = None
        self._active = False
        self._matrix = np.eye(4)
        self._point_size = 3.0
        self._max_point_size = 1.0
        self._use_rgb = True
        self._color_mode = "rgb"
        self._origin = np.zeros(3)
        self._uploaded_origin = None
        self._capacity = 0
        self._failed = False

    def synchronize(self, item):
        window = item.window()
        if self._quick_window is None and window is not None:
            self._quick_window = window
            renderer_ref = weakref.ref(self)

            def release_resources():
                renderer = renderer_ref()
                if renderer is not None:
                    renderer._release_resources()

            self._release_callback = release_resources
            window.sceneGraphInvalidated.connect(release_resources, Qt.ConnectionType.DirectConnection)
        if (self._serial, self._record) != (item._serial, item._record):
            self._failed = False
        self._serial, self._record = item._serial, item._record
        self._active = item._active and not item._stopped
        self._matrix = item._camera.view_projection(item.width() / max(item.height(), 1))
        self._origin = item._camera.origin.copy()
        if item._controller is not None:
            ratio = window.devicePixelRatio() if window is not None else 1
            self._point_size = item._controller.point_size * ratio
            self._use_rgb = item._controller.use_rgb
            self._color_mode = item._controller.color_mode

    # Use Qt's default FBO factory, avoiding the PyQt6 6.7.1 cross-module FBO
    # conversion crash also worked around by the OCCT renderer.
    def _initialize(self):
        context = QOpenGLContext.currentContext()
        if context is None:
            raise RuntimeError("未获得 OpenGL 上下文。")
        functions = QOpenGLFunctions_4_1_Core()
        if not functions.initializeOpenGLFunctions():
            raise RuntimeError("点云预览需要 OpenGL 4.1 Core 或更新的显卡驱动。")
        self._functions = functions
        # GL_ALIASED_POINT_SIZE_RANGE is not valid in a core profile.
        self._max_point_size = max(1.0, float(functions.glGetFloatv(0x0B12)[1]))  # GL_POINT_SIZE_RANGE
        # These two output-pointer functions are not exposed by PyQt6's core
        # function wrapper. Resolve them from Qt's current context, not a DLL.
        call_type = ctypes.WINFUNCTYPE if sys.platform == "win32" else ctypes.CFUNCTYPE
        signature = call_type(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint))
        gen_address = context.getProcAddress(b"glGenRenderbuffers")
        delete_address = context.getProcAddress(b"glDeleteRenderbuffers")
        if not gen_address or not delete_address:
            raise RuntimeError("显卡不支持点云深度缓冲。")
        generate = signature(int(gen_address))
        self._delete_renderbuffers = signature(int(delete_address))
        depth = ctypes.c_uint()
        generate(1, ctypes.byref(depth))
        self._depth_buffer = depth.value
        if not self._depth_buffer:
            raise RuntimeError("无法创建点云深度缓冲。")
        logging.getLogger(__name__).info("Point cloud OpenGL vendor=%s renderer=%s version=%s",
            functions.glGetString(0x1F00), functions.glGetString(0x1F01), functions.glGetString(0x1F02))

    def _prepare_depth(self, size):
        functions = self._functions
        functions.glBindRenderbuffer(0x8D41, self._depth_buffer)  # GL_RENDERBUFFER
        if size != self._depth_size:
            functions.glRenderbufferStorage(0x8D41, 0x81A6, *size)  # GL_DEPTH_COMPONENT24
            self._depth_size = size
        functions.glFramebufferRenderbuffer(0x8D40, 0x8D00, 0x8D41, self._depth_buffer)
        if functions.glCheckFramebufferStatus(0x8D40) != 0x8CD5:  # GL_FRAMEBUFFER_COMPLETE
            raise RuntimeError("点云帧缓冲不完整。")

    def _initialize_program(self):
        program = QOpenGLShaderProgram()
        for shader_type, source in ((QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX_SHADER),
                                    (QOpenGLShader.ShaderTypeBit.Fragment, _FRAGMENT_SHADER)):
            if not program.addShaderFromSourceCode(shader_type, source):
                raise RuntimeError("点云着色器编译失败：" + program.log())
        if not program.link():
            raise RuntimeError("点云着色器链接失败：" + program.log())
        self._program = program

    def _upload_cloud(self, record):
        # Center in float64 before converting to GPU float32 to retain small
        # coordinate differences in survey data with large world offsets.
        vertices = np.empty((len(record.points), 7), dtype=np.float32)
        vertices[:, :3] = record.points - self._origin
        vertices[:, 3:6] = record.colors if record.colors is not None else 0
        vertices[:, 6] = 0
        if getattr(record, "intensity", None) is not None:
            low, high = record.intensity_range
            # Normalize in float64 before upload; preserve the sender's fixed range.
            vertices[:, 6] = (np.clip(record.intensity, low, high) - low) / (high - low)
        if (isinstance(record, PointCloudFrame) and isinstance(self._uploaded_record, PointCloudFrame)
                and self._buffer is not None and vertices.nbytes <= self._capacity):
            try:
                if not self._buffer.bind():
                    raise RuntimeError("无法绑定点云 GPU 缓冲区。")
                if vertices.nbytes:
                    self._buffer.write(0, sip.voidptr(vertices.ctypes.data), vertices.nbytes)
                error = self._functions.glGetError()
                if error:
                    # Force a full restore of the last acknowledged frame.
                    self._uploaded_record = None
                    raise RuntimeError(f"点云 GPU 数据更新失败（OpenGL 错误 {error:#x}）。")
            except Exception:
                self._uploaded_record = None
                raise
            finally:
                self._buffer.release()
            self._uploaded_record = record
            self._uploaded_origin = self._origin.copy()
            return
        buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        vertex_array = QOpenGLVertexArrayObject()
        try:
            if not buffer.create() or not vertex_array.create():
                raise RuntimeError("无法创建点云 GPU 缓冲区。")
            vertex_array.bind()
            if not buffer.bind():
                raise RuntimeError("无法绑定点云 GPU 缓冲区。")
            dynamic = isinstance(record, PointCloudFrame)
            buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.DynamicDraw if dynamic else QOpenGLBuffer.UsagePattern.StaticDraw)
            capacity = max(vertices.nbytes, 28)
            if dynamic:
                capacity = 1 << (capacity - 1).bit_length()
            buffer.allocate(capacity)
            if vertices.nbytes:
                buffer.write(0, sip.voidptr(vertices.ctypes.data), vertices.nbytes)
            self._program.enableAttributeArray(0)
            self._program.setAttributeBuffer(0, 0x1406, 0, 3, 28)  # GL_FLOAT
            self._program.enableAttributeArray(1)
            self._program.setAttributeBuffer(1, 0x1406, 12, 3, 28)
            self._program.enableAttributeArray(2)
            self._program.setAttributeBuffer(2, 0x1406, 24, 1, 28)
            error = self._functions.glGetError()
            if error or buffer.size() != capacity:
                raise RuntimeError(f"点云 GPU 数据上传失败（OpenGL 错误 {error:#x}）。")
        except Exception:
            vertex_array.destroy()
            buffer.destroy()
            raise
        finally:
            vertex_array.release()
            buffer.release()
        # Replace resources only after upload succeeds, retaining the previous
        # document's GPU data when an import cannot be previewed.
        if self._vertex_array is not None:
            self._vertex_array.destroy()
            self._buffer.destroy()
        self._buffer, self._vertex_array, self._uploaded_record = buffer, vertex_array, record
        self._capacity = capacity
        self._uploaded_origin = self._origin.copy()

    def _reset_gl_state(self):
        functions = self._functions
        functions.glBindVertexArray(0)
        functions.glBindBuffer(0x8892, 0)
        functions.glBindRenderbuffer(0x8D41, 0)
        functions.glUseProgram(0)
        for capability in (0x0B71, 0x0B90, 0x0C11, 0x0BE2, 0x0B44, 0x8642):
            functions.glDisable(capability)  # Depth, stencil, scissor, blend, cull, shader point size.
        functions.glColorMask(True, True, True, True)
        functions.glDepthMask(True)
        functions.glDepthFunc(0x0201)  # GL_LESS
        functions.glStencilMask(0xFF)
        functions.glStencilOp(0x1E00, 0x1E00, 0x1E00)
        functions.glStencilFunc(0x0207, 0, 0xFF)
        functions.glBlendFunc(1, 0)
        functions.glActiveTexture(0x84C0)
        functions.glBindTexture(0x0DE1, 0)

    def render(self):
        if not self._active or self._failed:
            return
        framebuffer_id, srgb_enabled = None, False
        try:
            if self._functions is None:
                self._initialize()
            functions = self._functions
            framebuffer_id = functions.glGetIntegerv(0x8CA6)  # GL_FRAMEBUFFER_BINDING
            viewport = functions.glGetIntegerv(0x0BA2)
            size = (viewport[2], viewport[3])
            if not framebuffer_id or min(size) <= 0:
                return
            srgb_enabled = bool(functions.glIsEnabled(0x8DB9))
            self._reset_gl_state()
            functions.glDisable(0x8DB9)  # GL_FRAMEBUFFER_SRGB
            # Errors left by another renderer are not caused by this upload.
            for _ in range(8):
                if not functions.glGetError():
                    break
            self._prepare_depth(size)
            functions.glClearColor(239 / 255, 237 / 255, 250 / 255, 1)
            functions.glClearDepth(1.0)
            functions.glClear(0x4000 | 0x0100)  # Color and depth.
            if self._record is None:
                return
            if self._program is None:
                self._initialize_program()
            if not self._program.bind():
                raise RuntimeError("无法启用点云着色器。")
            if self._record is not self._uploaded_record or not np.array_equal(self._origin, self._uploaded_origin):
                self._upload_cloud(self._record)
            self._vertex_array.bind()
            self._program.setUniformValue("view_projection", QMatrix4x4(*self._matrix.ravel().tolist()))
            self._program.setUniformValue("point_size", float(min(self._point_size, self._max_point_size)))
            mode = {"uniform": 0, "rgb": 1, "height": 2, "intensity": 3}[self._color_mode]
            if (mode == 1 and self._record.colors is None) or (mode == 3 and getattr(self._record, "intensity", None) is None):
                mode = 0
            self._program.setUniformValue("color_mode", mode)
            minimum, maximum = self._record.bounds
            self._program.setUniformValue("height_min", float(minimum[2] - self._origin[2]))
            self._program.setUniformValue("height_span", float(max(maximum[2] - minimum[2], 1e-6)))
            functions.glEnable(0x0B71)  # GL_DEPTH_TEST
            functions.glEnable(0x8642)  # GL_PROGRAM_POINT_SIZE
            functions.glDrawArrays(0x0000, 0, len(self._record.points))  # GL_POINTS
            error = functions.glGetError()
            if error:
                raise RuntimeError(f"点云绘制失败（OpenGL 错误 {error:#x}）。")
            if self._notified != (self._serial, self._record):
                self._notified = (self._serial, self._record)
                self._report_frame(self._serial, self._record, "")
        except Exception as error:
            self._failed = True
            logging.getLogger(__name__).exception("Point cloud OpenGL rendering failed")
            self._report_frame(self._serial, self._record, "点云预览失败：" + str(error))
        finally:
            if self._functions is not None:
                self._reset_gl_state()
                if srgb_enabled:
                    self._functions.glEnable(0x8DB9)
                if framebuffer_id is not None:
                    self._functions.glBindFramebuffer(0x8D40, framebuffer_id)

    def _release_resources(self):
        if self._quick_window is not None and self._release_callback is not None:
            try:
                self._quick_window.sceneGraphInvalidated.disconnect(self._release_callback)
            except (TypeError, RuntimeError):
                pass
        if QOpenGLContext.currentContext() is not None:
            if self._vertex_array is not None:
                self._vertex_array.destroy()
            if self._buffer is not None:
                self._buffer.destroy()
            if self._program is not None:
                self._program.removeAllShaders()
            if self._depth_buffer and self._delete_renderbuffers is not None:
                depth = ctypes.c_uint(self._depth_buffer)
                self._delete_renderbuffers(1, ctypes.byref(depth))
        self._vertex_array = self._buffer = self._program = None
        self._depth_buffer, self._depth_size = 0, None
        self._quick_window = self._release_callback = self._functions = None
        self._uploaded_record = self._notified = None
        self._uploaded_origin = None
        self._capacity = 0
        self._failed = False

    def __del__(self):
        try:
            if QOpenGLContext.currentContext() is not None:
                self._release_resources()
        except Exception:
            logging.getLogger(__name__).debug("Point cloud GPU cleanup", exc_info=True)
