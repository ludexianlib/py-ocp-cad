"""Qt process/thread adapter for the UI-independent STEP importer."""

import json
import logging
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PyQt6.QtCore import QCoreApplication, QObject, QProcess, QThread, pyqtSignal

from app.models.step_importer import EVENT_PREFIX, load_prepared_model


class PreparedModelLoader(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self._directory = directory

    def run(self):
        try:
            self.loaded.emit(load_prepared_model(self._directory))
        except Exception as error:
            self.failed.emit(str(error))


class StepImportTask(QObject):
    prepared = pyqtSignal(object)
    statistics_ready = pyqtSignal(object)
    phase_changed = pyqtSignal(str)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._directory = TemporaryDirectory(prefix="cad-step-")
        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(Path(__file__).resolve().parents[2]))
        self._process.readyReadStandardOutput.connect(self._read_output)
        self._process.readyReadStandardError.connect(self._read_error_output)
        self._process.errorOccurred.connect(self._process_error)
        self._process.finished.connect(self._process_finished)
        self._loader = None
        self._loader_delivered = False
        self._buffer = b""
        self._error_output = ""
        self._failed = False
        self._got_prepared = False
        self._process_done = False
        self._stopped = False
        self._complete = False
        QCoreApplication.instance().aboutToQuit.connect(self.stop)

    def start(self, source):
        self._process.start(sys.executable, ["-u", "-m", "app.models.step_importer", str(source), self._directory.name])

    def _read_output(self):
        self._buffer += bytes(self._process.readAllStandardOutput())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").strip()
            if not text.startswith(EVENT_PREFIX):
                continue  # OCCT can also write native diagnostic text to stdout.
            try:
                event = json.loads(text[len(EVENT_PREFIX):])
            except ValueError:
                continue
            if self._stopped or self._failed:
                continue
            event_type = event.get("event")
            if event_type == "phase":
                self.phase_changed.emit(event["text"])
            elif event_type == "prepared" and not self._got_prepared:
                self._got_prepared = True
                self.phase_changed.emit("正在显示模型…")
                self._loader = PreparedModelLoader(self._directory.name, self)
                self._loader.loaded.connect(self._model_loaded)
                self._loader.failed.connect(self._model_load_failed)
                self._loader.finished.connect(self._finish_if_idle)
                self._loader.start()
            elif event_type == "statistics":
                self.statistics_ready.emit(event)
            elif event_type == "error":
                self._fail(event.get("message", "STEP 导入失败。"))

    def _model_loaded(self, result):
        self._loader_delivered = True
        if not self._stopped and not self._failed:
            self.prepared.emit(result)
        self._finish_if_idle()

    def _model_load_failed(self, message):
        self._loader_delivered = True
        self._fail(message)
        self._finish_if_idle()

    def _read_error_output(self):
        output = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._error_output = (self._error_output + output)[-4000:]

    def _fail(self, message):
        if not self._failed and not self._stopped:
            self._failed = True
            self.failed.emit(message)

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._process_done = True
            self._fail("无法启动后台导入任务。")
            self._finish_if_idle()

    def _process_finished(self, exit_code, exit_status):
        self._read_output()
        self._read_error_output()
        self._process_done = True
        if not self._got_prepared:
            if self._error_output:
                logging.getLogger(__name__).warning("STEP import worker: %s", self._error_output)
            self._fail("后台导入任务异常退出。" if exit_code else "STEP 文件中没有可导入的模型。")
        elif exit_code:
            logging.getLogger(__name__).warning("STEP statistics worker exited: %s", exit_code)
        self._finish_if_idle()

    def _finish_if_idle(self):
        if self._complete or not self._process_done:
            return
        if self._loader is not None and (self._loader.isRunning() or not self._loader_delivered):
            return
        self._complete = True
        self._cleanup()
        self.finished.emit()

    def _cleanup(self):
        try:
            self._directory.cleanup()
        except OSError:
            logging.getLogger(__name__).warning("Could not remove STEP temporary files", exc_info=True)

    def stop(self):
        self._stopped = True
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(3000)
        if self._loader is not None and self._loader.isRunning():
            self._loader.wait()
        self._cleanup()
