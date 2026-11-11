pragma ComponentBehavior: Bound
import QtQuick
import "../../components"
import QtQuick.Controls

Menu {
    id: root
    required property var cad_controller
    objectName: "entity_context_menu"
    width: 174
    padding: 6
    font.family: Theme.font_family
    font.pixelSize: 12
    property real slide_offset: 0

    function open_at(source_item, mouse_x, mouse_y) {
        const position = source_item.mapToItem(root.parent, mouse_x, mouse_y)
        root.popup(position.x, position.y)
    }

    contentItem: ListView {
        implicitHeight: contentHeight
        model: root.contentModel
        interactive: Window.window
                     ? contentHeight + root.topPadding + root.bottomPadding > root.height
                     : false
        clip: true
        currentIndex: root.currentIndex
        transform: Translate { y: root.slide_offset }

        ScrollIndicator.vertical: ScrollIndicator {}
    }

    background: Rectangle {
        id: menu_background
        radius: 12
        color: Theme.surface
        border.color: Theme.line
        transform: Translate { y: root.slide_offset }
        Canvas {
            anchors.fill: parent
            anchors.margins: -24
            z: -1
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                ctx.clearRect(0, 0, width, height)
                ctx.shadowColor = "rgba(37, 37, 63, 0.16)"
                ctx.shadowBlur = 16
                ctx.shadowOffsetY = 4
                ctx.fillStyle = menu_background.color
                ctx.beginPath()
                ctx.roundedRect(24, 24, menu_background.width, menu_background.height,
                                menu_background.radius, menu_background.radius)
                ctx.fill()
            }
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
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180; easing.type: Easing.OutCubic }
            NumberAnimation { target: root; property: "slide_offset"; from: -8; to: 0; duration: 180; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: 120; easing.type: Easing.InCubic } }
}
