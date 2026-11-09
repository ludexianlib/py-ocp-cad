"""UI-independent STEP colors, deterministic fallback colors and BREP mappings."""

import math
from pathlib import Path


PALETTE = (
    (0.43, 0.55, 0.74), (0.56, 0.50, 0.72), (0.39, 0.65, 0.58),
    (0.77, 0.58, 0.42), (0.68, 0.48, 0.56), (0.48, 0.61, 0.69),
    (0.67, 0.64, 0.40), (0.54, 0.59, 0.49),
)


def shape_map(shape):
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
    from OCP.TopExp import TopExp

    shapes = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape, shapes)
    return shapes


def new_document():
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document

    return TDocStd_Document(TCollection_ExtendedString("BinXCAF"))


def read_step_model(path, notify, *, include_entities=False):
    from OCP.BRep import BRep_Builder
    from OCP.collections import Sequence_TDF_Label
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TopoDS import TopoDS_Compound
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    reader.SetSHUOMode(True)
    reader.SetPropsMode(False)
    reader.SetGDTMode(False)
    notify("phase", text="正在读取文件与颜色…")
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError("无法读取 STEP 文件，请检查文件格式是否正确。")
    reader.Reader().SetSystemLengthUnit(1.0)
    document = new_document()
    notify("phase", text="正在转换模型与外观…")
    if not reader.Transfer(document):
        raise ValueError("STEP 文件中没有可导入的几何模型。")
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    labels = Sequence_TDF_Label()
    shape_tool.GetFreeShapes(labels)
    if labels.Length() == 0:
        raise ValueError("STEP 文件中没有可导入的几何模型。")
    if labels.Length() == 1:
        shape = shape_tool.GetShape_s(labels.Value(1))
    else:
        shape = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(shape)
        for index in range(1, labels.Length() + 1):
            builder.Add(shape, shape_tool.GetShape_s(labels.Value(index)))
    if shape.IsNull():
        raise ValueError("STEP 文件中没有可导入的几何模型。")
    appearance = collect_appearance(shape, labels, shape_tool)
    if include_entities:
        from app.models.entity_tree import extract_step_tree

        return shape, appearance, extract_step_tree(shape, labels, shape_tool, Path(path).stem)
    return shape, appearance


def collect_appearance(shape, labels, shape_tool):
    from OCP.collections import IndexedDataMap_TopoDS_Shape_XCAFPrs_Style_TopTools_ShapeMapHasher
    from OCP.collections import Sequence_TDF_Label
    from OCP.Quantity import Quantity_TypeOfColor
    from OCP.TDF import TDF_Label
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Iterator
    from OCP.XCAFPrs import XCAFPrs

    styles = IndexedDataMap_TopoDS_Shape_XCAFPrs_Style_TopTools_ShapeMapHasher()
    shapes = shape_map(shape)
    fallback_groups = {}
    group_count = 0

    def collect_parts(label, parent_location):
        nonlocal group_count
        referred = TDF_Label()
        if shape_tool.GetReferredShape_s(label, referred):
            location = parent_location.Multiplied(shape_tool.GetLocation_s(label))
            collect_parts(referred, location)
            return
        components = Sequence_TDF_Label()
        if shape_tool.GetComponents_s(label, components):
            location = parent_location.Multiplied(shape_tool.GetLocation_s(label))
            for index in range(1, components.Length() + 1):
                collect_parts(components.Value(index), location)
            return
        part = shape_tool.GetShape_s(label).Moved(parent_location)
        part_index = shapes.FindIndex(part)
        if part_index:
            fallback_groups[part_index] = PALETTE[group_count % len(PALETTE)]
            solids = []
            explorer = TopExp_Explorer(part, TopAbs_SOLID)
            while explorer.More():
                solids.append(explorer.Current())
                explorer.Next()
            if len(solids) > 1:
                for offset, solid in enumerate(solids):
                    fallback_groups[shapes.FindIndex(solid)] = PALETTE[(group_count + offset) % len(PALETTE)]
            group_count += max(1, len(solids))

    for index in range(1, labels.Length() + 1):
        label = labels.Value(index)
        XCAFPrs.CollectStyleSettings_s(label, TopLoc_Location(), styles)
        collect_parts(label, TopLoc_Location())

    colors = []
    visited = set()
    source_count = 0
    generated_count = 0

    def visit(current, inherited_color=None, inherited_source=False):
        nonlocal source_count, generated_count
        index = shapes.FindIndex(current)
        if index in visited:
            return
        visited.add(index)
        color = None
        style_index = styles.FindIndex(current)
        if style_index:
            style = styles.FindFromIndex(style_index)
            if style.IsSetColorSurf():
                color = style.GetColorSurf().Values(Quantity_TypeOfColor.Quantity_TOC_sRGB)
            elif current.ShapeType() in (TopAbs_EDGE, TopAbs_WIRE) and style.IsSetColorCurv():
                color = style.GetColorCurv().Values(Quantity_TypeOfColor.Quantity_TOC_sRGB)
        if color is not None:
            source_count += 1
            is_source = True
        elif not inherited_source and index in fallback_groups:
            color = fallback_groups[index]
            generated_count += 1
            is_source = False
        else:
            is_source = inherited_source
        if color is not None:
            colors.append({"shape_index": index, "rgb": list(color)})
        effective_color = color if color is not None else inherited_color
        if current.ShapeType() in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
            return
        children = TopoDS_Iterator(current)
        while children.More():
            visit(children.Value(), effective_color, is_source)
            children.Next()

    visit(shape)
    return {"version": 1, "colors": colors, "source_color_count": source_count,
            "generated_color_count": generated_count}


def map_display_colors(shape, display_shape, copier, appearance):
    """Map actual copied subshapes before serializing either BREP tree."""
    originals = shape_map(shape)
    display_shapes = shape_map(display_shape)
    for entry in appearance["colors"]:
        original = originals.FindKey(entry["shape_index"])
        copied = copier.ModifiedShape(original)
        display_index = display_shapes.FindIndex(copied)
        if not display_index:
            raise RuntimeError("无法将模型颜色匹配到显示副本。")
        entry["display_index"] = display_index


def appearance_targets(shape, appearance, for_display=False):
    if not appearance or appearance.get("version") != 1:
        return
    shapes = shape_map(shape)
    key = "display_index" if for_display else "shape_index"
    for entry in appearance["colors"]:
        index = entry[key]
        rgb = entry["rgb"]
        if not isinstance(index, int) or not 1 <= index <= shapes.Extent():
            raise ValueError("模型颜色索引无效。")
        if len(rgb) != 3 or not all(math.isfinite(value) and 0 <= value <= 1 for value in rgb):
            raise ValueError("模型颜色数据无效。")
        yield shapes.FindKey(index), rgb


def export_colored_step(shape, appearance, destination):
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

    document = new_document()
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    root_label = shape_tool.AddShape(shape, False, False)
    for target, rgb in appearance_targets(shape, appearance):
        label = root_label if target.IsSame(shape) else shape_tool.AddSubShape(root_label, target)
        if label.IsNull():
            raise RuntimeError("无法保存模型子形状的颜色。")
        color = Quantity_Color(*rgb, Quantity_TypeOfColor.Quantity_TOC_sRGB)
        color_type = (XCAFDoc_ColorType.XCAFDoc_ColorCurv
                      if target.ShapeType() in (TopAbs_EDGE, TopAbs_WIRE)
                      else XCAFDoc_ColorType.XCAFDoc_ColorSurf)
        color_tool.SetColor(label, color, color_type)
    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    if not writer.Transfer(document, STEPControl_AsIs):
        raise RuntimeError("模型与颜色转换失败，未能导出 STEP。")
    if writer.Write(str(Path(destination))) != IFSelect_RetDone:
        raise OSError("文件保存失败，请检查目录权限。")
