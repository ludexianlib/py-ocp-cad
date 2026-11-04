import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "model_loading_dialog"
    property bool loading: false
    property string filename: ""
    property string stage_text: "正在读取文件…"
    property int elapsed_seconds: 0

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(420, parent ? parent.width - 48 : 420)
    modal: true
    closePolicy: Popup.NoAutoClose
    padding: 26

    onLoadingChanged: {
        if (loading) open()
        else close()
    }
    Component.onCompleted: { if (loading) open() }

    background: Rectangle {
        radius: Theme.card_radius
        color: Theme.surface
        border.color: Theme.line
    }
    Overlay.modal: Rectangle {
        color: "#5525253f"
        Behavior on opacity { NumberAnimation { duration: 160 } }
    }

    contentItem: ColumnLayout {
        spacing: 16
        Label {
            text: "正在加载模型"
            color: Theme.ink
            font.pixelSize: 20
            font.weight: Font.DemiBold
        }
        Label {
            Layout.fillWidth: true
            text: root.filename
            textFormat: Text.PlainText
            elide: Text.ElideMiddle
            color: Theme.muted
            font.pixelSize: 12
        }
        ProgressBar {
            id: progress_bar
            objectName: "model_loading_progress"
            Layout.fillWidth: true
            Layout.topMargin: 4
            implicitHeight: 8
            indeterminate: root.loading
            background: Rectangle {
                radius: 4
                color: Theme.primary_soft
                antialiasing: true
            }
            contentItem: Item {
                clip: true
                implicitHeight: 8
                Rectangle {
                    id: progress_indicator
                    width: parent.width * 0.32
                    height: parent.height
                    radius: 4
                    color: Theme.primary
                    NumberAnimation on x {
                        from: -progress_indicator.width
                        to: progress_indicator.parent.width
                        duration: 1100
                        loops: Animation.Infinite
                        running: root.loading && root.visible
                        easing.type: Easing.InOutSine
                    }
                }
                Canvas {
                    anchors.fill: parent
                    // Cover the corners outside the rounded track. The outer
                    // rectangle and inner capsule have opposite winding.
                    onPaint: {
                        const ctx = getContext("2d")
                        const radius = height / 2
                        ctx.reset()
                        ctx.fillStyle = Theme.surface
                        ctx.beginPath()
                        ctx.rect(0, 0, width, height)
                        ctx.moveTo(radius, 0)
                        ctx.arc(radius, radius, radius, -Math.PI / 2, Math.PI / 2, true)
                        ctx.lineTo(width - radius, height)
                        ctx.arc(width - radius, radius, radius, Math.PI / 2, -Math.PI / 2, true)
                        ctx.closePath()
                        ctx.fill()
                    }
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Label {
                Layout.fillWidth: true
                text: root.stage_text
                color: Theme.muted
                font.pixelSize: 11
            }
            Label {
                objectName: "model_loading_elapsed"
                text: "已耗时：" + root.elapsed_seconds + " 秒"
                color: Theme.primary
                font.pixelSize: 11
            }
        }
    }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180 }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 180; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 140 }
            NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: 140 }
        }
    }
}
