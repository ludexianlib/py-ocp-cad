"""Device-independent frames and byte-exact wire compatibility."""

import json
import unittest

import numpy as np

from app.point_cloud.models.point_cloud_frame import PointCloudFrame
from app.point_cloud.models.point_cloud_protocol import (
    MAGIC, MAX_HEADER_BYTES, MAX_PAYLOAD_BYTES, PREFIX, decode_frame, decode_prefix, encode_frame,
)


def unpack_packet(packet):
    header_size, payload_size = decode_prefix(packet[:PREFIX.size])
    header = packet[PREFIX.size:PREFIX.size + header_size]
    payload = packet[PREFIX.size + header_size:]
    assert len(payload) == payload_size
    return header, payload


def make_packet(sequence=0, **options):
    values = dict(points=np.array([[1.25, 2, 3], [4, 5, 6]], dtype=np.float32), unit="mm",
                  stream_id="test", sequence=sequence, coordinate_frame="lidar")
    values.update(options)
    return encode_frame(**values)


class PointCloudProtocolTests(unittest.TestCase):
    def test_minimal_external_packet_uses_declared_types_and_units(self):
        # Handcrafted, independent of our encoder, like a C++ vendor adapter.
        header = {"protocol_version": 1, "stream_id": "external", "sequence": 7,
                  "coordinate_frame": "lidar", "unit": "m", "point_count": 1,
                  "fields": {"points": {"dtype": "<f4", "offset": 0, "shape": [1, 3]}}}
        frame = decode_frame(json.dumps(header).encode(), b"\x00\x00\xa0\x3f\x00\x00\x00\x00\x00\x00\x00\xbf")
        np.testing.assert_array_equal(frame.points, [[1250, 0, -500]])
        self.assertIsNone(frame.colors)
        self.assertIsNone(frame.intensity)
        self.assertEqual(frame.unit, "mm")
        self.assertEqual(frame.source_unit, "m")

    def test_optional_attributes_and_time_round_trip(self):
        colors = np.array([[0, 0, 0], [255, 128, 30]], dtype=np.uint8)
        packet = make_packet(unit="m", colors=colors, intensity=np.array([0.0, 200]),
                             intensity_range=(0, 255), timestamp_ns=1_800_000_000_000_000_001, time_base="unix")
        frame = decode_frame(*unpack_packet(packet))
        np.testing.assert_allclose(frame.colors * 255, colors)
        np.testing.assert_array_equal(frame.intensity, [0, 200])
        self.assertEqual(frame.timestamp_ns, 1_800_000_000_000_000_001)
        self.assertEqual(frame.to_summary()["timestamp_ns"], "1800000000000000001")
        self.assertEqual(frame.intensity_range, (0, 255))

    def test_snapshots_own_arrays_and_filter_attributes_together(self):
        points = np.array([[1, 2, 3], [np.nan, 0, 1], [4, 5, 6]])
        colors = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.uint8)
        intensity = np.array([10, 20, 30])
        frame = PointCloudFrame("test", 0, "lidar", "mm", points, colors, intensity, (0, 100))
        points[:] = 0
        colors[:] = 0
        intensity[:] = 0
        np.testing.assert_array_equal(frame.points, [[1, 2, 3], [4, 5, 6]])
        np.testing.assert_array_equal(frame.intensity, [10, 30])
        np.testing.assert_allclose(frame.colors * 255, [[1, 2, 3], [7, 8, 9]])
        self.assertEqual(frame.to_summary()["removed_count"], 1)
        for array in (frame.points, frame.colors, frame.intensity, *frame.bounds):
            self.assertFalse(array.flags.writeable)

    def test_empty_frame_is_valid_but_all_invalid_nonempty_frame_is_rejected(self):
        frame = decode_frame(*unpack_packet(make_packet(points=np.empty((0, 3)))))
        self.assertEqual(frame.to_summary()["point_count"], 0)
        self.assertEqual(frame.to_summary()["dimensions"], [0, 0, 0])
        with self.assertRaises(ValueError):
            make_packet(points=np.full((1, 3), np.nan))

    def test_attribute_contract_rejects_inconsistent_or_ambiguous_values(self):
        cases = [dict(unit=""), dict(unit="cm"), dict(sequence=True), dict(sequence=-1),
                 dict(colors=np.zeros((2, 3))), dict(colors=np.zeros((1, 3), np.uint8)),
                 dict(intensity=np.ones(2)), dict(intensity=np.ones(1), intensity_range=(0, 10)),
                 dict(intensity=np.array([0, np.inf]), intensity_range=(0, 10)),
                 dict(intensity=np.ones(2), intensity_range=(10, 10)),
                 dict(intensity=np.ones(2), intensity_range=(-1e308, 1e308)),
                 dict(timestamp_ns=1), dict(time_base="unix")]
        for options in cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                make_packet(**options)

    def test_prefix_enforces_limits_before_payload_allocation(self):
        for prefix in (b"bad", PREFIX.pack(b"NOPE", 1, 0), PREFIX.pack(MAGIC, 0, 0),
                       PREFIX.pack(MAGIC, MAX_HEADER_BYTES + 1, 0),
                       PREFIX.pack(MAGIC, 10, MAX_PAYLOAD_BYTES + 1)):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                decode_prefix(prefix)

    def test_malformed_layouts_and_versions_are_rejected(self):
        raw_header, payload = unpack_packet(make_packet(colors=np.zeros((2, 3), np.uint8)))
        for change in (lambda h: h.update(protocol_version=2), lambda h: h.pop("unit"),
                       lambda h: h.update(point_count=1_000_001),
                       lambda h: h["fields"]["points"].update(dtype="<i8"),
                       lambda h: h["fields"]["colors"].update(offset=0),
                       lambda h: h["fields"]["points"].update(shape=[2, 4]),
                       lambda h: h["fields"]["points"].update(offset=-1)):
            header = json.loads(raw_header)
            change(header)
            with self.subTest(header=header), self.assertRaises(ValueError):
                decode_frame(json.dumps(header).encode(), payload)
        for header, data in ((b"{", payload), (b"[]", payload), (raw_header, payload[:-1]), (raw_header, payload + b"x")):
            with self.assertRaises(ValueError):
                decode_frame(header, data)
        with self.assertRaises(ValueError):
            decode_frame(raw_header.decode().encode("utf-16"), payload)


if __name__ == "__main__":
    unittest.main()
