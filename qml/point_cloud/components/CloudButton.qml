import QtQuick
import QtQuick.Controls
import "../../components"

Button {
    id: root
    property bool primary: false
    implicitHeight: 40
    leftPadding: 18
    rightPadding: 18
    background: Rectangle {
        radius: 11
        color: !root.enabled ? "#e0dced" : root.primary ? (root.hovered ? Theme.primary_hover : Theme.primary) : (root.hovered ? Theme.primary_soft : Theme.surface)
        border.color: root.primary ? "transparent" : Theme.line
        Behavior on color { ColorAnimation { duration: 150 } }
    }
    contentItem: Label {
        text: root.text
        color: !root.enabled ? Theme.muted : root.primary ? "white" : Theme.primary
        font.pixelSize: 12
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
