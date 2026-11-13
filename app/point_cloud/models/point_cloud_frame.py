"""Validated, owned point-cloud snapshots. No UI or device SDK dependencies."""

from dataclasses import dataclass, field

import numpy as np


MAX_POINTS = 1_000_000
UNIT_SCALES = {"mm": 1.0, "m": 1000.0}


def unit_scale(unit):
    if not isinstance(unit, str) or unit not in UNIT_SCALES:
        raise ValueError("请明确指定坐标单位 mm 或 m。")
    return UNIT_SCALES[unit]


def validate_integer(value, name, maximum=2**63 - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} 必须是 0–{maximum} 的整数。")


@dataclass(frozen=True, slots=True, eq=False)
class PointCloudFrame:
    stream_id: str
    sequence: int
    coordinate_frame: str
    unit: str
    points: np.ndarray = field(repr=False)
    colors: np.ndarray | None = field(default=None, repr=False)
    intensity: np.ndarray | None = field(default=None, repr=False)
    intensity_range: tuple | None = None
    timestamp_ns: int | None = None
    time_base: str | None = None
    protocol_version: int = 1
    source_unit: str = field(init=False)
    source_count: int = field(init=False)
    bounds: tuple = field(init=False, repr=False)

    def __post_init__(self):
        if type(self.protocol_version) is not int or self.protocol_version != 1:
            raise ValueError("不支持的点云协议版本。")
        for name in ("stream_id", "coordinate_frame"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError(f"{name} 必须是 1–128 字符的非空名称。")
        validate_integer(self.sequence, "sequence")
        if self.timestamp_ns is not None:
            validate_integer(self.timestamp_ns, "timestamp_ns")
            if self.time_base not in ("unix", "device", "monotonic"):
                raise ValueError("采集时间必须声明 time_base：unix、device 或 monotonic。")
        elif self.time_base is not None:
            raise ValueError("time_base 需要同时提供 timestamp_ns。")
        scale = unit_scale(self.unit)
        raw_points = np.asarray(self.points)
        if raw_points.ndim != 2 or raw_points.shape[1] != 3 or raw_points.dtype.kind not in "fiu":
            raise ValueError("points 必须是 N×3 数值数组。")
        count = len(raw_points)
        if count > MAX_POINTS:
            raise ValueError(f"每帧最多 {MAX_POINTS} 个点。")
        with np.errstate(over="ignore", invalid="ignore"):
            points = np.array(raw_points, dtype=np.float64, order="C", copy=True) * scale
        valid = np.isfinite(points).all(axis=1)
        if count and not valid.any():
            raise ValueError("非空点云中没有有效坐标。")
        colors = None
        if self.colors is not None:
            raw_colors = np.asarray(self.colors)
            if raw_colors.shape != (count, 3) or raw_colors.dtype != np.uint8:
                raise ValueError("colors 必须是与点数相同的 N×3 uint8 RGB 数组。")
            colors = raw_colors[valid].astype(np.float32) / 255.0
        intensity = None
        value_range = None
        if self.intensity is not None:
            raw_intensity = np.asarray(self.intensity)
            if raw_intensity.shape != (count,) or raw_intensity.dtype.kind not in "fiu":
                raise ValueError("intensity 必须是与点数相同的一维数值数组。")
            if not np.isfinite(raw_intensity).all():
                raise ValueError("intensity 必须全部为有限值。")
            try:
                value_range = tuple(float(value) for value in self.intensity_range)
            except (TypeError, ValueError) as error:
                raise ValueError("有强度时必须提供 intensity_range。") from error
            if (len(value_range) != 2 or not np.isfinite(value_range).all()
                    or value_range[0] >= value_range[1] or not np.isfinite(value_range[1] - value_range[0])):
                raise ValueError("intensity_range 必须是有限且递增的两个值。")
            intensity = np.array(raw_intensity[valid], dtype=np.float64, copy=True)
        elif self.intensity_range is not None:
            raise ValueError("intensity_range 需要同时提供 intensity。")
        points = points[valid]
        bounds = (points.min(axis=0), points.max(axis=0)) if len(points) else (np.zeros(3), np.zeros(3))
        for array in (points, colors, intensity, *bounds):
            if array is not None:
                array.flags.writeable = False
        for name, value in (("points", points), ("colors", colors), ("intensity", intensity),
                            ("intensity_range", value_range), ("bounds", bounds),
                            ("source_count", count), ("source_unit", self.unit), ("unit", "mm")):
            object.__setattr__(self, name, value)

    def to_summary(self):
        minimum, maximum = self.bounds
        return {
            "name": self.stream_id, "source_path": "", "point_count": len(self.points),
            "removed_count": self.source_count - len(self.points),
            "has_colors": self.colors is not None, "has_intensity": self.intensity is not None,
            "dimensions": (maximum - minimum).tolist(), "minimum": minimum.tolist(),
            "maximum": maximum.tolist(), "unit": self.unit, "source_unit": self.source_unit,
            "stream_id": self.stream_id, "coordinate_frame": self.coordinate_frame,
            # Strings preserve 64-bit values when exposed to QML/JavaScript.
            "sequence": str(self.sequence),
            "timestamp_ns": "" if self.timestamp_ns is None else str(self.timestamp_ns),
            "time_base": self.time_base or "",
        }
