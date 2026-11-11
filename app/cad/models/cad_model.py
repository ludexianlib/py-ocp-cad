"""OCCT geometry and the current in-memory model. No Qt dependency."""

from dataclasses import dataclass, field
import math
from pathlib import Path

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Transform,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepLib import BRepLib
from OCP.BRepOffsetAPI import (
    BRepOffsetAPI_MakeThickSolid,
    BRepOffsetAPI_ThruSections,
)
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakePrism,
)
from OCP.Bnd import Bnd_Box
from OCP.GC import (
    GC_MakeArcOfCircle,
    GC_MakeSegment,
    GC_MakeSegment2d,
)
from OCP.Geom import Geom_CylindricalSurface, Geom_Plane
from OCP.Geom2d import Geom2d_Ellipse, Geom2d_TrimmedCurve
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.collections import List_TopoDS_Shape
from OCP.gp import (
    gp_Ax1,
    gp_Ax2,
    gp_Ax2d,
    gp_Ax3,
    gp_Dir,
    gp_Dir2d,
    gp_Pnt,
    gp_Pnt2d,
    gp_Trsf,
    gp_Vec,
)

from app.cad.models.entity_tree import EntityTree, load_entity_tree


@dataclass(slots=True)
class ModelRecord:
    model_id: str
    name: str
    length: float
    width: float
    height: float
    shape: TopoDS_Shape = field(repr=False)
    display_shape: TopoDS_Shape | None = field(default=None, repr=False)
    source_path: str = ""
    appearance: dict | None = field(default=None, repr=False)
    entities: EntityTree | None = field(default=None, repr=False)

    def to_summary(self) -> dict:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "is_imported": bool(self.source_path),
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "dimensions_text": f"{self.length:g} × {self.width:g} × {self.height:g} mm",
        }


class CadModel:
    def __init__(self) -> None:
        self._active_record: ModelRecord | None = None
        self._sequence = 0

    @property
    def active_record(self) -> ModelRecord | None:
        return self._active_record

    def restore_model(self, record: ModelRecord | None) -> None:
        """Restore the previous model after a failed import or display."""
        self._active_record = record

    def create_box(self, length: float, width: float, height: float) -> ModelRecord:
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
        self._sequence += 1
        sequence = self._sequence
        record = ModelRecord(
            model_id=f"box-{sequence:04d}",
            name=f"长方体 {sequence:02d}",
            length=length,
            width=width,
            height=height,
            shape=shape,
        )
        record.entities = load_entity_tree(None, shape, name=record.name)
        self._active_record = record
        return record

    @staticmethod
    def make_bottle(width: float, height: float, thickness: float) -> TopoDS_Shape:
        """Build the OCCT tutorial bottle, including its hollow body and threading."""
        try:
            width, height, thickness = (float(width), float(height), float(thickness))
        except (TypeError, ValueError) as error:
            raise ValueError("请输入有效的瓶子尺寸。") from error
        if not all(math.isfinite(value) and value > 0 for value in (width, height, thickness)):
            raise ValueError("请输入有效的瓶子尺寸。")

        # 1. 定义半个瓶身轮廓的支撑点
        point_1 = gp_Pnt(-width / 2, 0, 0)  # 底部左侧
        point_2 = gp_Pnt(-width / 2, -thickness / 4, 0)  # 底部内侧
        point_3 = gp_Pnt(0, -thickness / 2, 0)
        point_4 = gp_Pnt(width / 2, -thickness / 4, 0)  # 底部内侧
        point_5 = gp_Pnt(width / 2, 0, 0)

        # 2. 创建圆弧和线段
        arc = GC_MakeArcOfCircle(point_2, point_3, point_4).Value()
        segment_1 = GC_MakeSegment(point_1, point_2).Value()
        segment_2 = GC_MakeSegment(point_4, point_5).Value()

        # 3. 将曲线转换为拓扑边，再连接为线框
        edge_1 = BRepBuilderAPI_MakeEdge(segment_1).Edge()
        edge_2 = BRepBuilderAPI_MakeEdge(arc).Edge()
        edge_3 = BRepBuilderAPI_MakeEdge(segment_2).Edge()
        wire = BRepBuilderAPI_MakeWire(edge_1, edge_2, edge_3).Wire()

        # 4. 绕X轴镜像
        x_axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))
        transform = gp_Trsf()
        transform.SetMirror(x_axis)
        mirrored_shape = BRepBuilderAPI_Transform(wire, transform, True).Shape()
        mirrored_wire = TopoDS.Wire(mirrored_shape)

        wire_builder = BRepBuilderAPI_MakeWire()
        wire_builder.Add(wire)
        wire_builder.Add(mirrored_wire)
        if not wire_builder.IsDone():
            raise RuntimeError("瓶子轮廓线框创建失败。")

        full_wire = wire_builder.Wire()

        # 5. 轮廓生成面，再沿 Z 轴拉伸成瓶身
        profile_face = BRepBuilderAPI_MakeFace(full_wire).Face()
        body = BRepPrimAPI_MakePrism(profile_face, gp_Vec(0, 0, height)).Shape()

        # 6. 对瓶身的所有边添加圆角
        fillet_builder = BRepFilletAPI_MakeFillet(body)
        edge_explorer = TopExp_Explorer(body, TopAbs_EDGE)
        while edge_explorer.More():
            edge = TopoDS.Edge(edge_explorer.Current())
            fillet_builder.Add(thickness / 12, edge)
            edge_explorer.Next()
        fillet_builder.Build()
        if not fillet_builder.IsDone():
            raise RuntimeError("瓶身圆角创建失败，请调整尺寸。")
        body = fillet_builder.Shape()

        # 7. 创建瓶颈，并与瓶身融合
        neck_axis = gp_Ax2(gp_Pnt(0, 0, height), gp_Dir(0, 0, 1))
        neck_radius = thickness / 4
        neck_height = height / 10
        neck = BRepPrimAPI_MakeCylinder(neck_axis, neck_radius, neck_height).Shape()
        fuse_builder = BRepAlgoAPI_Fuse(body, neck)
        if not fuse_builder.IsDone():
            raise RuntimeError("瓶身与瓶颈融合失败。")
        body = fuse_builder.Shape()

        # 8. 找到瓶颈顶部的平面，移除该面并向内抽壳
        face_to_remove = None
        highest_z = -math.inf
        face_explorer = TopExp_Explorer(body, TopAbs_FACE)
        while face_explorer.More():
            face = TopoDS.Face(face_explorer.Current())
            surface = BRep_Tool.Surface_s(face)
            if isinstance(surface, Geom_Plane):
                z_position = surface.Location().Z()
                if z_position > highest_z:
                    highest_z = z_position
                    face_to_remove = face
            face_explorer.Next()
        if face_to_remove is None:
            raise RuntimeError("没有找到用于打开瓶口的平面。")

        faces_to_remove = List_TopoDS_Shape()
        faces_to_remove.Append(face_to_remove)
        solid_builder = BRepOffsetAPI_MakeThickSolid()
        solid_builder.MakeThickSolidByJoin(body, faces_to_remove, -thickness / 50, 1e-3)
        if not solid_builder.IsDone():
            raise RuntimeError("瓶身抽壳失败，请调整尺寸或壁厚。")
        body = solid_builder.Shape()

        # 9. 在两个同轴圆柱面上构建螺纹截面
        cylinder_surface_1 = Geom_CylindricalSurface(gp_Ax3(neck_axis), neck_radius * 0.99)
        cylinder_surface_2 = Geom_CylindricalSurface(gp_Ax3(neck_axis), neck_radius * 1.05)
        ellipse_axis = gp_Ax2d(
            gp_Pnt2d(2 * math.pi, neck_height / 2),
            gp_Dir2d(2 * math.pi, neck_height / 4),
        )
        major_radius = 2 * math.pi
        minor_radius = neck_height / 10
        ellipse_1 = Geom2d_Ellipse(ellipse_axis, major_radius, minor_radius)
        ellipse_2 = Geom2d_Ellipse(ellipse_axis, major_radius, minor_radius / 4)
        arc_1 = Geom2d_TrimmedCurve(ellipse_1, 0, math.pi)
        arc_2 = Geom2d_TrimmedCurve(ellipse_2, 0, math.pi)
        segment_2d = GC_MakeSegment2d(ellipse_1.Value(0), ellipse_1.Value(math.pi)).Value()

        threading_wire_1 = BRepBuilderAPI_MakeWire(
            BRepBuilderAPI_MakeEdge(arc_1, cylinder_surface_1).Edge(),
            BRepBuilderAPI_MakeEdge(segment_2d, cylinder_surface_1).Edge(),
        ).Wire()
        threading_wire_2 = BRepBuilderAPI_MakeWire(
            BRepBuilderAPI_MakeEdge(arc_2, cylinder_surface_2).Edge(),
            BRepBuilderAPI_MakeEdge(segment_2d, cylinder_surface_2).Edge(),
        ).Wire()
        if not BRepLib.BuildCurves3d_s(threading_wire_1):
            raise RuntimeError("第一条螺纹线框的三维曲线生成失败。")
        if not BRepLib.BuildCurves3d_s(threading_wire_2):
            raise RuntimeError("第二条螺纹线框的三维曲线生成失败。")

        # 10. 截面之间放样，生成螺纹实体
        threading_builder = BRepOffsetAPI_ThruSections(True)
        threading_builder.AddWire(threading_wire_1)
        threading_builder.AddWire(threading_wire_2)
        threading_builder.CheckCompatibility(False)
        threading_builder.Build()
        if not threading_builder.IsDone():
            raise RuntimeError("瓶口螺纹放样失败。")

        # 11. 用复合形状保留瓶身和螺纹两个实体
        result = TopoDS_Compound()
        compound_builder = BRep_Builder()
        compound_builder.MakeCompound(result)
        compound_builder.Add(result, body)
        compound_builder.Add(result, threading_builder.Shape())
        return result

    def create_bottle(self, width: float, height: float, thickness: float) -> ModelRecord:
        """Register a bottle for the existing entity tree, viewport and STEP export."""
        shape = self.make_bottle(width, height, thickness)
        if shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
            raise RuntimeError("瓶子模型创建失败，请调整尺寸。")

        bounds = Bnd_Box()
        BRepBndLib.AddOptimal_s(shape, bounds, False, False)
        if bounds.IsVoid() or bounds.IsOpen():
            raise ValueError("瓶子模型没有有效的有限尺寸。")
        x_min, y_min, z_min = bounds.CornerMin().Coord()
        x_max, y_max, z_max = bounds.CornerMax().Coord()
        dimensions = (x_max - x_min, y_max - y_min, z_max - z_min)
        if not all(math.isfinite(value) and value > 0 for value in dimensions):
            raise ValueError("瓶子模型尺寸无效。")

        sequence = self._sequence + 1
        record = ModelRecord(
            model_id=f"bottle-{sequence:04d}",
            name=f"瓶子 {sequence:02d}",
            # Match the existing parameter editor's two-decimal precision.
            length=round(dimensions[0], 2),
            width=round(dimensions[1], 2),
            height=round(dimensions[2], 2),
            shape=shape,
        )
        record.entities = load_entity_tree(None, shape, name=record.name)
        self._sequence = sequence
        self._active_record = record
        return record

    def set_imported_model(self, result: dict) -> ModelRecord:
        shape = result["shape"]
        display_shape = result["display_shape"]
        if shape.IsNull() or display_shape.IsNull():
            raise ValueError("STEP 文件中没有可显示的模型。")
        self._sequence += 1
        record = ModelRecord(
            model_id=f"step-{self._sequence:04d}",
            name=result["name"],
            length=result["dimensions"][0],
            width=result["dimensions"][1],
            height=result["dimensions"][2],
            shape=shape,
            display_shape=display_shape,
            source_path=result["source_path"],
            appearance=result.get("appearance"),
            entities=load_entity_tree(result.get("entities"), shape, display_shape, result["name"]),
        )
        self._active_record = record
        return record

    def export_step(self, destination: str | Path) -> Path:
        record = self.active_record
        if record is None:
            raise ValueError("请先创建一个模型。")
        path = Path(destination).expanduser()
        if path.suffix.lower() not in {".step", ".stp"}:
            raise ValueError("请选择 .step 或 .stp 文件。")
        if not path.parent.is_dir():
            raise ValueError("保存目录不存在。")
        if record.appearance:
            from app.cad.models.model_appearance import export_colored_step

            export_colored_step(record.shape, record.appearance, path)
            return path.resolve()
        writer = STEPControl_Writer()
        if writer.Transfer(record.shape, STEPControl_AsIs) != IFSelect_RetDone:
            raise RuntimeError("模型转换失败，未能导出 STEP。")
        if writer.Write(str(path)) != IFSelect_RetDone:
            raise OSError("文件保存失败，请检查目录权限。")
        return path.resolve()
