"""Start the Python/QML workbench; no native compilation step is needed."""

import argparse
import faulthandler
import logging
import os
from pathlib import Path
import sys

_fault_log = None
_graphics_configured = False


def configure_diagnostics():
    global _fault_log
    log_directory = Path(__file__).resolve().parent / "out"
    log_directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_directory / "workbench.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    if _fault_log is None:
        _fault_log = (log_directory / "workbench-crash.log").open("a", encoding="utf-8")
        faulthandler.enable(file=_fault_log, all_threads=True)

    def log_exception(error_type, error, trace):
        logging.getLogger(__name__).critical("Unhandled Python exception", exc_info=(error_type, error, trace))

    sys.excepthook = log_exception
    logging.getLogger(__name__).info("Starting workbench: executable=%s Python=%s", sys.executable, sys.version)


def configure_windows_identity():
    """Give the workbench its own Windows taskbar group instead of Python's."""
    if sys.platform != "win32":
        return
    import ctypes

    shell32 = ctypes.WinDLL("shell32")
    set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
    set_app_id.argtypes = [ctypes.c_wchar_p]
    set_app_id.restype = ctypes.c_long
    result = set_app_id("CadStudio.Workbench")
    if result < 0:
        logging.getLogger(__name__).warning("Windows AppUserModelID failed: 0x%08X", result & 0xFFFFFFFF)


def configure_graphics():
    global _graphics_configured
    if _graphics_configured:
        return
    from PyQt6.QtGui import QSurfaceFormat
    from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_OPENGL", "desktop")
    surface_format = QSurfaceFormat()
    surface_format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    surface_format.setVersion(4, 1)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(surface_format)
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
    _graphics_configured = True


def create_engine(application):
    from PyQt6.QtCore import QStandardPaths, QUrl
    from PyQt6.QtQml import QQmlApplicationEngine, QQmlEngine, qmlRegisterType
    from PyQt6.QtQuick import QQuickWindow

    from app.controllers.cad_controller import CadController
    from app.views.occt_viewport import OcctViewport

    configure_graphics()
    qmlRegisterType(OcctViewport, "Cad.Native", 1, 0, "OcctViewport")
    controller = CadController(application)
    QQmlEngine.setObjectOwnership(controller, QQmlEngine.ObjectOwnership.CppOwnership)
    engine = QQmlApplicationEngine()
    documents_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    documents_folder = QUrl.fromLocalFile(documents_path or str(Path.home()))
    engine.setInitialProperties({"cad_controller": controller, "documents_folder": documents_folder})
    qml_path = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if engine.rootObjects() and not isinstance(engine.rootObjects()[0], QQuickWindow):
        raise RuntimeError("QML 入口必须创建 Qt Quick 窗口。")
    return engine, controller


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Python CAD workbench")
    parser.add_argument("--screenshot", type=Path, help="Save the rendered workbench to an image, then exit.")
    options = parser.parse_args(argv)
    configure_diagnostics()
    try:
        from PyQt6.QtCore import QEvent, QTimer, QtMsgType, qInstallMessageHandler
        from PyQt6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon

        def log_qt_message(message_type, context, message):
            level = {
                QtMsgType.QtDebugMsg: logging.DEBUG,
                QtMsgType.QtInfoMsg: logging.INFO,
                QtMsgType.QtWarningMsg: logging.WARNING,
                QtMsgType.QtCriticalMsg: logging.ERROR,
                QtMsgType.QtFatalMsg: logging.CRITICAL,
            }.get(message_type, logging.INFO)
            logging.getLogger("qt").log(level, "%s: %s", context.category, message)

        qInstallMessageHandler(log_qt_message)
        configure_windows_identity()
        configure_graphics()
        application = QGuiApplication([sys.argv[0]])
        logging.getLogger(__name__).info("Qt platform=%s", application.platformName())
        application.setApplicationName("Cad Workspace")
        application.setOrganizationName("Cad Workspace")
        icon_name = "cad-studio.ico" if sys.platform == "win32" else "cad-studio.svg"
        icon_path = Path(__file__).resolve().parent / "assets" / icon_name
        application.setWindowIcon(QIcon(str(icon_path)))
        font_file = os.environ.get("CAD_WORKSPACE_FONT")
        if font_file:
            QFontDatabase.addApplicationFont(font_file)
        families = set(QFontDatabase.families())
        for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI", "DejaVu Sans"):
            if family in families:
                font = QFont(family)
                font.setPixelSize(13)
                application.setFont(font)
                break
        engine, controller = create_engine(application)
    except ModuleNotFoundError as error:
        print(f"缺少依赖：{error.name}。请运行 .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt", file=sys.stderr)
        return 1

    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if options.screenshot:
        def capture_window():
            try:
                options.screenshot.parent.mkdir(parents=True, exist_ok=True)
                image = window.grabWindow()
                if image.isNull() or not image.save(str(options.screenshot)):
                    raise RuntimeError("无法读取或保存界面图像。")
            except Exception as error:
                print(f"界面截图失败：{error}", file=sys.stderr)
                application.exit(2)
                return
            print(f"界面截图：{options.screenshot}")
            application.quit()

        QTimer.singleShot(1100, capture_window)
    exit_code = application.exec()
    # Destroy QML windows/renderers while QApplication and its GL services live.
    engine.deleteLater()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    logging.getLogger(__name__).info("Workbench exited: code=%s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
