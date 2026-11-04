pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Cad.Native 1.0

Card {
    id: root
    required property var cad_controller
    property var active_model: ({})
    property string view_mode: "iso"
    readonly property bool has_model: !!root.active_model.model_id
    padding: 22

    function fit_view() { native_view.fit_view() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 14
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 5
                Label { text: "模型工作区"; color: Theme.ink; font.pixelSize: 19; font.weight: Font.DemiBold }
                Label { text: root.active_model.name || "等待创建模型"; color: Theme.muted; font.pixelSize: 11 }
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                implicitHeight: 33
                implicitWidth: view_controls.implicitWidth + 6
                radius: 10
                color: Theme.surface_muted
                Row {
                    id: view_controls
                    anchors.centerIn: parent
                    spacing: 2
                    Repeater {
                        model: [{key: "iso", label: "等轴测"}, {key: "front", label: "正视"}, {key: "top", label: "俯视"}]
                        Button {
                            id: view_button
                            required property var modelData
                            objectName: "view_" + modelData.key
                            readonly property bool is_active: root.view_mode === modelData.key
                            width: modelData.key === "iso" ? 62 : 48
                            height: 27
                            onClicked: {
                                root.view_mode = modelData.key
                                native_view.fit_view()
                            }
                            background: Rectangle {
                                radius: 8
                                color: view_button.is_active ? "white" : view_button.hovered ? "#eeebf7" : "transparent"
                                Behavior on color { ColorAnimation { duration: 140 } }
                            }
                            contentItem: Label { text: view_button.modelData.label; font.pixelSize: 10; color: view_button.is_active ? Theme.primary : Theme.muted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        }
                    }
                    Button {
                        id: fit_button
                        objectName: "view_fit"
                        text: "适配"
                        width: 48
                        height: 27
                        enabled: root.has_model && native_view.render_ready
                        onClicked: root.fit_view()
                        background: Rectangle {
                            radius: 8
                            color: fit_button.hovered ? "#eeebf7" : "transparent"
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }
                        contentItem: Label {
                            text: fit_button.text
                            font.pixelSize: 10
                            color: Theme.muted
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 15
            color: "#fbfaff"
            border.color: "#f0edf8"
            clip: true
            OcctViewport {
                id: native_view
                objectName: "occt_viewport"
                anchors.fill: parent
                anchors.margins: 8
                controller: root.cad_controller
                view_mode: root.view_mode
                onOrbit_started: root.view_mode = "free"
            }
            Label { anchors.top: parent.top; anchors.left: parent.left; anchors.margins: 15; text: "3D PREVIEW"; font.pixelSize: 8; font.letterSpacing: 1.8; color: "#aaa1bd" }
            Label { anchors.bottom: parent.bottom; anchors.right: parent.right; anchors.margins: 13; text: "单位 · mm"; font.pixelSize: 9; color: "#a79eb8" }
            Label {
                anchors.centerIn: parent
                width: parent.width - 48
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                opacity: !native_view.render_ready || !root.has_model ? 1 : 0
                visible: opacity > 0.001
                text: native_view.error_text || (!native_view.render_ready ? "正在加载三维预览…" : "创建一个模型，开始预览")
                font.pixelSize: 12
                color: native_view.error_text ? Theme.error : Theme.muted
                Behavior on opacity { NumberAnimation { duration: 180 } }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 7
            Rectangle {
                implicitWidth: 5; implicitHeight: 5; radius: 3
                color: native_view.error_text ? Theme.error : root.has_model && native_view.render_ready ? Theme.green : Theme.muted
                Behavior on color { ColorAnimation { duration: 150 } }
            }
            Label { text: native_view.error_text ? "预览加载失败" : !native_view.render_ready ? "正在加载预览" : root.has_model ? "三维模型已同步" : "等待模型"; color: Theme.muted; font.pixelSize: 10 }
            Item { Layout.fillWidth: true }
            Label { text: "左键旋转 · 右键平移 · 滚轮缩放 · 双击适配"; color: "#aaa4ba"; font.pixelSize: 9 }
        }
    }
}
