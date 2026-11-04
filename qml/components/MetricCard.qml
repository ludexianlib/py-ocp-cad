import QtQuick
import QtQuick.Layouts

Card {
    id: root
    property string label_text: ""
    property string value_text: "0"
    property string unit_text: ""
    property color accent_color: Theme.primary
    property int icon_kind: 0

    padding: 20
    color: Theme.surface_muted
    border.width: 0

    RowLayout {
        anchors.fill: parent
        spacing: 16
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 5
            Text { text: root.label_text; font.family: Theme.font_family; font.pixelSize: 12; color: Theme.muted }
            Item {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                implicitHeight: 44
                Text {
                    id: value_label
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    width: Math.max(0, Math.min(implicitWidth, parent.width - unit_label.implicitWidth - 8))
                    height: parent.height
                    text: root.value_text
                    font.family: Theme.font_family
                    font.pixelSize: 34
                    font.weight: Font.Bold
                    fontSizeMode: Text.HorizontalFit
                    minimumPixelSize: 18
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignBottom
                    color: root.accent_color
                }
                Text {
                    id: unit_label
                    anchors.left: value_label.right
                    anchors.leftMargin: 8
                    anchors.bottom: value_label.bottom
                    anchors.bottomMargin: 5
                    text: root.unit_text
                    font.family: Theme.font_family
                    font.pixelSize: 12
                    color: Theme.muted
                }
            }
        }
        Rectangle {
            Layout.preferredWidth: 42
            Layout.preferredHeight: 42
            radius: 13
            color: Qt.rgba(root.accent_color.r, root.accent_color.g, root.accent_color.b, 0.09)
            Canvas {
                anchors.centerIn: parent
                width: 24
                height: 24
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.reset()
                    ctx.strokeStyle = root.accent_color
                    ctx.lineWidth = 1.5
                    ctx.lineJoin = "round"
                    ctx.beginPath()
                    if (root.icon_kind === 0) {
                        ctx.moveTo(12, 2); ctx.lineTo(21, 7); ctx.lineTo(21, 17)
                        ctx.lineTo(12, 22); ctx.lineTo(3, 17); ctx.lineTo(3, 7); ctx.closePath()
                        ctx.moveTo(3, 7); ctx.lineTo(12, 12); ctx.lineTo(21, 7)
                        ctx.moveTo(12, 12); ctx.lineTo(12, 22)
                    } else if (root.icon_kind === 1) {
                        ctx.rect(4, 4, 16, 16)
                        ctx.moveTo(4, 10); ctx.lineTo(20, 10)
                        ctx.moveTo(10, 4); ctx.lineTo(10, 20)
                    } else {
                        ctx.moveTo(3, 16); ctx.lineTo(10, 5); ctx.lineTo(22, 9)
                        ctx.lineTo(15, 20); ctx.closePath()
                        ctx.moveTo(8, 14); ctx.lineTo(11, 9); ctx.lineTo(17, 11)
                    }
                    ctx.stroke()
                }
            }
        }
    }
}
