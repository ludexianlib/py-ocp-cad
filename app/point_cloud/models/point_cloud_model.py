"""Immutable point cloud data and current document, independent of Qt/rendering."""

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True, slots=True, eq=False)
class PointCloudRecord:
    name: str
    source_path: str
    points: np.ndarray = field(repr=False)
    colors: np.ndarray | None = field(default=None, repr=False)
    source_count: int = 0
    bounds: tuple = field(init=False, repr=False)

    def __post_init__(self):
        minimum, maximum = self.points.min(axis=0), self.points.max(axis=0)
        minimum.flags.writeable = maximum.flags.writeable = False
        object.__setattr__(self, "bounds", (minimum, maximum))

    def to_summary(self):
        minimum, maximum = self.bounds
        return {
            "name": self.name,
            "source_path": self.source_path,
            "point_count": len(self.points),
            "removed_count": self.source_count - len(self.points),
            "has_colors": self.colors is not None,
            "dimensions": (maximum - minimum).tolist(),
            "minimum": minimum.tolist(),
            "maximum": maximum.tolist(),
        }


class PointCloudModel:
    def __init__(self):
        self.active_record = None

    def adopt(self, record: PointCloudRecord):
        self.active_record = record
