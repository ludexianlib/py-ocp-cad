"""Point-cloud camera math, independent of Qt and the rendering backend."""

import math

import numpy as np


class PointCloudCamera:
    def __init__(self):
        self.yaw = math.radians(45)
        self.pitch = math.radians(25)
        self.center = np.zeros(3)
        self.radius = 1.0
        self.distance = 3.0
        self.origin = np.zeros(3)
        self._bounds = None

    def fit(self, record, origin=None):
        if not len(record.points):
            return
        minimum, maximum = record.bounds
        midpoint = minimum / 2 + maximum / 2
        self.origin = midpoint.copy() if origin is None else np.array(origin, dtype=np.float64, copy=True)
        self.radius = max(float(np.linalg.norm(maximum - minimum)) / 2, 1e-6)
        self.distance = self.radius * 2.6
        self.center = midpoint - self.origin
        self.update_bounds(record)

    def update_bounds(self, record):
        if len(record.points):
            self._bounds = tuple(value - self.origin for value in record.bounds)

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

    def view_projection(self, aspect_ratio):
        eye, target, up = self.snapshot()
        forward = (target - eye) / self.distance
        right = np.cross(forward, up)
        right /= np.linalg.norm(right)
        view = np.eye(4)
        view[:3, :3] = (right, np.cross(right, forward), -forward)
        view[:3, 3] = -view[:3, :3] @ eye
        near = max(self.distance * 1e-4, self.radius * 1e-6)
        extent = self.radius
        if self._bounds is not None:
            extent = max(float(np.linalg.norm(value - self.center)) for value in self._bounds)
        far = max(self.distance + 4 * extent, near * 1000)
        scale = 1 / math.tan(math.radians(30))
        projection = np.zeros((4, 4))
        projection[0, 0] = scale / max(aspect_ratio, 1e-6)
        projection[1, 1] = scale
        projection[2, 2] = -(far + near) / (far - near)
        projection[2, 3] = -2 * far * near / (far - near)
        projection[3, 2] = -1
        return projection @ view
