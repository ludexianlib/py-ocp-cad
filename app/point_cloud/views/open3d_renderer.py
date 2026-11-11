"""Open3D offscreen backend. All renderer operations stay on its owner thread."""

import math

import numpy as np


class PointCloudCamera:
    def __init__(self):
        self.yaw = math.radians(45)
        self.pitch = math.radians(25)
        self.center = np.zeros(3)
        self.radius = 1.0
        self.distance = 3.0

    def fit(self, record):
        minimum, maximum = record.bounds
        self.radius = max(float(np.linalg.norm(maximum - minimum)) / 2, 1e-6)
        self.distance = self.radius * 2.6
        self.center = np.zeros(3)

    def orbit(self, delta_x, delta_y):
        self.yaw -= delta_x * 0.008
        self.pitch = float(np.clip(self.pitch + delta_y * 0.008, -1.55, 1.55))

    def zoom(self, wheel_delta):
        self.distance = float(np.clip(
            self.distance * math.exp(-float(np.clip(wheel_delta, -1200, 1200)) * 0.001),
            self.radius * 0.05, self.radius * 1000,
        ))

    def pan(self, delta_x, delta_y, viewport_height):
        eye, target, up = self.snapshot()
        direction = target - eye
        direction /= np.linalg.norm(direction)
        right = np.cross(direction, up)
        right /= np.linalg.norm(right)
        camera_up = np.cross(right, direction)
        scale = 2 * self.distance * math.tan(math.radians(30)) / max(viewport_height, 1)
        self.center += (-delta_x * right + delta_y * camera_up) * scale

    def snapshot(self):
        direction = np.array([
            math.cos(self.pitch) * math.cos(self.yaw),
            math.cos(self.pitch) * math.sin(self.yaw),
            math.sin(self.pitch),
        ])
        return self.center + direction * self.distance, self.center.copy(), np.array([0.0, 0.0, 1.0])


class Open3dRenderer:
    def __init__(self, width, height):
        import open3d as o3d

        self._o3d = o3d
        self._renderer = o3d.visualization.rendering.OffscreenRenderer(width, height)
        self._renderer.scene.set_background([0.94, 0.93, 0.98, 1.0])
        self._renderer.scene.view.set_post_processing(False)
        self._record = None
        self._use_rgb = None

    def render(self, record, camera, point_size, use_rgb):
        if record is not self._record or use_rgb != self._use_rgb:
            geometry = self._o3d.geometry.PointCloud()
            minimum, maximum = record.bounds
            # Center display coordinates to preserve GPU precision for large offsets.
            geometry.points = self._o3d.utility.Vector3dVector(record.points - (minimum / 2 + maximum / 2))
            if use_rgb and record.colors is not None:
                geometry.colors = self._o3d.utility.Vector3dVector(record.colors.astype(np.float64))
            else:
                geometry.paint_uniform_color([0.40, 0.30, 0.80])
            self._renderer.scene.clear_geometry()
            self._renderer.scene.add_geometry("point_cloud", geometry, self._material(point_size))
            self._record, self._use_rgb = record, use_rgb
        else:
            self._renderer.scene.modify_geometry_material("point_cloud", self._material(point_size))
        eye, target, up = camera
        distance = float(np.linalg.norm(eye - target))
        self._renderer.setup_camera(60.0, target, eye, up, max(distance * 0.0001, 1e-9), distance * 100 + 1)
        return np.asarray(self._renderer.render_to_image())

    def _material(self, point_size):
        material = self._o3d.visualization.rendering.MaterialRecord()
        material.shader = "defaultUnlit"
        material.point_size = float(point_size)
        return material

    def close(self):
        if self._renderer is not None:
            self._renderer.scene.clear_geometry()
        self._record = None
        self._renderer = None
