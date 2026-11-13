"""Send a moving torus without physical lidar hardware."""

import argparse
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.point_cloud.services.point_cloud_client import PointCloudClient


def main():
    parser = argparse.ArgumentParser(description="点云协议 v1 示例发送器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--mode", choices=("xyz", "rgb", "intensity"), default="rgb")
    parser.add_argument("--unit", choices=("mm", "m"), default="mm")
    parser.add_argument("--fps", type=float, default=10)
    parser.add_argument("--frames", type=int, default=0, help="0 表示持续发送，Ctrl+C 停止")
    options = parser.parse_args()
    if not 0 < options.fps <= 120 or options.frames < 0:
        parser.error("fps 必须在 0–120 之间，frames 不能为负数。")
    angle, ring = np.meshgrid(np.linspace(0, 2 * np.pi, 240), np.linspace(0, 2 * np.pi, 70))
    points = np.column_stack(((1000 + 300 * np.cos(ring)).ravel() * np.cos(angle).ravel(),
                              (1000 + 300 * np.cos(ring)).ravel() * np.sin(angle).ravel(),
                              300 * np.sin(ring).ravel()))
    colors = np.column_stack(((np.cos(angle).ravel() + 1) * 127.5,
                              (np.sin(angle).ravel() + 1) * 127.5,
                              (np.sin(ring).ravel() + 1) * 127.5)).astype(np.uint8)
    intensity = ((np.sin(ring).ravel() + 1) * 127.5).astype(np.float32)
    try:
        with PointCloudClient(options.host, options.port, stream_id="demo_lidar") as client:
            print(f"Connected to {options.host}:{options.port}; mode={options.mode}, unit={options.unit}", flush=True)
            index, deadline = 0, time.monotonic()
            while options.frames == 0 or index < options.frames:
                moved = points.copy()
                moved[:, 0] += np.sin(index * 0.08) * 200
                if options.unit == "m":
                    moved /= 1000
                client.send_frame(points=moved.astype(np.float32), unit=options.unit, coordinate_frame="lidar",
                                  colors=colors if options.mode == "rgb" else None,
                                  intensity=intensity if options.mode == "intensity" else None,
                                  intensity_range=(0, 255) if options.mode == "intensity" else None,
                                  timestamp_ns=time.time_ns(), time_base="unix")
                index += 1
                deadline += 1 / options.fps
                time.sleep(max(0, deadline - time.monotonic()))
    except KeyboardInterrupt:
        pass
    except OSError as error:
        parser.exit(1, f"连接或发送失败：{error}\n请先在工作台中启动实时点云接收。\n")


if __name__ == "__main__":
    main()
