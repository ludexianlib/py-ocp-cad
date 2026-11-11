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


def configure_fonts(application):
    """Choose available outline fonts before creating QML controls/popups."""
    from PyQt6.QtGui import QFont, QFontDatabase

    preferred = []
    font_file = os.environ.get("CAD_WORKSPACE_FONT")
    if font_file:
        font_id = QFontDatabase.addApplicationFont(font_file)
        if font_id >= 0:
            preferred.extend(QFontDatabase.applicationFontFamilies(font_id))
    available = set(QFontDatabase.families())
    preferred.extend(family for family in (
        "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI", "DejaVu Sans", "Segoe UI Symbol"
    ) if family in available)
    preferred.append(application.font().family())
    if sys.platform == "win32":
        fixed_fallbacks = [family for family in ("Consolas", "Courier New") if family in available]
        if fixed_fallbacks:
            QFont.insertSubstitutions("Fixedsys", fixed_fallbacks)
    font = QFont()
    font.setFamilies(list(dict.fromkeys(preferred)))
    font.setPixelSize(13)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setStyleStrategy(QFont.StyleStrategy.PreferOutline)
    application.setFont(font)


def _create_engine_steps(application, startup=None):
    """Yield actual loading stages; the startup controller schedules them by frame."""
    from PyQt6.QtCore import QStandardPaths, QUrl
    from PyQt6.QtQml import QQmlApplicationEngine, QQmlEngine, qmlRegisterType
    from PyQt6.QtQuick import QQuickWindow

    yield 10, "正在加载 CAD 模块…"
    from app.cad.controllers.cad_controller import CadController
    from app.cad.views.occt_viewport import OcctViewport

    yield 35, "正在加载点云工作台…"
    from app.point_cloud.controllers.point_cloud_controller import PointCloudController
    from app.point_cloud.views.point_cloud_viewport import PointCloudViewport

    configure_graphics()
    if startup is None:
        configure_fonts(application)
    qmlRegisterType(OcctViewport, "Cad.Native", 1, 0, "OcctViewport")
    qmlRegisterType(PointCloudViewport, "PointCloud.Native", 1, 0, "PointCloudViewport")

    yield 50, "正在创建默认模型…"
    controller = CadController(application)
    if controller.last_error:
        raise RuntimeError(controller.last_error)
    cloud_controller = PointCloudController(application)
    QQmlEngine.setObjectOwnership(controller, QQmlEngine.ObjectOwnership.CppOwnership)
    QQmlEngine.setObjectOwnership(cloud_controller, QQmlEngine.ObjectOwnership.CppOwnership)

    yield 70, "正在加载主界面…"
    engine = QQmlApplicationEngine()
    engine._workspace_controllers = (controller, cloud_controller)
    documents_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    documents_folder = QUrl.fromLocalFile(documents_path or str(Path.home()))
    properties = {"cad_controller": controller, "cloud_controller": cloud_controller,
                  "documents_folder": documents_folder}
    if startup is not None:
        properties["startup_controller"] = startup
    engine.setInitialProperties(properties)
    qml_path = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        engine.deleteLater()
        raise RuntimeError("主界面加载失败，请查看运行日志。")
    if not isinstance(engine.rootObjects()[0], QQuickWindow):
        engine.deleteLater()
        raise RuntimeError("QML 入口必须创建 Qt Quick 窗口。")
    if startup is not None:
        startup.watch_window(engine.rootObjects()[0])
    yield 90, "正在初始化三维预览…"
    return engine, controller


def create_engine(application):
    """Create the workspace directly for embedding and existing GUI checks."""
    steps = _create_engine_steps(application)
    while True:
        try:
            next(steps)
        except StopIteration as result:
            return result.value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Python CAD workbench")
    parser.add_argument("--screenshot", type=Path, help="Save the rendered workbench to an image, then exit.")
    options = parser.parse_args(argv)
    configure_diagnostics()
    startup = None
    application = None
    try:
        from PyQt6.QtCore import QEvent, QTimer, QtMsgType, qInstallMessageHandler
        from PyQt6.QtGui import QGuiApplication, QIcon

        from app.application.startup_controller import StartupController

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
        configure_fonts(application)
        startup = StartupController(application)
        startup.exit_requested.connect(application.exit)
        startup.start(_create_engine_steps(application, startup))
    except ModuleNotFoundError as error:
        print(f"缺少依赖：{error.name}。请运行 .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    except Exception:
        logging.getLogger(__name__).exception("Could not initialize application startup")
        if startup is not None:
            startup.shutdown()
        if application is not None:
            application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        return 1

    if options.screenshot:
        def capture_window():
            try:
                window = startup.main_engine.rootObjects()[0]
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

        startup.splash_dismissed.connect(lambda: QTimer.singleShot(0, capture_window))
        startup.state_changed.connect(lambda: application.exit(1) if startup.failed else None)
    exit_code = application.exec()
    # Destroy QML windows/renderers while QApplication and its GL services live.
    startup.shutdown()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    logging.getLogger(__name__).info("Workbench exited: code=%s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
