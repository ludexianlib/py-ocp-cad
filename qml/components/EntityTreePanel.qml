pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: root
    required property var cad_controller
    signal context_menu_requested(var source_item, real mouse_x, real mouse_y)
    objectName: "entity_tree_panel"
    padding: 16

    function reveal_entity(node_id) {
        reveal_scroll.stop()
        entity_list.cancelFlick()
        const row = root.cad_controller.entity_tree_model.reveal_node(node_id)
        if (row < 0) return
        entity_list.forceLayout()
        const previous_y = entity_list.contentY
        entity_list.positionViewAtIndex(row, ListView.Contain)
        const target_y = entity_list.contentY
        if (Math.abs(target_y - previous_y) < 0.5) return
        entity_list.contentY = previous_y
        reveal_scroll.from = previous_y
        reveal_scroll.to = target_y
        reveal_scroll.start()
    }

    Connections {
        target: root.cad_controller
        function onEntity_focus_requested(node_id) { root.reveal_entity(node_id) }
    }

    Connections {
        target: root.cad_controller.entity_tree_model
        function onModelAboutToBeReset() { reveal_scroll.stop() }
        function onRowsAboutToBeRemoved() { reveal_scroll.stop() }
    }

    NumberAnimation {
        id: reveal_scroll
        target: entity_list
        property: "contentY"
        duration: 180
        easing.type: Easing.OutCubic
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: "实体树"; font.pixelSize: 18; font.weight: Font.DemiBold; color: Theme.ink; Layout.fillWidth: true }
            Label { text: root.cad_controller.entity_count + " 个"; font.pixelSize: 10; color: Theme.muted }
            ToolButton {
                id: more_button
                objectName: "entity_tree_menu_button"
                implicitWidth: 28; implicitHeight: 26
                enabled: root.cad_controller.has_model && !root.cad_controller.loading
                onClicked: root.context_menu_requested(more_button, 0, more_button.height)
                background: Rectangle {
                    radius: 7
                    color: Theme.primary_soft
                    opacity: more_button.hovered && more_button.enabled ? 1 : 0.35
                    Behavior on opacity { NumberAnimation { duration: 120 } }
                }
                contentItem: EntityNodeIcon { icon_kind: "more"; opacity: more_button.enabled ? 1 : 0.5 }
                AppToolTip {
                    parent: more_button
                    visible: more_button.hovered && more_button.enabled
                    text: "实体操作"
                }
            }
        }
        Label {
            Layout.fillWidth: true
            text: !root.cad_controller.has_model ? "等待模型" : root.cad_controller.entity_tree_source === "assembly" ? "原始装配层级" : "按几何实体分组"
            color: Theme.muted
            font.pixelSize: 10
        }
        ListView {
            id: entity_list
            objectName: "entity_tree_list"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.rightMargin: -8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: root.cad_controller.entity_tree_model
            spacing: 3
            onMovementStarted: reveal_scroll.stop()
            ScrollBar.vertical: ScrollBar {
                objectName: "entity_tree_scrollbar"
                onPressedChanged: if (pressed) reveal_scroll.stop()
            }
            delegate: Rectangle {
                id: entity_row
                required property string node_id
                required property string node_name
                required property string node_kind
                required property int node_depth
                required property bool has_children
                required property bool is_expanded
                required property bool is_selected
                required property bool is_partial
                required property bool is_visible
                required property bool is_partly_visible
                objectName: "entity_row_" + node_id
                width: Math.max(0, entity_list.width - 8)
                height: 34
                radius: 8
                color: Theme.surface
                Rectangle {
                    objectName: "entity_row_highlight_" + entity_row.node_id
                    anchors.fill: parent
                    radius: parent.radius
                    color: Theme.primary_soft
                    opacity: entity_row.is_selected || entity_row.is_partial ? 1 : row_mouse.containsMouse ? 0.4 : 0
                    Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                }
                MouseArea {
                    id: row_mouse
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    enabled: !root.cad_controller.loading
                    onClicked: mouse => {
                        const context = mouse.button === Qt.RightButton
                        root.cad_controller.select_entity(entity_row.node_id, !context && !!(mouse.modifiers & Qt.ControlModifier), context)
                        if (context) root.context_menu_requested(entity_row, mouse.x, mouse.y)
                    }
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 4 + Math.min(entity_row.node_depth, 8) * 13
                    anchors.rightMargin: 8
                    spacing: 4
                    ToolButton {
                        id: expand_button
                        objectName: "entity_expand_" + entity_row.node_id
                        Layout.preferredWidth: 18
                        Layout.preferredHeight: 26
                        padding: 0
                        enabled: entity_row.has_children
                        onClicked: root.cad_controller.entity_tree_model.toggle_expanded(entity_row.node_id)
                        background: Rectangle {
                            radius: 5
                            color: Theme.primary_soft
                            opacity: expand_button.hovered && entity_row.has_children ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 120 } }
                        }
                        contentItem: EntityNodeIcon {
                            icon_kind: "chevron"
                            stroke_color: Theme.muted
                            visible: entity_row.has_children
                            rotation: entity_row.is_expanded ? 90 : 0
                            Behavior on rotation { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                        }
                    }
                    EntityNodeIcon {
                        Layout.preferredWidth: 15
                        Layout.preferredHeight: 15
                        icon_kind: entity_row.has_children ? "group" : "entity"
                        stroke_color: entity_row.is_visible ? Theme.primary : Theme.muted
                    }
                    Label {
                        Layout.fillWidth: true
                        text: entity_row.node_name
                        elide: Text.ElideRight
                        font.pixelSize: 11
                        color: !entity_row.is_visible ? Theme.muted : entity_row.is_selected || entity_row.is_partial ? Theme.primary : Theme.ink
                        opacity: entity_row.is_visible ? 1 : 0.55
                        Behavior on opacity { NumberAnimation { duration: 150 } }
                    }
                    Label {
                        text: !entity_row.is_visible ? "隐藏" : entity_row.is_partly_visible ? "部分" : ""
                        font.pixelSize: 9
                        color: Theme.muted
                    }
                    EntityNodeIcon {
                        Layout.preferredWidth: 11
                        Layout.preferredHeight: 11
                        visible: entity_row.is_visible && !entity_row.is_partly_visible && entity_row.is_partial
                        icon_kind: "partial"
                        stroke_color: Theme.primary
                    }
                }
                AppToolTip {
                    parent: entity_row
                    visible: row_mouse.containsMouse && !root.cad_controller.loading
                    text: entity_row.node_name + " · " + entity_row.node_kind
                }
            }
            add: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 160 } }
            remove: Transition { NumberAnimation { property: "opacity"; to: 0; duration: 120 } }
            displaced: Transition { NumberAnimation { properties: "x,y"; duration: 160; easing.type: Easing.OutCubic } }
        }
        Label {
            Layout.fillWidth: true
            text: root.cad_controller.selected_entity_count > 0 ? "已选 " + root.cad_controller.selected_entity_count + " 个 · 右键操作" : "Ctrl + 单击多选 · 右键操作"
            color: Theme.muted
            font.pixelSize: 10
        }
    }
}
