"""Read point clouds using Open3D, retaining valid coordinates and RGB data."""

from pathlib import Path

import numpy as np

from app.point_cloud.models.point_cloud_model import PointCloudRecord


def validate_point_cloud_path(source):
    path = Path(source).expanduser().resolve()
    if path.suffix.lower() not in {".ply", ".pcd", ".xyz"}:
        raise ValueError("请选择 .ply、.pcd 或 .xyz 点云文件。")
    if not path.is_file():
        raise ValueError("点云文件不存在。")
    if path.stat().st_size == 0:
        raise ValueError("点云文件为空。")
    return path


def read_point_cloud(source):
    path = validate_point_cloud_path(source)
    try:
        import open3d as o3d
    except ModuleNotFoundError as error:
        if error.name == "open3d":
            message = "点云依赖 Open3D 未安装，请安装 requirements.txt 中的依赖。"
        else:
            message = "Open3D 依赖缺失，请在当前 Python 环境安装 requirements.txt 中的依赖。"
        raise RuntimeError(f"{message}原始错误：{error}") from error
    except ImportError as error:
        raise RuntimeError(f"Open3D 加载失败：{error}") from error

    cloud = o3d.io.read_point_cloud(str(path), format=path.suffix[1:].lower())
    coordinates = np.asarray(cloud.points)
    if coordinates.ndim != 2 or coordinates.shape[1] != 3 or not len(coordinates):
        raise ValueError("文件中没有可读取的点云坐标。")
    source_count = len(coordinates)
    valid = np.isfinite(coordinates).all(axis=1)
    if not valid.any():
        raise ValueError("点云中没有有效的有限坐标。")
    points = np.array(coordinates[valid], dtype=np.float64, order="C", copy=True)
    colors = None
    if cloud.has_colors():
        candidate = np.asarray(cloud.colors)[valid]
        if np.isfinite(candidate).all():
            colors = np.clip(candidate, 0, 1).astype(np.float32)
            colors.flags.writeable = False
    points.flags.writeable = False
    return PointCloudRecord(path.stem, str(path), points, colors, source_count)
