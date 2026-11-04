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
    property int current_page: 0
    width: 1360
    height: 900
    minimumWidth: 1080
    minimumHeight: 760
    visible: true
    title: "CAD Studio · 几何工作空间"
    color: Theme.background
    font.family: Theme.font_family

    function start_new_model() {
        root.current_page = 0
        Qt.callLater(() => box_panel.start_new_model())
    }
    function show_notice(message, is_error) {
        toast_manager.show_toast(message, is_error)
    }
    onCurrent_pageChanged: page_transition.restart()

    Connections {
        target: root.cad_controller
        function onState_changed() {
            root.show_notice(root.cad_controller.status_text, root.cad_controller.last_error.length > 0)
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
            active_index: root.current_page
            model_count: root.cad_controller.model_count
            onNavigate_requested: page_index => root.current_page = page_index
            onHelp_requested: help_dialog.open()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.surface
            Flickable {
                id: page_scroll
                anchors.fill: parent
                clip: true
                contentWidth: width
                contentHeight: Math.max(page_column.implicitHeight + 64, height)
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                ScrollBar.vertical: ScrollBar { }

                ColumnLayout {
                    id: page_column
                    x: 34
                    y: 30
                    width: page_scroll.width - 68
                    height: Math.max(0, page_scroll.height - 64)
                    spacing: 22
                    transform: Translate { id: page_slide; x: 0 }

                    CadToolbar {
                        Layout.fillWidth: true
                        Layout.minimumHeight: implicitHeight
                        page_title: root.current_page === 0 ? "你的建模工作台" : "我的模型库"
                        subtitle_text: root.current_page === 0 ? "创建模型、调整尺寸，专注每一次构建。" : "当前会话中的每一个想法，都在这里。"
                        has_model: root.cad_controller.has_model
                        onNew_requested: root.start_new_model()
                        onExport_requested: save_dialog.open()
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumHeight: implicitHeight
                        spacing: 11
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "工作空间概览"; font.pixelSize: 11; color: Theme.muted; Layout.fillWidth: true }
                            Label { text: "当前会话  /  默认单位 mm"; font.pixelSize: 10; color: "#aaa8b8" }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 16
                            MetricCard {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 104
                                label_text: "模型数量"
                                value_text: root.cad_controller.model_count < 10 ? "0" + root.cad_controller.model_count : String(root.cad_controller.model_count)
                                unit_text: "个模型"
                                accent_color: Theme.primary
                                icon_kind: 0
                                enter_delay: 30
                            }
                            MetricCard {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 104
                                label_text: "当前模型体积"
                                value_text: Theme.format_number(root.cad_controller.active_model.volume, 0)
                                unit_text: "mm³"
                                accent_color: Theme.orange
                                icon_kind: 1
                                enter_delay: 70
                            }
                            MetricCard {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 104
                                label_text: "当前模型表面积"
                                value_text: Theme.format_number(root.cad_controller.active_model.surface_area, 0)
                                unit_text: "mm²"
                                accent_color: "#e4b200"
                                icon_kind: 2
                                enter_delay: 110
                            }
                        }
                    }

                    RowLayout {
                        visible: root.current_page === 0
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 600
                        Layout.preferredHeight: 600
                        spacing: 20
                        ViewportPanel {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 404
                            cad_controller: root.cad_controller
                            active_model: root.cad_controller.active_model
                            enter_delay: 100
                        }
                        ColumnLayout {
                            Layout.preferredWidth: 292
                            Layout.minimumWidth: 280
                            Layout.maximumWidth: 308
                            Layout.fillHeight: true
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

                    Card {
                        visible: root.current_page === 1
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(280, 85 + root.cad_controller.model_count * 72)
                        Layout.minimumHeight: Layout.preferredHeight
                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 12
                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "当前会话"; color: Theme.ink; font.pixelSize: 19; font.weight: Font.DemiBold; Layout.fillWidth: true }
                                Label { text: root.cad_controller.model_count + " 个模型"; color: Theme.muted; font.pixelSize: 11 }
                            }
                            Repeater {
                                model: root.cad_controller.models
                                Button {
                                    id: library_button
                                    required property var modelData
                                    objectName: "library_" + modelData.model_id
                                    readonly property bool is_active: root.cad_controller.active_model.model_id === modelData.model_id
                                    Layout.fillWidth: true
                                    implicitHeight: 60
                                    leftPadding: 16
                                    rightPadding: 16
                                    onClicked: root.cad_controller.select_model(modelData.model_id)
                                    background: Rectangle {
                                        radius: 12
                                        color: library_button.is_active ? Theme.primary_soft : library_button.hovered ? Theme.surface_muted : "white"
                                        border.color: library_button.is_active ? "#e1daf9" : Theme.line
                                        Behavior on color { ColorAnimation { duration: 140 } }
                                    }
                                    contentItem: RowLayout {
                                        spacing: 14
                                        Label { text: "◇"; color: Theme.primary; font.pixelSize: 28 }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 5
                                            Label { text: library_button.modelData.name; font.pixelSize: 13; font.weight: Font.DemiBold; color: Theme.ink }
                                            Label { text: library_button.modelData.dimensions_text; font.pixelSize: 11; color: Theme.muted }
                                        }
                                        Label { text: Theme.format_number(library_button.modelData.volume, 2) + " mm³"; font.pixelSize: 12; color: Theme.primary }
                                        Label { text: library_button.modelData.created_time; font.pixelSize: 11; color: Theme.muted; Layout.leftMargin: 18 }
                                        Label { text: library_button.is_active ? "当前模型" : "选择模型"; font.pixelSize: 10; color: library_button.is_active ? Theme.primary : Theme.muted; Layout.leftMargin: 18 }
                                    }
                                }
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.minimumHeight: implicitHeight
                        Label { text: "CAD STUDIO"; font.pixelSize: 9; font.letterSpacing: 1.8; color: "#b4afc4"; Layout.fillWidth: true }
                        Label { text: "本地会话 · 导出模型以保存你的构建"; font.pixelSize: 9; color: "#b4afc4" }
                    }
                }
            }
        }
    }

    ParallelAnimation {
        id: page_transition
        NumberAnimation { target: page_slide; property: "x"; from: -48; to: 0; duration: 280; easing.type: Easing.OutCubic }
        NumberAnimation { target: page_column; property: "opacity"; from: 0; to: 1; duration: 280; easing.type: Easing.OutCubic }
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
            Label { text: "在参数卡片中输入尺寸，点击创建模型。模型库可以切换当前会话中的模型。"; font.pixelSize: 12; color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
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
