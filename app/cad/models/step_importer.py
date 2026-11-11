"""STEP import and display preparation, without a Qt dependency.

Run as a module in a separate process. Small JSON events accompany binary BREP
results so expensive STEP conversion and meshing never run in the GUI process.
"""

import json
import math
import os
from pathlib import Path
import sys

EVENT_PREFIX = "CAD_IMPORT:"


def maximum_step_bytes() -> int:
    try:
        limit_mb = int(os.environ.get("CAD_STEP_MAX_MB", "100"))
    except ValueError as error:
        raise ValueError("CAD_STEP_MAX_MB 必须是正整数。") from error
    if limit_mb <= 0:
        raise ValueError("CAD_STEP_MAX_MB 必须是正整数。")
    return limit_mb * 1024 * 1024


def validate_step_path(source: str | Path) -> Path:
    path = Path(source).expanduser().resolve()
    if path.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("请选择 .step 或 .stp 文件。")
    if not path.is_file():
        raise ValueError("STEP 文件不存在。")
    size = path.stat().st_size
    if size == 0:
        raise ValueError("STEP 文件为空。")
    limit = maximum_step_bytes()
    if size > limit:
        raise ValueError(f"STEP 文件超过 {limit // (1024 * 1024)} MB 导入上限。")
    return path


def import_step(source: str | Path, directory: str | Path, notify) -> None:
    from OCP.BinTools import BinTools
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from app.cad.models.model_appearance import map_display_colors, read_step_model
    from app.cad.models.entity_tree import map_display_entities

    path = validate_step_path(source)
    directory = Path(directory)
    shape, appearance, entities = read_step_model(path, notify, include_entities=True)

    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    if bounds.IsVoid() or bounds.IsOpen():
        raise ValueError("模型没有有效的有限尺寸。")
    # OCP 8.0.1 does not bind the Bnd_Box::Limits value returned by Get().
    x_min, y_min, z_min = bounds.CornerMin().Coord()
    x_max, y_max, z_max = bounds.CornerMax().Coord()
    dimensions = (x_max - x_min, y_max - y_min, z_max - z_min)
    if not all(math.isfinite(value) and value >= 0 for value in dimensions):
        raise ValueError("模型尺寸无效。")

    notify("phase", text="正在准备三维显示…")
    copier = BRepBuilderAPI_Copy(shape, True, False)
    display_shape = copier.Shape()
    map_display_colors(shape, display_shape, copier, appearance)
    entities = map_display_entities(entities, shape, display_shape, copier)
    del copier
    diagonal = math.sqrt(sum(value * value for value in dimensions))
    deflection = max(0.01, min(0.5, diagonal * 0.001))
    mesher = BRepMesh_IncrementalMesh(display_shape, deflection, False, 0.35, True)
    if not mesher.IsDone():
        raise RuntimeError("模型显示网格生成失败。")
    if not BinTools.Write_s(shape, str(directory / "model.brep")):
        raise OSError("无法保存模型中间数据。")
    if not BinTools.Write_s(display_shape, str(directory / "display.brep")):
        raise OSError("无法保存显示中间数据。")
    metadata = {"name": path.stem, "source_path": str(path), "dimensions": dimensions,
                "appearance": appearance, "entities": entities}
    (directory / "result.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    notify("prepared")


def load_prepared_model(directory: str | Path) -> dict:
    """Read the compact handoff files in a background thread."""
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape
    from app.cad.models.model_appearance import appearance_targets
    from app.cad.models.entity_tree import load_entity_tree

    directory = Path(directory)
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    for key, filename in (("shape", "model.brep"), ("display_shape", "display.brep")):
        shape = TopoDS_Shape()
        if not BinTools.Read_s(shape, str(directory / filename)) or shape.IsNull():
            raise RuntimeError("无法接收导入的模型数据。")
        result[key] = shape
    # Validate both index spaces after BREP deserialization, before adoption.
    for key, for_display in (("shape", False), ("display_shape", True)):
        for _ in appearance_targets(result[key], result.get("appearance"), for_display):
            pass
    result["entities"] = load_entity_tree(result.get("entities"), result["shape"], result["display_shape"],
                                          result["name"]).metadata
    return result


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    def notify(event, **values):
        print(EVENT_PREFIX + json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)

    try:
        import_step(sys.argv[1], sys.argv[2], notify)
    except Exception as error:
        notify("error", message=str(error) or "STEP 导入失败。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
