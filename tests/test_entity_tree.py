"""Run with: python -m unittest discover -s tests -v."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from OCP.BRep import BRep_Builder
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.Bnd import Bnd_Box
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.collections import Sequence_TDF_Label
from OCP.gp import gp_Pln, gp_Pnt, gp_Trsf, gp_Vec
from PyQt6.QtCore import QCoreApplication, QObject, QUrl, pyqtSignal

from app.cad.controllers.cad_controller import CadController
from app.cad.controllers.entity_tree_model import EntityTreeModel
from app.cad.models.entity_tree import EntityTree, extract_step_tree, fallback_tree, load_entity_tree, map_display_entities
from app.cad.models.model_appearance import new_document, read_step_model, shape_map
from app.cad.models.step_importer import import_step, load_prepared_model


def compound(*shapes):
    result = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def translated(x):
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(x, 0, 0))
    return TopLoc_Location(transform)


def assembly_document(coincident=False):
    document = new_document()
    tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    part = tool.AddShape(BRepPrimAPI_MakeBox(5, 6, 7).Shape(), False, False)
    root = tool.NewShape()
    nested = tool.NewShape()
    left = tool.AddComponent(root, part, translated(0))
    right = tool.AddComponent(root, part, translated(0 if coincident else 20))
    inner = tool.AddComponent(nested, part, translated(10))
    branch = tool.AddComponent(root, nested, translated(40))
    for label, name in ((root, "总装"), (part, "Bolt"), (left, "Left bolt"),
                        (right, "Right bolt"), (nested, "Bracket group"), (inner, "Inner bolt"),
                        (branch, "Nested instance")):
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name, True))
    tool.UpdateAssemblies()
    labels = Sequence_TDF_Label()
    tool.GetFreeShapes(labels)
    return document, tool, labels, tool.GetShape_s(root)


class EntityTreeTests(unittest.TestCase):
    def test_fallback_keeps_solids_surfaces_and_edges(self):
        solid = BRepPrimAPI_MakeBox(2, 3, 4).Shape()
        surface = BRepBuilderAPI_MakeFace(gp_Pln(), 0, 2, 0, 3).Face()
        edge = BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 10), gp_Pnt(5, 0, 10)).Edge()
        shape = compound(compound(solid), surface, edge)
        tree = load_entity_tree(None, shape)
        self.assertEqual(len(tree.leaves), 3)
        self.assertEqual({node["kind"] for node in tree.leaves.values()}, {"实体", "曲面", "边"})
        self.assertEqual(tree.visible_ids, set(tree.leaves))

    def test_single_surface_and_solid_have_an_operable_leaf(self):
        for shape in (BRepPrimAPI_MakeBox(1, 2, 3).Shape(), BRepBuilderAPI_MakeFace(gp_Pln(), 0, 2, 0, 3).Face()):
            tree = load_entity_tree(None, shape)
            tree.select("model")
            tree.hide_selected()
            self.assertEqual(tree.visible_ids, set())
            tree.show_all()
            self.assertEqual(len(tree.visible_ids), 1)

    def test_assembly_names_instance_ids_and_nested_placements(self):
        document, tool, labels, shape = assembly_document()
        tree = EntityTree(extract_step_tree(shape, labels, tool))
        self.assertEqual(tree.metadata["source"], "assembly")
        self.assertIn("总装", {node["name"] for node in tree.nodes.values()})
        self.assertEqual(len(tree.leaves), 3)
        self.assertEqual({node["name"] for node in tree.leaves.values()}, {"Left bolt", "Right bolt", "Inner bolt"})
        shapes = shape_map(shape)
        minima = []
        for node in tree.leaves.values():
            bounds = Bnd_Box()
            BRepBndLib.AddOptimal_s(shapes.FindKey(node["shape_index"]), bounds, False, False)
            minima.append(round(bounds.CornerMin().X()))
        self.assertEqual(sorted(minima), [0, 20, 50])

    def test_coincident_instances_remain_independently_selectable(self):
        document, tool, labels, shape = assembly_document(coincident=True)
        tree = EntityTree(extract_step_tree(shape, labels, tool))
        leaves = list(tree.leaves)
        self.assertEqual(len(leaves), 3)
        self.assertNotEqual(leaves[0], leaves[1])
        tree.select(leaves[0])
        tree.hide_selected()
        self.assertNotIn(leaves[0], tree.visible_ids)
        self.assertIn(leaves[1], tree.visible_ids)

    def test_unnamed_assembly_gets_nonempty_names(self):
        document, tool, labels, shape = assembly_document()
        from OCP.TDF import TDF_ChildIterator

        def clear_names(label):
            label.ForgetAttribute(TDataStd_Name.GetID_s())
            children = TDF_ChildIterator(label, False)
            while children.More():
                clear_names(children.Value())
                children.Next()

        clear_names(document.Main())
        tree = EntityTree(extract_step_tree(shape, labels, tool))
        self.assertEqual(tree.metadata["source"], "assembly")
        self.assertTrue(all(node["name"] for node in tree.nodes.values()))

    def test_selection_context_menu_and_visibility_semantics(self):
        shape = compound(*(BRepPrimAPI_MakeBox(gp_Pnt(index * 10, 0, 0), 2, 3, 4).Shape() for index in range(4)))
        tree = load_entity_tree(None, shape)
        a, b, c, d = tree.leaves
        tree.select(a)
        tree.select(b, additive=True)
        tree.select(a, context=True)
        self.assertEqual(tree.selected_ids, {a, b})
        tree.hide_selected()
        self.assertEqual(tree.visible_ids, {c, d})
        tree.isolate_selected()
        self.assertEqual(tree.visible_ids, {a, b})
        tree.select(c, context=True)
        self.assertEqual(tree.selected_ids, {c})
        tree.select("", context=True)
        self.assertEqual(tree.selected_ids, {c})
        tree.select("model")
        self.assertEqual(tree.selected_ids, {a, b, c, d})
        tree.hide_selected()
        tree.show_all()
        self.assertEqual(tree.visible_ids, {a, b, c, d})
        tree.select("")
        tree.isolate_selected()
        self.assertEqual(tree.visible_ids, {a, b, c, d})

    def test_missing_malformed_and_incomplete_hierarchy_falls_back(self):
        shape = compound(BRepPrimAPI_MakeBox(2, 3, 4).Shape(), BRepPrimAPI_MakeBox(gp_Pnt(10, 0, 0), 2, 3, 4).Shape())
        valid = fallback_tree(shape)
        invalid = deepcopy(valid)
        invalid["root"]["children"][0]["shape_index"] = 999999
        incomplete = deepcopy(valid)
        incomplete["root"]["children"].pop()
        duplicate = deepcopy(valid)
        duplicate["root"]["children"][1]["node_id"] = duplicate["root"]["children"][0]["node_id"]
        for metadata in (None, {}, invalid, incomplete, duplicate):
            tree = load_entity_tree(metadata, shape)
            self.assertEqual(len(tree.leaves), 2)
            self.assertEqual(tree.metadata["source"], "geometry")

    def test_display_mapping_survives_real_brep_handoff(self):
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            document, tool, labels, shape = assembly_document()
            source = directory / "assembly.step"
            writer = STEPCAFControl_Writer()
            writer.SetNameMode(True)
            self.assertTrue(writer.Transfer(document, STEPControl_AsIs))
            self.assertEqual(writer.Write(str(source)), IFSelect_RetDone)
            events = []
            import_step(source, directory, lambda event, **values: events.append(event))
            result = load_prepared_model(directory)
            tree = load_entity_tree(result["entities"], result["shape"], result["display_shape"])
            self.assertEqual(len(tree.leaves), 3)
            self.assertEqual(tree.metadata["source"], "assembly")
            self.assertTrue(all(node["display_index"] > 0 for node in tree.leaves.values()))
            self.assertIn("prepared", events)
            metadata_path = directory / "result.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata.pop("entities")
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            fallback_result = load_prepared_model(directory)
            fallback = EntityTree(fallback_result["entities"])
            self.assertEqual(fallback.metadata["source"], "geometry")
            self.assertEqual(len(fallback.leaves), 3)
            # Legacy callers that only need geometry and appearance remain valid.
            self.assertEqual(len(read_step_model(source, lambda *args, **values: None)), 2)

    def test_invalid_display_index_falls_back_to_complete_geometry(self):
        document, tool, labels, shape = assembly_document()
        copier = BRepBuilderAPI_Copy(shape, True, False)
        display = copier.Shape()
        metadata = map_display_entities(extract_step_tree(shape, labels, tool), shape, display, copier)
        tree = EntityTree(metadata)
        next(iter(tree.leaves.values()))["display_index"] = 999999
        restored = load_entity_tree(tree.metadata, shape, display)
        self.assertEqual(restored.metadata["source"], "geometry")
        self.assertEqual(len(restored.leaves), 3)
        self.assertTrue(all(node["display_index"] > 0 for node in restored.leaves.values()))


class ControlledImportTask(QObject):
    prepared = pyqtSignal(object)
    failed = pyqtSignal(str)
    phase_changed = pyqtSignal(str)
    finished = pyqtSignal()

    def start(self, path):
        pass


class EntityAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def test_expand_collapse_and_parent_partial_state(self):
        shape = compound(BRepPrimAPI_MakeBox(2, 3, 4).Shape(), BRepPrimAPI_MakeBox(gp_Pnt(10, 0, 0), 2, 3, 4).Shape())
        tree = load_entity_tree(None, shape)
        model = EntityTreeModel()
        model.set_tree(tree)
        self.assertEqual(model.rowCount(), 3)
        model.toggle_expanded("model")
        self.assertEqual(model.rowCount(), 1)
        model.toggle_expanded("model")
        self.assertEqual(model.rowCount(), 3)
        tree.select(next(iter(tree.leaves)))
        tree.hide_selected()
        roles = {name.decode(): role for role, name in model.roleNames().items()}
        self.assertTrue(model.data(model.index(0), roles["is_partial"]))
        self.assertTrue(model.data(model.index(0), roles["is_partly_visible"]))
        model.set_tree(None)
        self.assertEqual(model.rowCount(), 0)

    def test_reveal_expands_ancestors_without_resetting_selection_or_siblings(self):
        document, tool, labels, shape = assembly_document()
        tree = EntityTree(extract_step_tree(shape, labels, tool))
        target_id = next(node_id for node_id, node in tree.leaves.items() if node["name"] == "Inner bolt")
        other_id = next(node_id for node_id, node in tree.leaves.items() if node["name"] == "Left bolt")
        tree.select(other_id)
        tree.hide_selected()
        snapshot = tree.snapshot()
        model = EntityTreeModel()
        model.set_tree(tree)
        root_id = tree.metadata["root"]["node_id"]
        branch_id = model._parent_ids[target_id]
        # Keep this unrelated branch expanded while revealing a collapsed sibling.
        model.toggle_expanded(branch_id)
        model.toggle_expanded(root_id)
        self.assertEqual(model.rowCount(), 1)
        inserted = []
        reset = []
        model.rowsInserted.connect(lambda parent, first, last: inserted.append((first, last)))
        model.modelReset.connect(lambda: reset.append(True))
        row = model.reveal_node(other_id)
        role = next(role for role, name in model.roleNames().items() if name == b"node_id")
        self.assertEqual(model.data(model.index(row), role), other_id)
        self.assertIn(branch_id, model._expanded_ids)
        self.assertEqual(model.data(model.index(model.reveal_node(target_id)), role), target_id)
        self.assertEqual(tree.snapshot(), snapshot)
        self.assertTrue(inserted)
        self.assertEqual(reset, [])
        inserted.clear()
        self.assertEqual(model.reveal_node(other_id), row)
        self.assertEqual(inserted, [])
        self.assertEqual(model.reveal_node("missing"), -1)
        model.set_tree(None)
        self.assertEqual(model.reveal_node(target_id), -1)

    def test_reveal_distinguishes_repeated_geometry_occurrences(self):
        document, tool, labels, shape = assembly_document(coincident=True)
        tree = EntityTree(extract_step_tree(shape, labels, tool))
        model = EntityTreeModel()
        model.set_tree(tree)
        target_id = next(node_id for node_id, node in tree.leaves.items() if node["name"] == "Inner bolt")
        parent_id = model._parent_ids[target_id]
        self.assertNotIn(parent_id, model._expanded_ids)
        row = model.reveal_node(target_id)
        self.assertIn(parent_id, model._expanded_ids)
        role = next(role for role, name in model.roleNames().items() if name == b"node_id")
        self.assertEqual(model.data(model.index(row), role), target_id)
        rows = {model.reveal_node(node_id) for node_id in tree.leaves}
        self.assertEqual(len(rows), 3)

    def test_only_selected_viewport_entities_request_tree_focus(self):
        controller = CadController()
        tree = controller.active_entities
        node_id = next(iter(tree.leaves))
        requests = []
        controller.entity_focus_requested.connect(requests.append)
        controller.select_entity(node_id, False, False)
        self.assertEqual(requests, [])
        controller.select_entity_from_viewport(node_id, False, False)
        controller.select_entity_from_viewport(node_id, False, True)
        self.assertEqual(requests, [node_id, node_id])
        requests.clear()
        controller.select_entity_from_viewport(node_id, True, False)
        controller.select_entity_from_viewport("", False, False)
        controller.select_entity_from_viewport("", False, True)
        controller.select_entity_from_viewport("missing", False, False)
        self.assertEqual(requests, [])
        self.assertEqual(tree.selected_ids, set())
        controller._loading = True
        controller.select_entity_from_viewport(node_id, False, False)
        self.assertEqual(requests, [])
        self.assertEqual(tree.selected_ids, set())
        controller.deleteLater()

    def test_failed_import_restores_previous_selection_and_visibility(self):
        controller = CadController()
        previous = controller._model.active_record
        controller.select_entity("model", False, False)
        controller.hide_selected_entities()
        with TemporaryDirectory() as directory, patch("app.cad.controllers.cad_controller.StepImportTask", ControlledImportTask):
            source = Path(directory) / "placeholder.step"
            source.write_text("placeholder")
            self.assertTrue(controller.import_step(QUrl.fromLocalFile(str(source))))
            state = controller._pending_import
            shape = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
            display = BRepBuilderAPI_Copy(shape, True, False).Shape()
            state["task"].prepared.emit({"shape": shape, "display_shape": display, "dimensions": (1, 2, 3),
                                         "name": "replacement", "source_path": str(source)})
            controller.report_model_displayed(shape, "render failure")
            self.assertIs(controller._model.active_record, previous)
            self.assertEqual(controller.selected_entity_count, len(previous.entities.leaves))
            self.assertEqual(controller.active_entities.visible_ids, set())
            self.assertIsNone(state["previous_record"])
            state["task"].prepared.emit({})
            self.assertIs(controller._model.active_record, previous)
        controller.deleteLater()


if __name__ == "__main__":
    unittest.main()
