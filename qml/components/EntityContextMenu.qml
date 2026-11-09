pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls

Menu {
    id: root
    required property var cad_controller
    objectName: "entity_context_menu"
    width: 174
    padding: 6
    font.family: Theme.font_family
    font.pixelSize: 12

    function open_at(source_item, mouse_x, mouse_y) {
        const position = source_item.mapToItem(root.parent, mouse_x, mouse_y)
        root.popup(position.x, position.y)
    }

    background: Rectangle {
        radius: 12
        color: Theme.surface
        border.color: Theme.line
        Rectangle {
            z: -1
            x: -3; y: 3
            width: parent.width + 6; height: parent.height + 3
            radius: 14
            color: "#1025253f"
        }
    }

    component EntityAction: MenuItem {
        id: action_item
        implicitHeight: 36
        font.family: root.font.family
        font.pixelSize: 12
        leftPadding: 12
        rightPadding: 12
        contentItem: Label {
            text: action_item.text
            font: action_item.font
            color: !action_item.enabled ? Theme.muted : action_item.highlighted ? Theme.primary : Theme.ink
            opacity: action_item.enabled ? 1 : 0.5
            verticalAlignment: Text.AlignVCenter
            Behavior on color { ColorAnimation { duration: 120 } }
        }
        background: Rectangle {
            radius: 8
            color: Theme.primary_soft
            opacity: action_item.highlighted && action_item.enabled ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        }
    }

    EntityAction {
        objectName: "hide_selected_action"
        text: "隐藏选中"
        enabled: root.cad_controller.selected_entity_count > 0 && !root.cad_controller.loading
        onTriggered: root.cad_controller.hide_selected_entities()
    }
    EntityAction {
        objectName: "isolate_selected_action"
        text: "仅显示选中"
        enabled: root.cad_controller.selected_entity_count > 0 && !root.cad_controller.loading
        onTriggered: root.cad_controller.isolate_selected_entities()
    }
    MenuSeparator {
        leftPadding: 8; rightPadding: 8
        contentItem: Rectangle { implicitWidth: 144; implicitHeight: 1; color: Theme.line }
    }
    EntityAction {
        objectName: "show_all_entities_action"
        text: "显示全部"
        enabled: root.cad_controller.has_model && !root.cad_controller.loading
        onTriggered: root.cad_controller.show_all_entities()
    }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 150 }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 150; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 110 } }
}
