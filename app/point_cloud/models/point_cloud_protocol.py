"""Version 1 TCP framing: little-endian prefix, UTF-8 JSON, binary arrays."""

import json
import struct

import numpy as np

from app.point_cloud.models.point_cloud_frame import MAX_POINTS, PointCloudFrame, validate_integer


PREFIX = struct.Struct("<4sII")
MAGIC = b"PCV1"
MAX_HEADER_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024


def decode_prefix(data):
    if len(data) != PREFIX.size:
        raise ValueError("点云报文前缀长度错误。")
    magic, header_size, payload_size = PREFIX.unpack(data)
    if magic != MAGIC or not 1 <= header_size <= MAX_HEADER_BYTES or payload_size > MAX_PAYLOAD_BYTES:
        raise ValueError("点云报文标识或长度无效。")
    return header_size, payload_size


def decode_frame(header_bytes, payload):
    if not 1 <= len(header_bytes) <= MAX_HEADER_BYTES or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("点云报文超过长度限制。")
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValueError("点云帧头不是有效 UTF-8 JSON。") from error
    if not isinstance(header, dict):
        raise ValueError("点云帧头必须是对象。")
    required = {"protocol_version", "stream_id", "sequence", "coordinate_frame", "unit", "point_count", "fields"}
    if not required <= header.keys():
        raise ValueError("点云帧头缺少必填字段。")
    count = header["point_count"]
    validate_integer(count, "point_count", MAX_POINTS)
    fields = header["fields"]
    if not isinstance(fields, dict) or "points" not in fields or not fields.keys() <= {"points", "colors", "intensity"}:
        raise ValueError("fields 必须包含 points，第一版只支持 points、colors、intensity。")
    arrays, spans = {}, []
    for name, descriptor in fields.items():
        if not isinstance(descriptor, dict) or not {"dtype", "shape", "offset"} <= descriptor.keys():
            raise ValueError("字段描述缺少 dtype、shape 或 offset。")
        shape = [count, 3] if name in ("points", "colors") else [count]
        if descriptor["shape"] != shape or any(type(value) is not int for value in descriptor["shape"]):
            raise ValueError(f"{name} 数组形状与点数不一致。")
        dtype_name = descriptor["dtype"]
        allowed = ("|u1",) if name == "colors" else ("<f4", "<f8")
        if dtype_name not in allowed:
            raise ValueError(f"{name} 数据类型无效。")
        offset = descriptor["offset"]
        validate_integer(offset, "offset", MAX_PAYLOAD_BYTES)
        dtype = np.dtype(dtype_name)
        size = count * (3 if name in ("points", "colors") else 1) * dtype.itemsize
        if offset + size > len(payload):
            raise ValueError("字段超出二进制数据边界。")
        if size:
            spans.append((offset, offset + size))
        arrays[name] = np.frombuffer(payload, dtype=dtype, count=size // dtype.itemsize, offset=offset).reshape(shape)
    end = 0
    for start, stop in sorted(spans):
        if start != end:
            raise ValueError("二进制字段不能重叠或留空隙。")
        end = stop
    if end != len(payload):
        raise ValueError("二进制数据长度与字段描述不一致。")
    return PointCloudFrame(
        **{name: header[name] for name in required - {"point_count", "fields"}},
        **arrays, **{name: header.get(name) for name in ("intensity_range", "timestamp_ns", "time_base")},
    )


def encode_frame(*, points, unit, stream_id, sequence, coordinate_frame,
                 colors=None, intensity=None, intensity_range=None, timestamp_ns=None, time_base=None):
    """Validate and serialize one owned snapshot; source coordinates retain their unit."""
    frame = PointCloudFrame(stream_id, sequence, coordinate_frame, unit, points, colors,
                            intensity, intensity_range, timestamp_ns, time_base)
    scale = 1000.0 if unit == "m" else 1.0
    point_dtype = "<f8" if np.asarray(points).dtype.itemsize > 4 else "<f4"
    arrays = {"points": np.asarray(frame.points / scale, dtype=point_dtype)}
    if frame.colors is not None:
        arrays["colors"] = np.rint(frame.colors * 255).astype(np.uint8)
    if frame.intensity is not None:
        arrays["intensity"] = np.asarray(frame.intensity, dtype="<f8")
    fields, chunks, offset = {}, [], 0
    for name, array in arrays.items():
        fields[name] = {"dtype": array.dtype.str, "shape": list(array.shape), "offset": offset}
        chunks.append(array.tobytes(order="C"))
        offset += array.nbytes
    header = {"protocol_version": 1, "stream_id": stream_id, "sequence": sequence,
              "coordinate_frame": coordinate_frame, "unit": unit, "point_count": len(frame.points), "fields": fields}
    if intensity is not None:
        header["intensity_range"] = frame.intensity_range
    if timestamp_ns is not None:
        header.update(timestamp_ns=timestamp_ns, time_base=time_base)
    header_bytes = json.dumps(header, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    decode_prefix(PREFIX.pack(MAGIC, len(header_bytes), offset))
    return PREFIX.pack(MAGIC, len(header_bytes), offset) + header_bytes + b"".join(chunks)
