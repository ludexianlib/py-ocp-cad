"""Render OCCT into a Qt-owned framebuffer using the current OpenGL context."""

import ctypes
import logging
import sys
import weakref

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QOpenGLContext
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core
from PyQt6.QtQuick import QQuickFramebufferObject

from OCP.AIS import AIS_DisplayMode, AIS_InteractiveContext, AIS_SelectionScheme, AIS_Shape
from OCP.Aspect import Aspect_DisplayConnection, Aspect_NeutralWindow
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.OpenGl import OpenGl_Context, OpenGl_FrameBuffer, OpenGl_GraphicDriver
from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
from OCP.V3d import V3d_TypeOfOrientation, V3d_Viewer


class OcctRenderer(QQuickFramebufferObject.Renderer):
    def __init__(self, report_result, report_shape):
        super().__init__()
        self._report_result = report_result
        self._report_shape = report_shape
        self._quick_window = None
        self._release_callback = None
        self._window_id = 0
        self._pixel_ratio = 1.0
        self._shape = None
        self._prepared_shape = None
        self._notified_shape = None
        self._displayed_shape = None
        self._view_mode = "iso"
        self._commands = []
        self._functions = None
        self._bind_framebuffer = None
        self._bind_vertex_array = None
        self._driver = None
        self._viewer = None
        self._context = None
        self._view = None
        self._native_window = None
        self._gl_context = None
        self._wrapped_fbo = None
        self._presentation = None
        self._last_size = None
        self._failed = False
        self._ready_reported = False
        self._report_result(False, "")

    def synchronize(self, item):  # Qt blocks the GUI thread during this callback.
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
        if window is not None:
            self._window_id = int(window.winId())
            self._pixel_ratio = window.devicePixelRatio()
        if self._shape is not item._shape:
            self._failed = False
        self._shape = item._shape
        self._prepared_shape = item._display_shape
        self._view_mode = item._view_mode
        self._commands.extend(item._pending_commands)
        item._pending_commands.clear()

    # Keep Qt's default FBO factory. PyQt6 6.7.1 crashes when converting
    # QOpenGLFramebufferObject instances across the QtQuick/QtOpenGL boundary.
    # render() receives an already-bound FBO, so no Qt FBO wrapper is needed.

    def _initialize_functions(self):
        context = QOpenGLContext.currentContext()
        if context is None:
            raise RuntimeError("未获得 OpenGL 上下文。")
        functions = QOpenGLFunctions_4_1_Core()
        if not functions.initializeOpenGLFunctions():
            raise RuntimeError("三维预览需要 OpenGL 4.1 Core 或更新的显卡驱动。")
        self._functions = functions
        self._bind_framebuffer = functions.glBindFramebuffer
        self._bind_vertex_array = functions.glBindVertexArray
        logging.getLogger(__name__).info(
            "OpenGL vendor=%s renderer=%s version=%s",
            functions.glGetString(0x1F00), functions.glGetString(0x1F01), functions.glGetString(0x1F02),
        )

    def _native_handle(self):
        if sys.platform != "win32":
            return self._window_id
        # WGL can render through a Qt helper window rather than the top-level HWND.
        opengl = ctypes.WinDLL("opengl32")
        opengl.wglGetCurrentDC.restype = ctypes.c_void_p
        user32 = ctypes.WinDLL("user32")
        user32.WindowFromDC.argtypes = [ctypes.c_void_p]
        user32.WindowFromDC.restype = ctypes.c_void_p
        window_handle = user32.WindowFromDC(opengl.wglGetCurrentDC())
        if not window_handle:
            raise RuntimeError("未找到可用的桌面 OpenGL 窗口。")
        # OCP represents opaque Windows handles as Python capsules.
        make_capsule = ctypes.pythonapi.PyCapsule_New
        make_capsule.restype = ctypes.py_object
        make_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
        return make_capsule(window_handle, None, None)

    def _initialize(self, framebuffer_id, size):
        # Initialize OCCT against the window framebuffer before wrapping Qt's FBO.
        self._bind_framebuffer(0x8D40, 0)  # GL_FRAMEBUFFER
        external_context = OpenGl_Context()
        if not external_context.Init(True):
            raise RuntimeError("OCCT 无法使用当前 OpenGL 上下文。")
        self._driver = OpenGl_GraphicDriver(Aspect_DisplayConnection(), False)
        options = self._driver.ChangeOptions()
        options.buffersNoSwap = True
        options.buffersOpaqueAlpha = True
        options.useSystemBuffer = False
        options.contextCompatible = False
        options.sRGBDisable = True
        self._viewer = V3d_Viewer(self._driver)
        self._viewer.SetDefaultLights()
        self._viewer.SetLightOn()
        self._context = AIS_InteractiveContext(self._viewer)
        self._view = self._viewer.CreateView()
        self._view.SetImmediateUpdate(False)
        # OCCT's scene FBO supplies depth and antialiasing; Qt owns the color target.
        self._view.ChangeRenderingParams().NbMsaaSamples = 4
        self._native_window = Aspect_NeutralWindow()
        self._native_window.SetVirtual(True)
        self._native_window.SetNativeHandle(self._native_handle())
        self._native_window.SetSize(*size)
        self._view.SetWindow(self._native_window, external_context.RenderingContext())
        self._gl_context = self._view.View().GlWindow().GetGlContext()
        if self._gl_context is None:
            raise RuntimeError("OCCT 渲染上下文创建失败。")
        self._view.SetBackgroundColor(self._color(251, 250, 255))
        self._wrapped_fbo = OpenGl_FrameBuffer()
        self._bind_framebuffer(0x8D40, framebuffer_id)
        logging.getLogger(__name__).info("OCCT view initialized, framebuffer=%s size=%s", framebuffer_id, size)

    @staticmethod
    def _color(red, green, blue):
        return Quantity_Color(red / 255.0, green / 255.0, blue / 255.0, Quantity_TypeOfColor.Quantity_TOC_RGB)

    def _wrap_framebuffer(self, size):
        if not self._wrapped_fbo.InitWrapper(self._gl_context):
            raise RuntimeError("OCCT 无法接入三维预览缓冲区。")
        # Resize against the window before assigning the new default offscreen FBO.
        self._gl_context.SetDefaultFrameBuffer(None)
        if size != self._last_size:
            self._native_window.SetSize(*size)
            self._view.MustBeResized()
            self._view.Invalidate()
            self._last_size = size
        self._gl_context.SetDefaultFrameBuffer(self._wrapped_fbo)

    def _reset_gl_state(self):
        """Restore the state Qt Quick expects after drawing external OpenGL."""
        functions = self._functions
        functions.glBindBuffer(0x8892, 0)  # GL_ARRAY_BUFFER
        self._bind_vertex_array(0)
        functions.glActiveTexture(0x84C0)  # GL_TEXTURE0
        functions.glBindTexture(0x0DE1, 0)  # GL_TEXTURE_2D
        for capability in (0x0B71, 0x0B90, 0x0C11, 0x0BE2):
            functions.glDisable(capability)  # Depth, stencil, scissor, blend.
        functions.glColorMask(True, True, True, True)
        functions.glDepthMask(True)
        functions.glDepthFunc(0x0201)  # GL_LESS
        functions.glStencilMask(0xFF)
        functions.glStencilOp(0x1E00, 0x1E00, 0x1E00)  # GL_KEEP
        functions.glStencilFunc(0x0207, 0, 0xFF)  # GL_ALWAYS
        functions.glBlendFunc(1, 0)  # GL_ONE, GL_ZERO
        functions.glUseProgram(0)
        for alignment in (0x0D05, 0x0CF5):  # GL_PACK_ALIGNMENT, GL_UNPACK_ALIGNMENT
            functions.glPixelStorei(alignment, 4)
        for row_length in (0x0D02, 0x0CF2):  # GL_PACK_ROW_LENGTH, GL_UNPACK_ROW_LENGTH
            functions.glPixelStorei(row_length, 0)

    def _set_projection(self, view_mode):
        orientations = {
            "iso": V3d_TypeOfOrientation.V3d_XposYnegZpos,
            "front": V3d_TypeOfOrientation.V3d_Yneg,
            "top": V3d_TypeOfOrientation.V3d_Zpos,
        }
        if view_mode in orientations:
            self._view.SetProj(orientations[view_mode])

    def _fit_view(self):
        if self._displayed_shape is not None:
            self._view.FitAll(0.12, False)
            self._view.ZFitAll()

    def _update_shape(self):
        if self._displayed_shape is self._shape:
            return
        self._context.RemoveAll(False)
        self._presentation = None
        self._displayed_shape = None
        if self._shape is not None and not self._shape.IsNull():
            # AIS triangulates its input. Give it a view-owned copy so rendering
            # and STEP export never modify/read the same triangulation in parallel.
            display_shape = self._prepared_shape
            if display_shape is None:
                display_shape = BRepBuilderAPI_Copy(self._shape, True, False).Shape()
            self._presentation = AIS_Shape(display_shape)
            if self._prepared_shape is not None:
                self._presentation.Attributes().SetAutoTriangulation(False)
            self._presentation.SetColor(self._color(128, 105, 206))
            self._presentation.Attributes().SetFaceBoundaryDraw(True)
            self._context.Display(self._presentation, AIS_DisplayMode.AIS_Shaded, 0, False)
            self._displayed_shape = self._shape
            self._set_projection(self._view_mode)
            self._fit_view()

    def _apply_commands(self):
        commands, self._commands = self._commands, []
        for command, *arguments in commands:
            if command == "view":
                self._set_projection(arguments[0])
                self._fit_view()
            elif command == "fit":
                self._fit_view()
            elif command == "hover_clear":
                self._context.ClearDetected(False)
            elif self._displayed_shape is not None:
                if command in {"hover", "select"}:
                    x, y = (round(value * self._pixel_ratio) for value in arguments)
                    if 0 <= x < self._last_size[0] and 0 <= y < self._last_size[1]:
                        self._context.MoveTo(x, y, self._view, False)
                    else:
                        self._context.ClearDetected(False)
                    if command == "select":
                        self._context.SelectDetected(AIS_SelectionScheme.AIS_SelectionScheme_Replace)
                elif command == "rotate_start":
                    self._view.StartRotation(*(round(value * self._pixel_ratio) for value in arguments))
                elif command == "rotate":
                    self._view.Rotation(*(round(value * self._pixel_ratio) for value in arguments))
                elif command == "pan":
                    self._view.Pan(*(round(value * self._pixel_ratio) for value in arguments))
                elif command == "zoom":
                    scale = self._view.Camera().Scale() / arguments[0]
                    if 0.00001 <= scale <= 1_000_000_000:
                        self._view.SetZoom(arguments[0])

    def render(self):
        if self._failed:
            return
        framebuffer_id = None
        try:
            if self._functions is None:
                self._initialize_functions()
            framebuffer_id = self._functions.glGetIntegerv(0x8CA6)  # GL_FRAMEBUFFER_BINDING
            viewport = self._functions.glGetIntegerv(0x0BA2)  # GL_VIEWPORT (physical pixels)
            size = (viewport[2], viewport[3])
            if not framebuffer_id or min(size) <= 0:
                return
            if self._view is None:
                self._initialize(framebuffer_id, size)
            self._wrap_framebuffer(size)
            # Qt and OCCT cache GL state independently. Clear Qt's drawing state.
            self._reset_gl_state()
            self._update_shape()
            self._apply_commands()
            self._view.Redraw()
            if self._notified_shape is not self._displayed_shape:
                self._notified_shape = self._displayed_shape
                self._report_shape(self._displayed_shape, "")
            if not self._ready_reported:
                self._ready_reported = True
                self._report_result(True, "")
                logging.getLogger(__name__).info("OCCT first frame rendered")
        except Exception as error:
            self._failed = True
            self._ready_reported = False
            logging.getLogger(__name__).exception("OCCT viewport rendering failed")
            error_text = "三维预览加载失败：" + str(error)
            self._report_result(False, error_text)
            self._report_shape(self._shape, error_text)
        finally:
            if self._functions is not None and self._bind_vertex_array is not None:
                self._reset_gl_state()
                if framebuffer_id is not None:
                    self._bind_framebuffer(0x8D40, framebuffer_id)

    def _release_resources(self):
        """Called on the rendering thread while Qt's GL context is still current."""
        if self._release_callback is not None and self._quick_window is not None:
            try:
                self._quick_window.sceneGraphInvalidated.disconnect(self._release_callback)
            except (TypeError, RuntimeError):
                pass  # Qt may have disconnected signals during window teardown.
            self._release_callback = None
        cleanup_operations = []
        if (
            sys.platform == "win32"
            and self._view is not None
            and self._gl_context is not None
            and QOpenGLContext.currentContext() is not None
            and not self._gl_context.IsCurrent()
        ):
            # Qt can switch the same GL context to a cleanup surface on exit.
            # OCCT must borrow its current HDC, not reactivate the old window HDC.
            self._native_window.SetNativeHandle(self._native_handle())
            native_window = self._view.View().GlWindow()
            native_window.Init(
                self._driver,
                self._native_window,
                self._native_window,
                self._gl_context.RenderingContext(),
                self._driver.ChangeOptions(),
                self._gl_context,
            )
            self._gl_context = native_window.GetGlContext()
        if self._context is not None:
            cleanup_operations.append((self._context.RemoveAll, (False,)))
        if self._gl_context is not None:
            cleanup_operations.append((self._gl_context.SetDefaultFrameBuffer, (None,)))
            if self._wrapped_fbo is not None:
                cleanup_operations.append((self._wrapped_fbo.Release, (self._gl_context,)))
        if self._view is not None:
            cleanup_operations.append((self._view.Remove, ()))
        for cleanup_function, arguments in cleanup_operations:
            try:
                cleanup_function(*arguments)
            except Exception:
                logging.getLogger(__name__).debug("OCCT resource cleanup", exc_info=True)
        self._presentation = None
        self._displayed_shape = None
        self._prepared_shape = None
        self._notified_shape = None
        self._wrapped_fbo = None
        self._context = None
        self._view = None
        self._viewer = None
        self._gl_context = None
        self._native_window = None
        self._driver = None
        self._functions = None
        self._bind_framebuffer = None
        self._bind_vertex_array = None
        self._quick_window = None
        self._last_size = None
        self._failed = False
        self._ready_reported = False

    def __del__(self):
        try:
            if QOpenGLContext.currentContext() is not None:
                self._release_resources()
        except Exception:
            # Python shutdown may already have destroyed the Qt window wrapper.
            logging.getLogger(__name__).debug("OCCT viewport cleanup", exc_info=True)
