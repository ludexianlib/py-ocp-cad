pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import PointCloud.Native 1.0
import "../components"
import "components"

Item {
    id: root
    objectName: "point_cloud_page"
    required property var cloud_controller
    required property url documents_folder
    property bool active: false
    property url pending_file
    signal notice_requested(string message, bool is_error)
    visible: active || opacity > 0
    enabled: active
    opacity: active ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 180 } }

    Connections {
        target: root.cloud_controller
        function onNotice_requested(message, is_error) { root.notice_requested(message, is_error) }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 30
        anchors.leftMargin: 34
        anchors.rightMargin: 34
        spacing: 22
        RowLayout {
            objectName: "cloud_toolbar"
            Layout.fillWidth: true
            Layout.preferredHeight: 78
            spacing: 14
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Label { text: "POINT CLOUD / 点云空间"; color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.5 }
                Label { text: "你的点云工作台"; color: Theme.ink; font.pixelSize: 29; font.weight: Font.Bold; Layout.fillWidth: true; elide: Text.ElideRight }
                Label { text: "导入三维点云，查看空间与色彩。"; color: Theme.muted; font.pixelSize: 12 }
            }
            CloudButton { objectName: "cloud_import_button"; text: "导入点云"; primary: true; enabled: !root.cloud_controller.loading && !root.cloud_controller.stream_running; onClicked: import_dialog.open() }
        }
        PointCloudConnectionPanel { Layout.fillWidth: true; cloud_controller: root.cloud_controller }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 20
            Card {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: 22
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 14
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: "点云预览"; color: Theme.ink; font.pixelSize: 19; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        CloudButton { text: "适配视图"; enabled: root.cloud_controller.has_cloud; onClicked: native_view.fit_view() }
                        CloudButton { text: "重置视角"; enabled: root.cloud_controller.has_cloud; onClicked: native_view.reset_camera() }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 15
                        color: "#efedfa"
                        border.color: "#dce3ee"
                        clip: true
                        PointCloudViewport {
                            id: native_view
                            objectName: "point_cloud_viewport"
                            anchors.fill: parent
                            anchors.margins: 8
                            controller: root.cloud_controller
                            active: root.active
                            Component.onDestruction: stop()
                        }
                        Column {
                            anchors.centerIn: parent
                            width: Math.min(380, parent.width - 48)
                            spacing: 12
                            visible: !root.cloud_controller.has_cloud || Boolean(native_view.error_text)
                            Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: native_view.error_text ? "点云预览失败" : root.cloud_controller.stream_running ? "等待有效点云" : root.cloud_controller.active_cloud.stream_id ? "当前帧没有有效点" : "导入你的第一份点云"; color: Theme.ink; font.pixelSize: 18; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
                            Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: native_view.error_text || (root.cloud_controller.stream_running ? "接收源需发送点云协议 v1 数据" : "支持 PLY、PCD、XYZ 格式"); color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
                        }
                        Label { anchors.top: parent.top; anchors.left: parent.left; anchors.margins: 14; text: "POINT CLOUD"; color: "#8f86a6"; font.pixelSize: 9; font.letterSpacing: 1.5 }
                    }
                    Label { text: native_view.error_text ? "预览加载失败" : root.cloud_controller.loading ? root.cloud_controller.stage_text : root.cloud_controller.has_cloud ? "点云已同步 · " + Theme.format_number(root.cloud_controller.active_cloud.point_count, 0) + " 个点" : root.cloud_controller.active_cloud.stream_id ? "当前扫描为空" : root.cloud_controller.stream_running ? "等待实时点云" : "等待导入点云"; color: native_view.error_text ? Theme.error : Theme.muted; font.pixelSize: 11 }
                }
            }
            Flickable {
                id: info_scroll
                Layout.preferredWidth: 270
                Layout.minimumWidth: 250
                Layout.fillHeight: true
                contentWidth: width
                contentHeight: Math.max(height, info_panel.implicitHeight)
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                ScrollBar.vertical: ScrollBar { }
                PointCloudInfoPanel { id: info_panel; width: info_scroll.width; height: info_scroll.contentHeight; cloud_controller: root.cloud_controller }
            }
        }
    }
    FileDialog {
        id: import_dialog
        objectName: "point_cloud_import_dialog"
        title: "导入三维点云"
        fileMode: FileDialog.OpenFile
        currentFolder: root.documents_folder
        nameFilters: ["点云文件 (*.ply *.pcd *.xyz *.PLY *.PCD *.XYZ)", "PLY 点云 (*.ply *.PLY)", "PCD 点云 (*.pcd *.PCD)", "XYZ 点云 (*.xyz *.XYZ)"]
        onAccepted: {
            root.pending_file = selectedFile
            source_unit.currentIndex = -1
            unit_dialog.open()
        }
    }
    Dialog {
        id: unit_dialog
        objectName: "cloud_unit_dialog"
        title: "选择源文件坐标单位"
        anchors.centerIn: parent
        modal: true
        width: 320
        closePolicy: Popup.CloseOnEscape
        background: Rectangle { color: Theme.surface; radius: 16; border.color: Theme.line }
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 160 } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 120 } }
        ColumnLayout {
            width: parent.width
            spacing: 14
            Label { text: "导入后统一换算为毫米。"; color: Theme.muted; font.pixelSize: 12 }
            CloudComboBox {
                id: source_unit
                objectName: "cloud_source_unit"
                Layout.fillWidth: true
                model: ["毫米 (mm)", "米 (m)"]
                currentIndex: -1
                displayText: currentIndex < 0 ? "请选择源单位" : currentText
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                CloudButton { text: "取消"; onClicked: unit_dialog.close() }
                CloudButton {
                    text: "导入"; primary: true; enabled: source_unit.currentIndex >= 0
                    onClicked: {
                        root.cloud_controller.import_cloud(root.pending_file, source_unit.currentIndex === 0 ? "mm" : "m")
                        unit_dialog.close()
                    }
                }
            }
        }
    }
}
