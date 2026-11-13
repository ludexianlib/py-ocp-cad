"""Loopback integration tests; no Qt, Open3D, GPU or physical lidar required."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest

import numpy as np

from app.point_cloud.models.point_cloud_protocol import PREFIX, MAGIC
from app.point_cloud.services.point_cloud_client import PointCloudClient
from app.point_cloud.services.point_cloud_stream import PointCloudStream
from tests.test_point_cloud_protocol import make_packet, unpack_packet


class PointCloudStreamTests(unittest.TestCase):
    def setUp(self):
        self.stream = PointCloudStream()
        self.stream.start(port=0)
        self.port = self.stream.snapshot()["port"]
        self.addCleanup(self.stream.stop)

    def wait_until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            self.assertLess(time.monotonic(), deadline, self.stream.snapshot())
            time.sleep(0.005)

    def connect(self):
        connection = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        self.addCleanup(connection.close)
        return connection

    def test_fragmented_and_coalesced_messages_use_only_latest_mailbox(self):
        connection = self.connect()
        packet = make_packet(0)
        for index in range(0, len(packet), 7):
            connection.sendall(packet[index:index + 7])
        connection.sendall(make_packet(1) + make_packet(2))
        self.wait_until(lambda: self.stream.snapshot()["received"] == 3)
        session, frame = self.stream.take_latest()
        self.assertEqual(session, 1)
        self.assertEqual(frame.sequence, 2)
        self.assertEqual(self.stream.snapshot()["dropped"], 2)
        self.assertIsNone(self.stream.take_latest())

    def test_invalid_frame_and_repeated_sequence_preserve_previous_mailbox(self):
        connection = self.connect()
        connection.sendall(make_packet(3))
        header, payload = unpack_packet(make_packet(4))
        header = json.loads(header)
        header["unit"] = "unknown"
        header = json.dumps(header).encode()
        connection.sendall(PREFIX.pack(MAGIC, len(header), len(payload)) + header + payload)
        connection.sendall(make_packet(2))
        self.wait_until(lambda: self.stream.snapshot()["rejected"] == 2)
        self.assertEqual(self.stream.take_latest()[1].sequence, 3)
        connection.sendall(make_packet(5))
        self.wait_until(lambda: self.stream.snapshot()["received"] == 2)
        self.assertEqual(self.stream.take_latest()[1].sequence, 5)

    def test_disconnect_and_reconnect_reset_session_sequence(self):
        connection = self.connect()
        connection.sendall(make_packet(10))
        self.wait_until(lambda: self.stream.snapshot()["received"] == 1)
        connection.close()
        self.wait_until(lambda: self.stream.snapshot()["state"] == "listening")
        with PointCloudClient(port=self.port) as client:
            client.send_frame(points=np.array([[0, 0, 1.25]]), unit="m", coordinate_frame="lidar")
            self.wait_until(lambda: self.stream.snapshot()["received"] == 2)
        session, frame = self.stream.take_latest()
        self.assertEqual(session, 2)
        self.assertEqual(frame.sequence, 0)
        np.testing.assert_array_equal(frame.points, [[0, 0, 1250]])

    def test_broken_prefix_disconnects_client_but_listener_survives(self):
        connection = self.connect()
        connection.sendall(PREFIX.pack(b"oops", 4, 0))
        self.wait_until(lambda: self.stream.snapshot()["rejected"] == 1)
        self.wait_until(lambda: self.stream.snapshot()["state"] == "listening")
        with PointCloudClient(port=self.port) as client:
            client.send_frame(points=np.empty((0, 3)), unit="mm", coordinate_frame="lidar")
            self.wait_until(lambda: self.stream.snapshot()["received"] == 1)
        self.assertEqual(len(self.stream.take_latest()[1].points), 0)

    def test_stop_interrupts_partial_payload_and_releases_port(self):
        connection = self.connect()
        connection.sendall(make_packet()[:-5])
        self.wait_until(lambda: self.stream.snapshot()["state"] == "connected")
        started = time.monotonic()
        self.stream.stop()
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(self.stream.snapshot()["state"], "stopped")
        self.assertIsNone(self.stream.take_latest())
        self.stream.start(port=self.port)
        self.assertEqual(self.stream.snapshot()["state"], "listening")

    def test_documented_example_sends_all_three_modes(self):
        root = Path(__file__).resolve().parents[1]
        for index, mode in enumerate(("xyz", "rgb", "intensity"), start=1):
            with self.subTest(mode=mode):
                completed = subprocess.run(
                    [sys.executable, str(root / "examples" / "point_cloud_sender.py"),
                     "--port", str(self.port), "--mode", mode, "--unit", "m", "--frames", "2", "--fps", "120"],
                    cwd=root, capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.wait_until(lambda: self.stream.snapshot()["received"] == index * 2)
                _, frame = self.stream.take_latest()
                self.assertEqual(frame.sequence, 1)
                self.assertEqual(frame.source_unit, "m")
                self.assertEqual(frame.colors is not None, mode == "rgb")
                self.assertEqual(frame.intensity is not None, mode == "intensity")
                self.assertGreater(frame.to_summary()["dimensions"][0], 2500)

    def test_disconnect_between_prefix_and_header_is_rejected(self):
        connection = self.connect()
        connection.sendall(PREFIX.pack(MAGIC, 100, 0))
        connection.close()
        self.wait_until(lambda: self.stream.snapshot()["rejected"] == 1)
        self.assertIn("不完整", self.stream.snapshot()["error"])


if __name__ == "__main__":
    unittest.main()
