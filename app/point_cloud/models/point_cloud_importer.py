"""Read clouds in a clean process and exchange NumPy data without native objects."""

import json
from pathlib import Path

import numpy as np

from app.point_cloud.models.point_cloud_io import read_point_cloud
from app.point_cloud.models.point_cloud_model import PointCloudRecord


def save_prepared_cloud(record, directory):
    directory = Path(directory)
    np.save(directory / "points.npy", record.points, allow_pickle=False)
    if record.colors is not None:
        np.save(directory / "colors.npy", record.colors, allow_pickle=False)
    metadata = {
        "name": record.name,
        "source_path": record.source_path,
        "source_count": record.source_count,
        "has_colors": record.colors is not None,
        "unit": record.unit,
        "source_unit": record.source_unit,
    }
    (directory / "cloud.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")


def load_prepared_cloud(directory):
    """Restore immutable arrays without importing Open3D in the host process."""
    directory = Path(directory)
    metadata = json.loads((directory / "cloud.json").read_text(encoding="utf-8"))
    points = np.load(directory / "points.npy", allow_pickle=False)
    colors = np.load(directory / "colors.npy", allow_pickle=False) if metadata["has_colors"] else None
    points.flags.writeable = False
    if colors is not None:
        colors.flags.writeable = False
    return PointCloudRecord(metadata["name"], metadata["source_path"], points, colors, metadata["source_count"],
                            unit=metadata["unit"], source_unit=metadata["source_unit"])


def main(argv=None):
    import argparse
    import faulthandler
    import traceback

    parser = argparse.ArgumentParser(description="Isolated point cloud reader")
    parser.add_argument("--unit", required=True, choices=("mm", "m"))
    parser.add_argument("source", type=Path)
    parser.add_argument("directory", type=Path)
    options = parser.parse_args(argv)
    faulthandler.enable()
    try:
        record = read_point_cloud(options.source, options.unit)
        save_prepared_cloud(record, options.directory)
    except Exception as error:
        traceback.print_exc()
        message = str(error) or "点云读取失败。"
        (options.directory / "error.json").write_text(json.dumps({"message": message}, ensure_ascii=False), encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
