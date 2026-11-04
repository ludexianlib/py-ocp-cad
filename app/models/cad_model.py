"""OCCT geometry and an in-memory model collection. No Qt dependency."""

from dataclasses import dataclass, field
from datetime import datetime
import math
from pathlib import Path

from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS_Shape


@dataclass(slots=True)
class BoxRecord:
    model_id: str
    name: str
    length: float
    width: float
    height: float
    volume: float
    surface_area: float
    created_at: datetime
    shape: TopoDS_Shape = field(repr=False)

    def to_summary(self) -> dict:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "volume": self.volume,
            "surface_area": self.surface_area,
            "dimensions_text": f"{self.length:g} × {self.width:g} × {self.height:g} mm",
            "created_time": self.created_at.strftime("%H:%M"),
        }


class CadModel:
    def __init__(self) -> None:
        self._records: dict[str, BoxRecord] = {}
        self._active_id = ""

    @property
    def records(self) -> list[BoxRecord]:
        return list(reversed(self._records.values()))

    @property
    def active_record(self) -> BoxRecord | None:
        return self._records.get(self._active_id)

    def create_box(self, length: float, width: float, height: float) -> BoxRecord:
        try:
            dimensions = tuple(float(value) for value in (length, width, height))
        except (TypeError, ValueError) as error:
            raise ValueError("请输入有效的模型尺寸。") from error
        if any(not math.isfinite(value) or not 0.01 <= value <= 10000 for value in dimensions):
            raise ValueError("尺寸范围为 0.01–10000 mm，请输入有限数值。")

        length, width, height = dimensions
        shape = BRepPrimAPI_MakeBox(length, width, height).Shape()
        if shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
            raise RuntimeError("模型创建失败，请检查输入尺寸。")
        volume_properties = GProp_GProps()
        area_properties = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, volume_properties)
        BRepGProp.SurfaceProperties_s(shape, area_properties)
        sequence = len(self._records) + 1
        record = BoxRecord(
            model_id=f"box-{sequence:04d}",
            name=f"长方体 {sequence:02d}",
            length=length,
            width=width,
            height=height,
            volume=volume_properties.Mass(),
            surface_area=area_properties.Mass(),
            created_at=datetime.now().astimezone(),
            shape=shape,
        )
        self._records[record.model_id] = record
        self._active_id = record.model_id
        return record

    def select_model(self, model_id: str) -> BoxRecord:
        if model_id not in self._records:
            raise ValueError("找不到这个模型。")
        self._active_id = model_id
        return self._records[model_id]

    def export_step(self, destination: str | Path) -> Path:
        record = self.active_record
        if record is None:
            raise ValueError("请先创建一个模型。")
        path = Path(destination).expanduser()
        if path.suffix.lower() not in {".step", ".stp"}:
            raise ValueError("请选择 .step 或 .stp 文件。")
        if not path.parent.is_dir():
            raise ValueError("保存目录不存在。")
        writer = STEPControl_Writer()
        if writer.Transfer(record.shape, STEPControl_AsIs) != IFSelect_RetDone:
            raise RuntimeError("模型转换失败，未能导出 STEP。")
        if writer.Write(str(path)) != IFSelect_RetDone:
            raise OSError("文件保存失败，请检查目录权限。")
        return path.resolve()
