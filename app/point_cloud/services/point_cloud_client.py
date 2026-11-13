"""Small synchronous client for vendor adapters and replay programs."""

import socket

from app.point_cloud.models.point_cloud_protocol import encode_frame


class PointCloudClient:
    def __init__(self, host="127.0.0.1", port=8765, stream_id="lidar_01", timeout=5.0):
        self.host, self.port, self.stream_id = host, port, stream_id
        self.timeout = timeout
        self._socket = None
        self._sequence = 0

    def connect(self):
        if self._socket is None:
            self._socket = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sequence = 0
        return self

    def send_frame(self, *, points, unit, coordinate_frame, colors=None, intensity=None,
                   intensity_range=None, timestamp_ns=None, time_base=None):
        if self._socket is None:
            raise RuntimeError("请先连接点云接收端。")
        packet = encode_frame(points=points, unit=unit, stream_id=self.stream_id, sequence=self._sequence,
                              coordinate_frame=coordinate_frame, colors=colors, intensity=intensity,
                              intensity_range=intensity_range, timestamp_ns=timestamp_ns, time_base=time_base)
        try:
            self._socket.sendall(packet)
        except OSError:
            self.close()
            raise
        self._sequence += 1

    def close(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        self.close()
