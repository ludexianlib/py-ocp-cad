pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"

Card {
    id: root
    required property var cloud_controller
    readonly property bool running: cloud_controller.stream_running
    readonly property var status: cloud_controller.stream_status
    padding: 16
    implicitHeight: content.implicitHeight + padding * 2

    component StreamField: TextField {
        id: field
        implicitHeight: 36
        font.pixelSize: 12
        color: enabled ? Theme.ink : Theme.muted
        leftPadding: 12
        selectByMouse: true
        background: Rectangle {
            color: field.activeFocus ? Theme.surface : Theme.surface_muted
            radius: 10
            border.color: field.activeFocus ? Theme.primary : Theme.line
            Behavior on border.color { ColorAnimation { duration: 150 } }
        }
    }

    ColumnLayout {
        id: content
        anchors.fill: parent
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: "实时点云"; color: Theme.ink; font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
            Label {
                text: root.status.state === "connected" ? "已连接" : root.running ? "等待连接" : "未启动"
                color: root.running ? Theme.primary : Theme.muted
                font.pixelSize: 12
                Behavior on color { ColorAnimation { duration: 150 } }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Label { text: "监听地址"; color: Theme.muted; font.pixelSize: 12 }
            StreamField { id: host; objectName: "cloud_stream_host"; text: "127.0.0.1"; enabled: !root.running; Layout.fillWidth: true }
            Label { text: "端口"; color: Theme.muted; font.pixelSize: 12 }
            StreamField { id: port; objectName: "cloud_stream_port"; text: "8765"; enabled: !root.running; Layout.preferredWidth: 78; validator: IntValidator { bottom: 1; top: 65535 } }
            CloudButton {
                objectName: "cloud_stream_toggle"
                text: root.running ? "停止接收" : "开始接收"
                primary: !root.running
                enabled: !root.cloud_controller.loading && (root.running || (host.text.trim().length > 0 && port.acceptableInput))
                onClicked: {
                    if (root.running) root.cloud_controller.stop_stream()
                    else root.cloud_controller.start_stream(host.text.trim(), Number(port.text))
                }
            }
        }
        Label {
            Layout.fillWidth: true
            text: "接收 " + root.status.received + " 帧 · 跳过待显示帧 " + root.status.dropped + " · 拒绝 " + root.status.rejected + " 帧"
            color: Theme.muted; font.pixelSize: 11
        }
        Label {
            Layout.fillWidth: true
            text: root.status.error || ""
            visible: opacity > 0
            opacity: text.length ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 150 } }
            color: Theme.error; font.pixelSize: 11; wrapMode: Text.Wrap
        }
    }
}
