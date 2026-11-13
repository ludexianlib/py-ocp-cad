pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import "../../components"

ComboBox {
    id: root
    property var disabled_indexes: []
    implicitHeight: 38
    leftPadding: 12
    rightPadding: 32
    font.pixelSize: 12
    background: Rectangle {
        color: root.enabled ? Theme.surface_muted : Theme.surface
        radius: 10
        border.color: root.activeFocus ? Theme.primary : Theme.line
        Behavior on border.color { ColorAnimation { duration: 150 } }
    }
    contentItem: Label {
        text: root.displayText
        color: root.enabled ? Theme.ink : Theme.muted
        font: root.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Label {
        text: "⌄"
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.muted
        rotation: root.popup.visible ? 180 : 0
        Behavior on rotation { NumberAnimation { duration: 140 } }
    }
    delegate: ItemDelegate {
        id: option
        required property int index
        required property string modelData
        width: root.width
        enabled: root.disabled_indexes.indexOf(index) < 0
        highlighted: root.highlightedIndex === index
        contentItem: Label { text: option.modelData; color: !option.enabled ? Theme.muted : Theme.ink; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 8; color: option.highlighted ? Theme.primary_soft : Theme.surface; Behavior on color { ColorAnimation { duration: 100 } } }
    }
    popup: Popup {
        y: root.height + 4
        width: root.width
        padding: 5
        implicitHeight: Math.min(contentItem.implicitHeight + padding * 2, 240)
        background: Rectangle { color: Theme.surface; radius: 11; border.color: Theme.line }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140 } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }
    }
}
