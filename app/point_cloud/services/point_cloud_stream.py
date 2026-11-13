"""Single-source TCP receiver with an owned, bounded latest-frame mailbox."""

import socket
import threading
import time

from app.point_cloud.models.point_cloud_protocol import PREFIX, decode_frame, decode_prefix


class PointCloudStream:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._listener = None
        self._latest = None
        self._status = {"state": "stopped", "error": "", "received": 0, "dropped": 0,
                        "rejected": 0, "session": 0, "host": "", "port": 0}

    def start(self, host="127.0.0.1", port=8765):
        if self._thread is not None:
            raise RuntimeError("接收服务已经启动。")
        if not isinstance(host, str) or not host.strip():
            raise ValueError("请输入监听地址。")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("监听端口必须为 0–65535。")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            reuse_option = getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR)
            listener.setsockopt(socket.SOL_SOCKET, reuse_option, 1)
            listener.bind((host, port))
            listener.listen(1)
            listener.settimeout(0.2)
        except BaseException:
            listener.close()
            raise
        self._stop_event.clear()
        self._listener = listener
        with self._lock:
            self._latest = None
            self._status = {"state": "listening", "error": "", "received": 0, "dropped": 0,
                            "rejected": 0, "session": 0, "host": host, "port": listener.getsockname()[1]}
        self._thread = threading.Thread(target=self._run, name="point-cloud-stream", daemon=True)
        self._thread.start()

    def snapshot(self):
        with self._lock:
            return dict(self._status)

    def take_latest(self):
        with self._lock:
            result, self._latest = self._latest, None
            return result

    def _update_status(self, **values):
        with self._lock:
            self._status.update(values)

    def _read_exact(self, connection, size, *, idle_allowed=False):
        data = bytearray(size)
        view, offset = memoryview(data), 0
        deadline = None if idle_allowed else time.monotonic() + 10
        while offset < size:
            if self._stop_event.is_set():
                raise InterruptedError()
            if deadline is not None and time.monotonic() > deadline:
                raise ValueError("点云报文接收超时。")
            try:
                count = connection.recv_into(view[offset:])
            except socket.timeout:
                continue
            if count == 0:
                if offset or not idle_allowed:
                    raise ValueError("连接中断，点云报文不完整。")
                raise EOFError()
            offset += count
            if deadline is None:
                deadline = time.monotonic() + 10
        return data

    def _receive(self, connection):
        stream_key, last_sequence = None, -1
        while not self._stop_event.is_set():
            prefix = self._read_exact(connection, PREFIX.size, idle_allowed=True)
            header_size, payload_size = decode_prefix(prefix)
            header = self._read_exact(connection, header_size)
            payload = self._read_exact(connection, payload_size)
            try:
                frame = decode_frame(header, payload)
                key = (frame.stream_id, frame.coordinate_frame)
                if stream_key is not None and key != stream_key:
                    raise ValueError("同一连接不能更换数据流或坐标系，请重新连接。")
                if frame.sequence <= last_sequence:
                    raise ValueError("帧序号必须递增。")
            except (ValueError, TypeError, OverflowError) as error:
                with self._lock:
                    self._status["rejected"] += 1
                    self._status["error"] = str(error)
                continue
            stream_key, last_sequence = key, frame.sequence
            with self._lock:
                self._status["received"] += 1
                if self._latest is not None:
                    self._status["dropped"] += 1
                self._latest = (self._status["session"], frame)

    def _run(self):
        try:
            while not self._stop_event.is_set():
                try:
                    connection, _ = self._listener.accept()
                except socket.timeout:
                    continue
                with connection:
                    connection.settimeout(0.2)
                    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    with self._lock:
                        self._status["state"] = "connected"
                        self._status["session"] += 1
                        self._status["error"] = ""
                    try:
                        self._receive(connection)
                    except EOFError:
                        pass
                    except InterruptedError:
                        break
                    except (OSError, ValueError) as error:
                        with self._lock:
                            self._status["error"] = str(error)
                            self._status["rejected"] += 1
                self._update_status(state="listening")
        except OSError as error:
            if not self._stop_event.is_set():
                self._update_status(state="failed", error=str(error))
        finally:
            self._listener.close()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self._listener = None
        with self._lock:
            self._latest = None
            self._status["state"] = "stopped"
