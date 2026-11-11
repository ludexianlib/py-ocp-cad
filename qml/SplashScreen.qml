pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"

Window {
    id: root
    objectName: "startup_splash"
    required property var startup_controller
    width: 540
    height: 330
    flags: Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"
    visible: false
    title: "CAD Studio · 正在启动"
    opacity: 0
    onVisibleChanged: {
        if (visible && !startup_controller.ready)
            enter_animation.start()
    }
    onClosing: {
        if (!startup_controller.ready)
            startup_controller.request_exit()
    }

    Rectangle {
        anchors.fill: parent
        radius: 22
        color: Theme.surface
        border.color: Theme.line
        clip: true
        Rectangle { anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 22; anchors.rightMargin: 22; height: 5; radius: 2; color: Theme.primary }
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 34
            spacing: 16
            RowLayout {
                spacing: 16
                Rectangle {
                    implicitWidth: 58; implicitHeight: 58; radius: 16; color: Theme.primary
                    Grid {
                        anchors.centerIn: parent
                        columns: 2
                        spacing: 4
                        Repeater {
                            model: ["white", "white", "white", "#ffcc00"]
                            Rectangle { required property string modelData; width: 13; height: 13; radius: 3; color: modelData }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Label { text: "CAD STUDIO"; color: Theme.ink; font.pixelSize: 27; font.weight: Font.Bold; font.letterSpacing: 1 }
                    Label { text: "几何与点云 · 同一个工作空间"; color: Theme.muted; font.pixelSize: 12 }
                }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Label { objectName: "startup_stage"; text: root.startup_controller.stage_text; color: root.startup_controller.failed ? Theme.error : Theme.ink; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                Label { objectName: "startup_percentage"; text: root.startup_controller.progress + "%"; color: Theme.primary; font.pixelSize: 13; font.weight: Font.DemiBold }
            }
            ProgressBar {
                id: progress_bar
                objectName: "startup_progress"
                Layout.fillWidth: true
                from: 0; to: 100
                value: root.startup_controller.progress
                implicitHeight: 7
                padding: 0
                background: Rectangle { implicitHeight: 7; radius: 4; color: Theme.primary_soft }
                contentItem: Item {
                    implicitHeight: 7
                    Rectangle { width: progress_bar.visualPosition * parent.width; height: parent.height; radius: 4; color: root.startup_controller.failed ? Theme.error : Theme.primary; Behavior on color { ColorAnimation { duration: 150 } } }
                }
            }
            Label {
                Layout.fillWidth: true
                text: root.startup_controller.failed ? root.startup_controller.error_text : "正在准备你的工作台，请稍候…"
                color: Theme.muted
                font.pixelSize: 11
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
            }
            Button {
                objectName: "startup_exit_button"
                text: "退出"
                visible: root.startup_controller.failed
                Layout.alignment: Qt.AlignRight
                implicitHeight: 34
                onClicked: root.startup_controller.request_exit()
                background: Rectangle { radius: 9; color: parent.hovered ? Theme.primary_hover : Theme.primary; Behavior on color { ColorAnimation { duration: 150 } } }
                contentItem: Label { text: parent.text; color: "white"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
        }
    }
    NumberAnimation { id: enter_animation; target: root; property: "opacity"; from: 0; to: 1; duration: 160 }
    SequentialAnimation {
        id: finish_animation
        PauseAnimation { duration: 140 }
        NumberAnimation { target: root; property: "opacity"; to: 0; duration: 180; easing.type: Easing.OutCubic }
        ScriptAction { script: root.startup_controller.finish_splash() }
    }
    Connections {
        target: root.startup_controller
        function onState_changed() {
            if (root.startup_controller.ready && !finish_animation.running) {
                enter_animation.stop()
                root.opacity = 1
                finish_animation.start()
            }
        }
    }
}
