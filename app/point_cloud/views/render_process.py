"""Own the Open3D GPU engine in an isolated, windowless worker process."""

import traceback

from app.point_cloud.views.open3d_renderer import Open3dRenderer


def render_point_cloud(connection):
    renderer, size, record = None, None, None
    try:
        while True:
            request = connection.recv()
            if request is None:
                break
            try:
                if request["record"] is not None:
                    record = request["record"]
                new_size = request["size"]
                if new_size != size:
                    if renderer is not None:
                        renderer.close()
                        renderer = None
                    renderer = Open3dRenderer(*new_size)
                    size = new_size
                pixels = renderer.render(record, request["camera"], request["point_size"], request["use_rgb"])
                connection.send((True, pixels))
            except Exception as error:
                traceback.print_exc()
                connection.send((False, str(error) or "点云渲染失败。"))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        if renderer is not None:
            renderer.close()
        connection.close()
