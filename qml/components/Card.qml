import QtQuick

Rectangle {
    id: root
    default property alias card_content: content_container.data
    property int padding: 24
    property int enter_delay: 0

    color: Theme.surface
    radius: Theme.card_radius
    border.width: 1
    border.color: Theme.line
    opacity: 0
    data: [
        Item {
            id: content_container
            anchors.fill: parent
            anchors.margins: root.padding
        }
    ]

    Component.onCompleted: enter_animation.start()
    SequentialAnimation {
        id: enter_animation
        PauseAnimation { duration: root.enter_delay }
        NumberAnimation { target: root; property: "opacity"; to: 1; duration: 260; easing.type: Easing.OutCubic }
    }
}
