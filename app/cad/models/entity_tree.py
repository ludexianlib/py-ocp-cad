"""UI-independent entity hierarchy, geometry fallback and display state."""

from copy import deepcopy

from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE
from OCP.TopoDS import TopoDS_Iterator

from app.cad.models.model_appearance import shape_map


def geometry_parts(shape):
    """Partition compounds without dropping loose surfaces, wires or edges."""
    if shape.ShapeType() in (TopAbs_COMPOUND, TopAbs_COMPSOLID):
        children = TopoDS_Iterator(shape)
        while children.More():
            yield from geometry_parts(children.Value())
            children.Next()
    else:
        yield shape


def shape_kind(shape):
    return {TopAbs_SOLID: "实体", TopAbs_SHELL: "曲面组", TopAbs_FACE: "曲面",
            TopAbs_WIRE: "线框", TopAbs_EDGE: "边"}.get(shape.ShapeType(), "形状")


def make_node(node_id, name, kind, shape_index=0, children=None):
    return {"node_id": node_id, "name": name, "kind": kind,
            "shape_index": shape_index, "display_index": 0, "children": children or []}


def fallback_tree(shape, name="模型", display_shape=None):
    originals = shape_map(shape)
    parts = list(geometry_parts(shape)) or [shape]
    display_parts = list(geometry_parts(display_shape)) if display_shape is not None else []
    if display_shape is not None and (len(parts) != len(display_parts) or any(
        original.ShapeType() != display.ShapeType() for original, display in zip(parts, display_parts)
    )):
        parts, display_parts = [shape], [display_shape]
    displays = shape_map(display_shape) if display_shape is not None else None
    nodes = []
    for index, part in enumerate(parts, 1):
        kind = shape_kind(part)
        node = make_node(f"model/{index}", f"{kind} {index}", kind, originals.FindIndex(part))
        if displays is not None:
            node["display_index"] = displays.FindIndex(display_parts[index - 1])
        nodes.append(node)
    return {"version": 1, "source": "geometry", "root": make_node("model", name, "模型", children=nodes)}


def extract_step_tree(shape, labels, shape_tool, name="模型"):
    """Use occurrence paths as IDs, including repeated/coincident instances."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_AttributeIterator, TDF_Label
    from OCP.TopLoc import TopLoc_Location

    shapes = shape_map(shape)
    has_assembly = False

    def label_name(label):
        # Use actual attribute handles; OCP's in/out FindAttribute binding is
        # unsafe when a name is absent.
        attributes = TDF_AttributeIterator(label)
        while attributes.More():
            attribute = attributes.Value()
            if isinstance(attribute, TDataStd_Name):
                return attribute.Get().ToExtString().strip()
            attributes.Next()
        return ""

    def visit(label, parent_location, node_id, ancestors):
        nonlocal has_assembly
        if len(ancestors) >= 128:
            raise ValueError("模型装配层级过深。")
        definition = label
        location = parent_location
        referred = TDF_Label()
        instance_name = label_name(label)
        if shape_tool.GetReferredShape_s(label, referred):
            location = parent_location.Multiplied(shape_tool.GetLocation_s(label))
            definition = referred
        if any(definition == ancestor for ancestor in ancestors):
            raise ValueError("模型装配层级存在循环引用。")
        part_name = instance_name or label_name(definition)
        components = Sequence_TDF_Label()
        if shape_tool.GetComponents_s(definition, components) and components.Length():
            has_assembly = True
            if definition == label:
                location = parent_location.Multiplied(shape_tool.GetLocation_s(label))
            children = [visit(components.Value(index), location, f"{node_id}/{index}", ancestors + [definition])
                        for index in range(1, components.Length() + 1)]
            return make_node(node_id, part_name or f"装配体 {node_id.rsplit('/', 1)[-1]}", "装配体", children=children)
        part = shape_tool.GetShape_s(definition).Moved(location)
        if part.IsNull():
            raise ValueError("模型零件没有有效几何。")
        parts = list(geometry_parts(part)) or [part]
        if len(parts) == 1:
            index = shapes.FindIndex(parts[0])
            if not index:
                raise ValueError("模型零件无法匹配到几何。")
            return make_node(node_id, part_name or f"{shape_kind(parts[0])} {node_id.rsplit('/', 1)[-1]}",
                             shape_kind(parts[0]), index)
        children = []
        for index, current in enumerate(parts, 1):
            shape_index = shapes.FindIndex(current)
            if not shape_index:
                raise ValueError("模型实体无法匹配到几何。")
            kind = shape_kind(current)
            children.append(make_node(f"{node_id}/{index}", f"{kind} {index}", kind, shape_index))
        return make_node(node_id, part_name or f"零件 {node_id.rsplit('/', 1)[-1]}", "零件", children=children)

    try:
        children = [visit(labels.Value(index), TopLoc_Location(), f"model/{index}", [])
                    for index in range(1, labels.Length() + 1)]
        if not has_assembly and labels.Length() == 1:
            return fallback_tree(shape, name)
        return {"version": 1, "source": "assembly" if has_assembly else "geometry",
                "root": make_node("model", name, "模型", children=children)}
    except (ValueError, RuntimeError, RecursionError):
        return fallback_tree(shape, name)


def map_display_entities(metadata, shape, display_shape, copier):
    originals, displays = shape_map(shape), shape_map(display_shape)
    try:
        tree = EntityTree(metadata)
        for node in tree.leaves.values():
            target = copier.ModifiedShape(originals.FindKey(node["shape_index"]))
            node["display_index"] = displays.FindIndex(target)
            if not node["display_index"]:
                raise ValueError("实体无法匹配到显示副本。")
        return tree.metadata
    except (ValueError, RuntimeError, IndexError):
        return fallback_tree(shape, metadata.get("root", {}).get("name", "模型"), display_shape)


def load_entity_tree(metadata, shape, display_shape=None, name="模型"):
    """Invalid/missing hierarchy falls back; valid geometry remains importable."""
    try:
        tree = EntityTree(metadata)
        originals = shape_map(shape)
        displays = shape_map(display_shape) if display_shape is not None else None
        for node in tree.leaves.values():
            index = node["shape_index"]
            if not isinstance(index, int) or not 1 <= index <= originals.Extent():
                raise ValueError("实体几何索引无效。")
            if displays is not None:
                display_index = node["display_index"]
                if not isinstance(display_index, int) or not 1 <= display_index <= displays.Extent():
                    raise ValueError("实体显示索引无效。")
                if originals.FindKey(index).ShapeType() != displays.FindKey(display_index).ShapeType():
                    raise ValueError("实体与显示副本不一致。")
        # Every geometric partition must be covered, including loose non-solid shapes.
        covered = set()
        for node in tree.leaves.values():
            target = originals.FindKey(node["shape_index"])
            for part in geometry_parts(target):
                covered.add(originals.FindIndex(part))
        if not all(originals.FindIndex(part) in covered for part in geometry_parts(shape)):
            raise ValueError("实体树没有覆盖整个模型。")
        return tree
    except (TypeError, KeyError, ValueError, RuntimeError, RecursionError):
        return EntityTree(fallback_tree(shape, name, display_shape))


class EntityTree:
    def __init__(self, metadata):
        if not isinstance(metadata, dict) or metadata.get("version") != 1:
            raise ValueError("实体层级数据无效。")
        self.metadata = deepcopy(metadata)
        self.nodes = {}
        self.leaves = {}
        self.descendants = {}

        def visit(node, depth=0):
            if not isinstance(node, dict) or depth > 128:
                raise ValueError("实体节点无效。")
            node_id = node["node_id"]
            if not isinstance(node_id, str) or not node_id or node_id in self.nodes:
                raise ValueError("实体节点标识无效。")
            if not isinstance(node.get("name"), str) or not isinstance(node.get("children"), list):
                raise ValueError("实体节点内容无效。")
            self.nodes[node_id] = node
            children = node["children"]
            if children:
                descendants = set()
                for child in children:
                    descendants.update(visit(child, depth + 1))
            else:
                if not node.get("shape_index"):
                    raise ValueError("实体节点缺少几何。")
                self.leaves[node_id] = node
                descendants = {node_id}
            self.descendants[node_id] = descendants
            return descendants

        visit(self.metadata["root"])
        self.selected_ids = set()
        self.visible_ids = set(self.leaves)

    def select(self, node_id, additive=False, context=False):
        targets = self.descendants.get(node_id, set())
        if context and (not targets or targets <= self.selected_ids):
            return
        if additive:
            if targets <= self.selected_ids:
                self.selected_ids.difference_update(targets)
            else:
                self.selected_ids.update(targets)
        else:
            self.selected_ids = set(targets)

    def hide_selected(self):
        self.visible_ids.difference_update(self.selected_ids)

    def isolate_selected(self):
        if self.selected_ids:
            self.visible_ids = set(self.selected_ids)

    def show_all(self):
        self.visible_ids = set(self.leaves)

    def snapshot(self):
        return tuple((node_id, node["shape_index"], node["display_index"],
                      node_id in self.visible_ids, node_id in self.selected_ids)
                     for node_id, node in self.leaves.items())
