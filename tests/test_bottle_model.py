"""OCCT tutorial bottle geometry and workbench integration regressions."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_OUT, TopAbs_SOLID
from OCP.gp import gp_Pnt
from PyQt6.QtCore import QCoreApplication

from app.controllers.cad_controller import CadController
from app.models.cad_model import CadModel
from app.models.entity_tree import geometry_parts


class BottleModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = CadModel()
        cls.record = cls.model.create_bottle(50, 70, 30)

    def test_bottle_contains_valid_hollow_body_and_threading(self):
        shape = self.record.shape
        self.assertFalse(shape.IsNull())
        self.assertTrue(BRepCheck_Analyzer(shape).IsValid())
        parts = list(geometry_parts(shape))
        self.assertEqual(len(parts), 2)
        for part in parts:
            self.assertEqual(part.ShapeType(), TopAbs_SOLID)
            self.assertTrue(BRepCheck_Analyzer(part).IsValid())
        body = parts[0]
        for point in (gp_Pnt(0, 0, 35), gp_Pnt(0, 0, 76)):
            classifier = BRepClass3d_SolidClassifier(body, point, 1e-7)
            self.assertEqual(classifier.State(), TopAbs_OUT)

    def test_record_includes_neck_height_and_both_entities(self):
        record = self.record
        self.assertIs(self.model.active_record, record)
        self.assertEqual(record.model_id, "bottle-0001")
        self.assertEqual((record.length, record.width, record.height), (50, 30, 77))
        self.assertEqual(len(record.entities.leaves), 2)
        self.assertEqual(record.entities.metadata["root"]["name"], record.name)
        self.assertFalse(record.to_summary()["is_imported"])

    def test_step_export_preserves_body_and_threading(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "bottle.step"
            self.assertEqual(self.model.export_step(destination), destination.resolve())
            reader = STEPControl_Reader()
            self.assertEqual(reader.ReadFile(str(destination)), IFSelect_RetDone)
            self.assertGreater(reader.TransferRoots(), 0)
            shape = reader.OneShape()
            self.assertTrue(BRepCheck_Analyzer(shape).IsValid())
            self.assertEqual(len(list(geometry_parts(shape))), 2)

    def test_invalid_dimensions_preserve_current_model(self):
        model = CadModel()
        previous = model.create_box(10, 20, 30)
        for value in (0, -1, float("nan"), float("inf"), "invalid", None):
            for index in range(3):
                dimensions = [50, 70, 30]
                dimensions[index] = value
                with self.subTest(value=value, index=index):
                    with self.assertRaisesRegex(ValueError, "瓶子尺寸"):
                        model.create_bottle(*dimensions)
                    self.assertIs(model.active_record, previous)
        self.assertEqual(model.create_box(1, 2, 3).model_id, "box-0002")


class BottleControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def test_startup_bottle_can_be_replaced_with_box(self):
        controller = CadController()
        try:
            self.assertTrue(controller.has_model)
            self.assertTrue(controller.active_model["model_id"].startswith("bottle-"))
            self.assertAlmostEqual(controller.active_model["height"], 77)
            self.assertEqual(controller.entity_count, 2)

            previous_shape = controller.active_shape
            self.assertFalse(controller.create_bottle(-1, 70, 30))
            self.assertIs(controller.active_shape, previous_shape)

            changes = []
            controller.state_changed.connect(lambda: changes.append(controller.active_shape))
            self.assertTrue(controller.create_box(40, 30, 10))
            self.assertEqual(len(changes), 1)
            self.assertTrue(controller.active_model["model_id"].startswith("box-"))
            self.assertEqual(controller.entity_count, 1)

            controller._loading = True
            box_shape = controller.active_shape
            self.assertFalse(controller.create_bottle(50, 70, 30))
            self.assertIs(controller.active_shape, box_shape)
        finally:
            controller.deleteLater()


if __name__ == "__main__":
    unittest.main()
