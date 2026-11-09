"""Real OCCT regression: python tests/test_viewport_visibility.py --render-check.

Set CAD_RUN_VIEWPORT_TESTS=1 to include it in unittest discovery. A separate
process keeps QGuiApplication/OpenGL isolated from the headless model tests.
"""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class ViewportVisibilityTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("CAD_RUN_VIEWPORT_TESTS") == "1", "Requires a desktop with OpenGL 4.1")
    def test_restored_entities_keep_shading_and_selection(self):
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--render-check"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=45,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("VISIBILITY_CHECK_OK", completed.stdout)


def render_check():
    import json
    from tempfile import TemporaryDirectory

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from PyQt6.QtCore import QEvent, QTimer, QUrl, qInstallMessageHandler
    from PyQt6.QtGui import QFont, QGuiApplication
    from PyQt6.QtQuick import QQuickItem
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from main import configure_graphics, create_engine
    from app.views.occt_renderer import OcctRenderer
    from test_entity_tree import assembly_document

    configure_graphics()
    application = QGuiApplication([])
    application.setFont(QFont("Microsoft YaHei UI", 10))
    latest = {}
    messages = []
    original_apply = OcctRenderer._apply_entity_state

    def observe(renderer):
        original_apply(renderer)
        manager = renderer._context.MainPrsMgr()
        # Inspect actual shaded presentations, rather than merely IsDisplayed.
        latest.update(snapshot=renderer._entity_snapshot,
                      shaded={node_id: manager.IsDisplayed(item, 1)
                              for node_id, item in renderer._presentations.items()},
                      displayed=sum(renderer._context.IsDisplayed(item) for item in renderer._presentations.values()),
                      highlighted=renderer._context.NbSelected())

    OcctRenderer._apply_entity_state = observe
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    engine, controller = create_engine(application)
    assert engine.rootObjects(), messages
    window = engine.rootObjects()[0]
    native = window.findChild(QQuickItem, "occt_viewport")
    state = {"case": 0, "step": 0, "cycles": 0, "ticks": 0, "checks": 0, "error": None}
    directory = TemporaryDirectory(prefix="cad-visibility-")
    document, tool, labels, shape = assembly_document()
    source = Path(directory.name) / "colored-assembly.step"
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    assert writer.Transfer(document, STEPControl_AsIs)
    assert writer.Write(str(source)) == IFSelect_RetDone

    def advance():
        state["ticks"] += 1
        try:
            assert state["ticks"] < 250, ("Rendering/import timeout", state, latest)
            assert not native.property("error_text"), native.property("error_text")
            if not native.property("render_ready") or controller.loading or controller._import_tasks:
                return
            assert not controller.last_error, controller.last_error
            snapshot = controller.active_entities.snapshot()
            if latest.get("snapshot") != snapshot:
                return
            visible_ids = {row[0] for row in snapshot if row[3]}
            for node_id in visible_ids:
                assert latest["shaded"].get(node_id), ("Entity restored without shading", state, latest)
            assert latest["displayed"] == len(visible_ids), (state, latest)
            assert latest["highlighted"] == sum(row[3] and row[4] for row in snapshot), (state, latest)
            state["checks"] += 1
            step = state["step"]
            if step == 0:
                leaves = list(controller.active_entities.leaves)
                controller.select_entity(leaves[0], False, False)
                if len(leaves) > 1:
                    controller.select_entity(leaves[1], True, False)
            elif step == 1:
                controller.hide_selected_entities()
            elif step == 2:
                controller.isolate_selected_entities()
            elif step == 3:
                controller.show_all_entities()
            elif step == 4:
                controller.select_entity("model", False, False)
                controller.hide_selected_entities()
            elif step == 5:
                controller.show_all_entities()
            elif step == 6:
                controller.select_entity("", False, False)
            else:
                state["cycles"] += 1
                if state["cycles"] < 3:
                    state["step"] = 0
                    return
                if state["case"] == 0:
                    assert controller.import_step(QUrl.fromLocalFile(str(source)))
                    state.update(case=1, cycles=0, step=0)
                    return
                assert not messages, messages
                print("VISIBILITY_CHECK_OK", json.dumps({"checks": state["checks"], "cases": 2,
                      "cycles_per_case": 3, "qt_messages": messages}), flush=True)
                timer.stop()
                application.quit()
                return
            state["step"] += 1
        except Exception as error:
            state["error"] = repr(error)
            timer.stop()
            application.quit()

    timer = QTimer()
    timer.setInterval(75)
    timer.timeout.connect(advance)
    timer.start()
    try:
        application.exec()
    finally:
        timer.stop()
        window.close()
        engine.deleteLater()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        OcctRenderer._apply_entity_state = original_apply
        directory.cleanup()
    if state["error"]:
        raise AssertionError(state["error"])


if __name__ == "__main__":
    if "--render-check" in sys.argv:
        render_check()
    else:
        unittest.main()
