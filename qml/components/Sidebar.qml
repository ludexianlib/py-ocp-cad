pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property int active_index: 0
    property int model_count: 0
    signal navigate_requested(int page_index)
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
        Repeater {
            model: ["工作台", "模型库"]
            Button {
                id: navigation_button
                required property int index
                required property string modelData
                objectName: index === 0 ? "nav_workbench" : "nav_library"
                readonly property bool is_active: root.active_index === index
                Layout.fillWidth: true
                implicitHeight: 46
                onClicked: root.navigate_requested(index)
                background: Rectangle {
                    radius: 12
                    color: navigation_button.is_active ? Theme.primary : navigation_button.hovered ? Theme.sidebar_hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 150 } }
                }
                contentItem: RowLayout {
                    spacing: 11
                    Canvas {
                        Layout.preferredWidth: 20
                        Layout.preferredHeight: 20
                        opacity: navigation_button.is_active ? 1 : 0.65
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.reset()
                            ctx.strokeStyle = "#ffffff"
                            ctx.lineWidth = 1.3
                            ctx.lineJoin = "round"
                            ctx.beginPath()
                            if (navigation_button.index === 0) {
                                ctx.rect(2, 2, 6, 6); ctx.rect(12, 2, 6, 6)
                                ctx.rect(2, 12, 6, 6); ctx.rect(12, 12, 6, 6)
                            } else {
                                ctx.moveTo(10, 1); ctx.lineTo(18, 5.5); ctx.lineTo(18, 14.5)
                                ctx.lineTo(10, 19); ctx.lineTo(2, 14.5); ctx.lineTo(2, 5.5); ctx.closePath()
                                ctx.moveTo(2, 5.5); ctx.lineTo(10, 10); ctx.lineTo(18, 5.5)
                                ctx.moveTo(10, 10); ctx.lineTo(10, 19)
                            }
                            ctx.stroke()
                        }
                    }
                    Label {
                        text: navigation_button.modelData
                        color: navigation_button.is_active ? "#ffffff" : "#b5b5c8"
                        font.pixelSize: 13
                        font.weight: navigation_button.is_active ? Font.DemiBold : Font.Normal
                        Layout.fillWidth: true
                    }
                    Label {
                        visible: navigation_button.index === 1
                        text: String(root.model_count)
                        color: "#bdb6ef"
                        font.pixelSize: 11
                    }
                }
                leftPadding: 12
                rightPadding: 12
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
                Label { text: "当前会话 · " + root.model_count + " 个模型"; color: "#9090a8"; font.pixelSize: 10 }
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
