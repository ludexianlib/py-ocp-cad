pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    signal help_requested()
    signal page_requested(string page_name)
    property string active_page: "cad"

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
            model: [
                { page_name: "cad", title: "CAD 工作台", object_name: "nav_workbench" },
                { page_name: "point_cloud", title: "点云工作台", object_name: "nav_point_cloud" }
            ]
            delegate: Button {
                id: nav_button
                required property var modelData
                readonly property bool selected: root.active_page === modelData.page_name
                objectName: modelData.object_name
                Layout.fillWidth: true
                implicitHeight: 46
                onClicked: root.page_requested(modelData.page_name)
                background: Rectangle {
                    radius: 12
                    color: nav_button.selected ? Theme.primary : nav_button.hovered ? Theme.sidebar_hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 160 } }
                }
                contentItem: RowLayout {
                    spacing: 11
                    Canvas {
                        Layout.preferredWidth: 20
                        Layout.preferredHeight: 20
                        property bool is_selected: nav_button.selected
                        onIs_selectedChanged: requestPaint()
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.reset()
                            ctx.strokeStyle = is_selected ? "#ffffff" : "#b0aacd"
                            ctx.fillStyle = ctx.strokeStyle
                            ctx.lineWidth = 1.3
                            if (nav_button.modelData.page_name === "cad") {
                                ctx.strokeRect(2, 2, 6, 6); ctx.strokeRect(12, 2, 6, 6)
                                ctx.strokeRect(2, 12, 6, 6); ctx.strokeRect(12, 12, 6, 6)
                            } else {
                                for (let row = 0; row < 3; row++)
                                    for (let column = 0; column < 3; column++) {
                                        ctx.beginPath(); ctx.arc(4 + column * 6, 4 + row * 6, 1.4, 0, Math.PI * 2); ctx.fill()
                                    }
                            }
                        }
                    }
                    Label { text: nav_button.modelData.title; color: nav_button.selected ? "#ffffff" : "#b0aacd"; font.pixelSize: 13; font.weight: Font.DemiBold; Layout.fillWidth: true }
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
