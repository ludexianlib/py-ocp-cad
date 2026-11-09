import QtQuick
import QtQuick.Controls

ToolTip {
    id: root
    objectName: "app_tooltip"
    delay: 600
    timeout: 5000
    padding: 9
    font.family: Theme.font_family
    font.pixelSize: 11
    implicitWidth: Math.min(280, contentItem.implicitWidth + leftPadding + rightPadding)
    implicitHeight: contentItem.implicitHeight + topPadding + bottomPadding
    contentItem: Label {
        text: root.text
        font: root.font
        color: Theme.ink
        wrapMode: Text.Wrap
    }
    background: Rectangle {
        radius: 8
        color: Theme.surface
        border.color: Theme.line
    }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140 }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 140; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 110 } }
}
