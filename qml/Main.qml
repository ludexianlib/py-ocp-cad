pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "components"

ApplicationWindow {
    id: root
    objectName: "workbench_window"
    required property var cad_controller
    required property url documents_folder
    width: 1360
    height: 900
    minimumWidth: 1080
    minimumHeight: 760
    visible: true
    title: "CAD Studio · 几何工作空间"
    color: Theme.background
    font.family: Theme.font_family

    function start_new_model() {
        Qt.callLater(() => box_panel.start_new_model())
    }
    function show_notice(message, is_error) {
        toast_manager.show_toast(message, is_error)
    }

    Connections {
        target: root.cad_controller
        function onNotice_requested(message, is_error) {
            root.show_notice(message, is_error)
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Sidebar {
            Layout.preferredWidth: 190
            Layout.minimumWidth: 190
            Layout.maximumWidth: 190
            Layout.fillHeight: true
            onHelp_requested: help_dialog.open()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
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
                        }
                        Flickable {
                            id: settings_scroll
                            Layout.preferredWidth: 292
                            Layout.minimumWidth: 280
                            Layout.maximumWidth: 308
                            Layout.fillHeight: true
                            clip: true
                            contentWidth: width
                            contentHeight: Math.max(settings_column.implicitHeight, height)
                            boundsBehavior: Flickable.StopAtBounds
                            flickableDirection: Flickable.VerticalFlick
                            ScrollBar.vertical: ScrollBar { }

                            ColumnLayout {
                                id: settings_column
                                width: settings_scroll.width
                                height: Math.max(implicitHeight, settings_scroll.height)
                                spacing: 20
                                BoxPanel {
                                    id: box_panel
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.minimumHeight: 404
                                    Layout.preferredHeight: 404
                                    active_model: root.cad_controller.active_model
                                    enter_delay: 140
                                    onCreate_requested: (length, width, height) => root.cad_controller.create_box(length, width, height)
                                }
                                Card {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 176
                                    Layout.minimumHeight: 176
                                    padding: 20
                                    color: Theme.primary
                                    border.width: 0
                                    enter_delay: 200
                                    ColumnLayout {
                                        anchors.fill: parent
                                        spacing: 7
                                        Label { text: "让想法，成为作品。"; color: "white"; font.pixelSize: 18; font.weight: Font.DemiBold }
                                        Label { text: "保存为 STEP，继续你的下一步。"; color: "#c5bdf0"; font.pixelSize: 10 }
                                        Item { Layout.fillHeight: true }
                                        Button {
                                            id: quick_export_button
                                            Layout.fillWidth: true
                                            implicitHeight: 36
                                            enabled: root.cad_controller.has_model
                                            onClicked: save_dialog.open()
                                            background: Rectangle { radius: 9; color: quick_export_button.hovered ? "#ffdb4d" : Theme.yellow; Behavior on color { ColorAnimation { duration: 150 } } }
                                            contentItem: Label { text: "导出当前模型    ↗"; color: Theme.ink; font.pixelSize: 11; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    ToastManager {
        id: toast_manager
        objectName: "toast_manager"
        parent: Overlay.overlay
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.topMargin: 20
        width: Math.max(0, Math.min(480, parent.width - 48))
        z: 1000
    }

    LoadingDialog {
        loading: root.cad_controller.loading
        filename: root.cad_controller.loading_filename
        stage_text: root.cad_controller.loading_stage
        elapsed_seconds: root.cad_controller.loading_elapsed_seconds
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
            Label { text: "工作区支持三维旋转、平移和缩放，可切换等轴测、正视和俯视。左键拖动旋转，右键或中键拖动平移，滚轮缩放，双击适配模型。"; font.pixelSize: 12; color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
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
