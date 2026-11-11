pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../components"
import "components"

Item {
    id: root
    required property var cad_controller
    required property url documents_folder
    property bool active: true
    signal notice_requested(string message, bool is_error)
    visible: active || opacity > 0
    enabled: active
    opacity: active ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 180 } }

    function open_help() { help_dialog.open() }
    function start_new_model() {
        Qt.callLater(() => {
            settings_scroll.contentY = Math.min(box_panel.y, settings_scroll.contentHeight - settings_scroll.height)
            box_panel.start_new_model()
        })
    }
    Connections {
        target: root.cad_controller
        function onNotice_requested(message, is_error) {
            root.notice_requested(message, is_error)
        }
    }
        Rectangle {
            anchors.fill: parent
            color: Theme.surface
            Item {
                id: workbench_container
                anchors.fill: parent
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 34
                    anchors.rightMargin: 34
                    anchors.topMargin: 30
                    anchors.bottomMargin: 30
                    spacing: 22

                    CadToolbar {
                        Layout.fillWidth: true
                        Layout.minimumHeight: implicitHeight
                        has_model: root.cad_controller.has_model
                        loading: root.cad_controller.loading
                        onNew_requested: root.start_new_model()
                        onExport_requested: save_dialog.open()
                        onImport_requested: import_dialog.open()
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 20
                        ViewportPanel {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 404
                            cad_controller: root.cad_controller
                            active_model: root.cad_controller.active_model
                            enter_delay: 100
                            onContext_menu_requested: (source_item, mouse_x, mouse_y) => entity_menu.open_at(source_item, mouse_x, mouse_y)
                        }
                        Flickable {
                            id: settings_scroll
                            Layout.preferredWidth: 292
                            Layout.minimumWidth: 280
                            Layout.maximumWidth: 308
                            Layout.fillHeight: true
                            clip: true
                            contentWidth: width
                            contentHeight: Math.max(entity_panel.Layout.minimumHeight + settings_column.spacing + box_panel.implicitHeight, height)
                            boundsBehavior: Flickable.StopAtBounds
                            flickableDirection: Flickable.VerticalFlick
                            ScrollBar.vertical: ScrollBar { }

                            ColumnLayout {
                                id: settings_column
                                width: settings_scroll.width
                                height: settings_scroll.contentHeight
                                spacing: 20
                                EntityTreePanel {
                                    id: entity_panel
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.preferredHeight: 320
                                    Layout.minimumHeight: 260
                                    cad_controller: root.cad_controller
                                    enter_delay: 120
                                    onContext_menu_requested: (source_item, mouse_x, mouse_y) => entity_menu.open_at(source_item, mouse_x, mouse_y)
                                }
                                BoxPanel {
                                    id: box_panel
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: implicitHeight
                                    Layout.preferredHeight: implicitHeight
                                    Layout.maximumHeight: implicitHeight
                                    active_model: root.cad_controller.active_model
                                    enter_delay: 140
                                    onCreate_requested: (length, width, height) => root.cad_controller.create_box(length, width, height)
                                }
                            }
                        }
                    }
                }
            }
        }
    EntityContextMenu {
        id: entity_menu
        parent: Overlay.overlay
        cad_controller: root.cad_controller
    }

    FileDialog {
        id: import_dialog
        objectName: "step_import_dialog"
        title: "导入 STEP 模型"
        fileMode: FileDialog.OpenFile
        currentFolder: root.documents_folder
        nameFilters: ["STEP 模型 (*.step *.stp *.STEP *.STP)"]
        onAccepted: root.cad_controller.import_step(selectedFile)
    }

    FileDialog {
        id: save_dialog
        title: "导出 STEP 模型"
        fileMode: FileDialog.SaveFile
        currentFolder: root.documents_folder
        defaultSuffix: "step"
        nameFilters: ["STEP 模型 (*.step *.stp)"]
        onAccepted: root.cad_controller.export_step(selectedFile)
    }

    Dialog {
        id: help_dialog
        objectName: "help_dialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 440
        modal: true
        padding: 26
        background: Rectangle { color: Theme.surface; radius: 22; border.color: Theme.line }
        header: Label { text: "工作台指南"; font.pixelSize: 21; font.weight: Font.DemiBold; color: Theme.ink; leftPadding: 26; topPadding: 24 }
        contentItem: ColumnLayout {
            spacing: 16
            Label { text: "01  创建几何"; font.pixelSize: 13; font.weight: Font.DemiBold; color: Theme.primary }
            Label { text: "在参数卡片中输入尺寸，点击创建模型；也可以通过顶部按钮导入 STEP 模型。"; font.pixelSize: 12; color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { text: "02  保存作品"; font.pixelSize: 13; font.weight: Font.DemiBold; color: Theme.primary }
            Label { text: "当前会话的模型在关闭程序后清空。需要保留的模型，请先导出为 STEP 文件。"; font.pixelSize: 12; color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { text: "03  三维预览"; font.pixelSize: 13; font.weight: Font.DemiBold; color: Theme.primary }
            Label { text: "左键单击选择，Ctrl + 单击多选，左键拖动旋转，右键拖动平移，滚轮缩放，双击适配。实体树和预览区支持右键显隐菜单；导出始终保存完整模型。"; font.pixelSize: 12; color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
        footer: Item {
            implicitHeight: 66
            Button {
                id: close_help_button
                anchors.right: parent.right
                anchors.rightMargin: 26
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 20
                text: "知道了"
                implicitWidth: 90
                implicitHeight: 36
                onClicked: help_dialog.close()
                background: Rectangle { radius: 9; color: close_help_button.hovered ? Theme.primary_hover : Theme.primary }
                contentItem: Label { text: close_help_button.text; color: "white"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
        }
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180 }
                NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 180; easing.type: Easing.OutCubic }
            }
        }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 140 } }
    }
}
