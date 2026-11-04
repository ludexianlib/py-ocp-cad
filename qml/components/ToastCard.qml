pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    required property string message_text
    required property bool is_error
    required property double expires_at
    property int toast_id: 0
    property bool is_closing: false
    property real slide_offset: -20
    readonly property int exit_duration: 160
    signal dismissed(var toast)

    objectName: "toast_" + toast_id
    implicitHeight: Math.max(48, message_label.implicitHeight + 28)
    height: implicitHeight
    radius: 13
    color: is_error ? "#fff1f3" : Theme.surface
    border.color: is_error ? "#f4d6dd" : Theme.line
    opacity: 0
    visible: opacity > 0
    transform: Translate { y: root.slide_offset }

    function dismiss() {
        if (root.is_closing)
            return
        root.is_closing = true
        expiry_timer.stop()
        enter_animation.stop()
        exit_animation.start()
    }

    Component.onCompleted: {
        enter_animation.start()
        expiry_timer.start()
    }

    Behavior on y {
        NumberAnimation { duration: 220; easing.type: Easing.OutCubic }
    }

    Rectangle {
        objectName: "toast_status_dot"
        x: 18
        anchors.verticalCenter: parent.verticalCenter
        width: 8
        height: 8
        radius: 4
        color: root.is_error ? Theme.error : Theme.green
    }

    Label {
        id: message_label
        objectName: "toast_message"
        x: 40
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, root.width - 58)
        text: root.message_text
        textFormat: Text.PlainText
        font.family: Theme.font_family
        font.pixelSize: 12
        color: Theme.ink
        wrapMode: Text.Wrap
        maximumLineCount: 3
        elide: Text.ElideRight
    }

    Timer {
        id: expiry_timer
        interval: Math.max(1, root.expires_at - Date.now() - root.exit_duration)
        onTriggered: root.dismiss()
    }

    ParallelAnimation {
        id: enter_animation
        NumberAnimation { target: root; property: "slide_offset"; from: -20; to: 0; duration: 220; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "opacity"; from: 0; to: 1; duration: 180; easing.type: Easing.OutCubic }
    }

    ParallelAnimation {
        id: exit_animation
        NumberAnimation { target: root; property: "slide_offset"; to: -12; duration: root.exit_duration; easing.type: Easing.InCubic }
        NumberAnimation { target: root; property: "opacity"; to: 0; duration: root.exit_duration; easing.type: Easing.InCubic }
        onFinished: root.dismissed(root)
    }
}
