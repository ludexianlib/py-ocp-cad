pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    signal help_requested()

    color: Theme.sidebar
    opacity: 0
    Component.onCompleted: opacity = 1
    Behavior on opacity { NumberAnimation { duration: 200 } }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 10

        RowLayout {
            Layout.topMargin: 14
            Layout.bottomMargin: 39
            spacing: 12
            Grid {
                columns: 2
                spacing: 3
                Repeater {
                    model: ["#ffffff", "#ffffff", "#ffffff", "#ffcc00"]
                    Rectangle { required property string modelData; width: 10; height: 10; radius: 3; color: modelData }
                }
            }
            ColumnLayout {
                spacing: 2
                Label { text: "CAD STUDIO"; color: "white"; font.pixelSize: 14; font.weight: Font.DemiBold; font.letterSpacing: 0.5 }
                Label { text: "你的几何工作空间"; color: "#9292aa"; font.pixelSize: 10 }
            }
        }

        Label { text: "WORKSPACE"; color: "#818198"; font.pixelSize: 10; font.letterSpacing: 1.5; Layout.leftMargin: 12; Layout.bottomMargin: 6 }
        Rectangle {
            objectName: "nav_workbench"
            Layout.fillWidth: true
            implicitHeight: 46
            radius: 12
            color: Theme.primary
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 11
                Canvas {
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20
                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.reset()
                        ctx.strokeStyle = "#ffffff"
                        ctx.lineWidth = 1.3
                        ctx.lineJoin = "round"
                        ctx.beginPath()
                        ctx.rect(2, 2, 6, 6); ctx.rect(12, 2, 6, 6)
                        ctx.rect(2, 12, 6, 6); ctx.rect(12, 12, 6, 6)
                        ctx.stroke()
                    }
                }
                Label {
                    text: "工作台"
                    color: "#ffffff"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
            }
        }

        Item { Layout.fillHeight: true }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 76
            radius: 14
            color: "#30304b"
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 13
                spacing: 6
                RowLayout {
                    spacing: 6
                    Rectangle { implicitWidth: 5; implicitHeight: 5; radius: 3; color: "#a8c45c" }
                    Label { text: "本地工作空间"; color: "#e2e0ef"; font.pixelSize: 11 }
                }
                Label { text: "当前会话 · 本地运行"; color: "#9090a8"; font.pixelSize: 10 }
            }
        }
        Button {
            id: help_button
            objectName: "help_button"
            Layout.fillWidth: true
            Layout.topMargin: 8
            implicitHeight: 40
            text: "操作指南"
            onClicked: root.help_requested()
            background: Rectangle { radius: 10; color: help_button.hovered ? Theme.sidebar_hover : "transparent"; Behavior on color { ColorAnimation { duration: 150 } } }
            contentItem: Label { text: "ⓘ   " + help_button.text; color: "#a4a4bb"; font.pixelSize: 12; leftPadding: 10; verticalAlignment: Text.AlignVCenter }
        }
    }
}
