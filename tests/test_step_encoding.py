"""Legacy text conversion and real STEP assembly-name regressions."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Trsf, gp_Vec

from app.models.entity_tree import EntityTree
from app.models.model_appearance import new_document, read_step_model
from app.models.step_encoding import detect_step_encoding, prepared_step_stream


class StepEncodingTests(unittest.TestCase):
    def test_ascii_utf8_and_standard_escapes_preserve_their_bytes(self):
        samples = (b"ISO-10303-21; 'ASCII';", "'主轴模块╱组';".encode("utf-8"),
                   b"'\\X2\\4E3B8F74\\X0\\';")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.step"
            for original in samples:
                with self.subTest(original=original):
                    path.write_bytes(original)
                    self.assertEqual(detect_step_encoding(path), "utf-8")
                    with prepared_step_stream(path) as stream:
                        self.assertEqual(stream.read(), original)
                    self.assertTrue(stream.closed)
                    self.assertEqual(path.read_bytes(), original)

    def test_gbk_extended_characters_and_chunk_boundaries_preserve_source_bytes(self):
        text = "ISO-10303-21;\r\n'主轴模块╱组';\r\n#1 = CARTESIAN_POINT('',(1.25,-2.5,0.));\r\n"
        original = text.encode("gbk")
        with TemporaryDirectory() as directory, patch("app.models.step_encoding._CHUNK_SIZE", 1):
            path = Path(directory) / "source.step"
            path.write_bytes(original)
            self.assertEqual(detect_step_encoding(path), "gbk")
            with prepared_step_stream(path) as stream:
                self.assertEqual(stream.read(), text.encode("utf-8"))
            self.assertTrue(stream.closed)
            self.assertEqual(path.read_bytes(), original)
            path.write_bytes(text.encode("utf-8"))
            self.assertEqual(detect_step_encoding(path), "utf-8")

    def test_stream_is_closed_after_reader_failure(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.step"
            original = "'主轴模块';".encode("gbk")
            path.write_bytes(original)
            with self.assertRaisesRegex(RuntimeError, "reader failed"):
                with prepared_step_stream(path) as stream:
                    raise RuntimeError("reader failed")
            self.assertTrue(stream.closed)
            self.assertEqual(path.read_bytes(), original)

    def test_unknown_or_truncated_encoding_fails_without_replacing_characters(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.step"
            original = b"ISO-10303-21; 'broken \x81"
            path.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "STEP"):
                with prepared_step_stream(path):
                    self.fail("Invalid text must not reach the reader")
            self.assertEqual(path.read_bytes(), original)

    def test_ascii_prefix_does_not_hide_gbk_names_after_the_sample(self):
        text = "ISO-10303-21;\r\n/*" + "x" * 70000 + "*/\r\n'主轴模块╱组';"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.step"
            original = text.encode("gbk")
            path.write_bytes(original)
            self.assertEqual(detect_step_encoding(path), "utf-8")
            with prepared_step_stream(path) as stream:
                self.assertEqual(stream.read(), text.encode("utf-8"))
            self.assertEqual(path.read_bytes(), original)

    def test_sample_can_end_inside_utf8_or_gbk_characters(self):
        with TemporaryDirectory() as directory, patch("app.models.step_encoding._SAMPLE_SIZE", 1):
            path = Path(directory) / "source.step"
            for encoding in ("utf-8", "gbk"):
                with self.subTest(encoding=encoding):
                    path.write_bytes("主轴模块╱组".encode(encoding))
                    with prepared_step_stream(path) as stream:
                        self.assertEqual(stream.read(), "主轴模块╱组".encode("utf-8"))

    def test_real_step_assembly_names_in_gbk_utf8_and_unicode_escapes(self):
        document = new_document()
        tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        part = tool.AddShape(BRepPrimAPI_MakeBox(5, 6, 7).Shape(), False, False)
        root = tool.NewShape()
        left = tool.AddComponent(root, part, TopLoc_Location())
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(20, 0, 0))
        right = tool.AddComponent(root, part, TopLoc_Location(transform))
        names = {"ENCODING_ROOT": "主轴模块╱组", "ENCODING_LEFT": "主轴上盖组件", "ENCODING_RIGHT": "探针密封组件"}
        for label, placeholder in ((root, "ENCODING_ROOT"), (left, "ENCODING_LEFT"), (right, "ENCODING_RIGHT")):
            TDataStd_Name.Set_s(label, TCollection_ExtendedString(placeholder, True))
        tool.UpdateAssemblies()

        with TemporaryDirectory() as directory:
            path = Path(directory) / "original-name.step"
            writer = STEPCAFControl_Writer()
            writer.SetNameMode(True)
            self.assertTrue(writer.Transfer(document, STEPControl_AsIs))
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            baseline = path.read_bytes()
            _, baseline_appearance, baseline_metadata = read_step_model(path, lambda *args, **kwargs: None, include_entities=True)
            baseline_count = len(EntityTree(baseline_metadata).leaves)
            for encoding in ("gbk", "utf-8", "escaped"):
                with self.subTest(encoding=encoding):
                    payload = baseline
                    for placeholder, name in names.items():
                        self.assertIn(placeholder.encode("ascii"), baseline)
                        replacement = (b"\\X2\\" + name.encode("utf-16-be").hex().upper().encode("ascii") + b"\\X0\\"
                                       if encoding == "escaped" else name.encode(encoding))
                        payload = payload.replace(placeholder.encode("ascii"), replacement)
                    path.write_bytes(payload)
                    shape, appearance, metadata = read_step_model(path, lambda *args, **kwargs: None, include_entities=True)
                    tree = EntityTree(metadata)
                    self.assertFalse(shape.IsNull())
                    self.assertEqual(len(tree.leaves), baseline_count)
                    self.assertTrue(set(names.values()) <= {node["name"] for node in tree.nodes.values()})
                    self.assertEqual(metadata["root"]["name"], path.stem)
                    self.assertEqual(appearance, baseline_appearance)
                    self.assertEqual(path.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
