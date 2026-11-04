import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property string page_title: "你的建模工作台"
    property string subtitle_text: "创建模型、调整尺寸，专注每一次构建。"
    property bool has_model: false
    signal new_requested()
    signal export_requested()
    implicitHeight: 78
    opacity: 0
    Component.onCompleted: opacity = 1
    Behavior on opacity { NumberAnimation { duration: 220 } }

    RowLayout {
        anchors.fill: parent
        spacing: 14
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Label { text: "WORKSPACE / 工作空间"; color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.5 }
            Label {
                text: root.page_title
                color: Theme.ink
                font.pixelSize: 29
                font.weight: Font.Bold
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Label { text: root.subtitle_text; color: Theme.muted; font.pixelSize: 12 }
        }
        Button {
            id: export_button
            objectName: "header_export_button"
            text: "导出 STEP  ↗"
            enabled: root.has_model
            implicitHeight: 42
            leftPadding: 18
            rightPadding: 18
            onClicked: root.export_requested()
            background: Rectangle {
                radius: 11
                color: export_button.hovered ? Theme.surface_muted : Theme.surface
                border.color: Theme.line
                Behavior on color { ColorAnimation { duration: 150 } }
            }
            contentItem: Label { text: export_button.text; color: export_button.enabled ? Theme.ink : Theme.muted; font.pixelSize: 12; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        }
        Button {
            id: new_button
            objectName: "new_model_button"
            text: "＋  新建模型"
            implicitHeight: 42
            leftPadding: 18
            rightPadding: 18
            onClicked: root.new_requested()
            background: Rectangle {
                radius: 11
                color: new_button.down ? Theme.primary_hover : new_button.hovered ? "#6654d5" : Theme.primary
                Behavior on color { ColorAnimation { duration: 150 } }
            }
            contentItem: Label { text: new_button.text; color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        }
    }
}
