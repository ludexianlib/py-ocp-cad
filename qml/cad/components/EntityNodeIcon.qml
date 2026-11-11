import QtQuick
import "../../components"

Canvas {
    id: root
    property string icon_kind: "entity"
    property color stroke_color: Theme.primary
    implicitWidth: 16
    implicitHeight: 16
    onIcon_kindChanged: requestPaint()
    onStroke_colorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        ctx.clearRect(0, 0, width, height)
        const icon_size = Math.min(width, height)
        ctx.translate((width - icon_size) / 2, (height - icon_size) / 2)
        ctx.scale(icon_size / 16, icon_size / 16)
        ctx.strokeStyle = root.stroke_color
        ctx.fillStyle = root.stroke_color
        ctx.lineWidth = 1.2
        ctx.lineJoin = "round"
        ctx.lineCap = "round"
        ctx.beginPath()
        if (root.icon_kind === "more") {
            for (let index = 0; index < 3; ++index) {
                ctx.moveTo(4.2 + index * 4.5, 8)
                ctx.arc(3 + index * 4.5, 8, 1.2, 0, Math.PI * 2)
            }
            ctx.fill()
        } else if (root.icon_kind === "chevron") {
            ctx.moveTo(5.5, 3.5); ctx.lineTo(10.5, 8); ctx.lineTo(5.5, 12.5)
            ctx.stroke()
        } else if (root.icon_kind === "partial") {
            ctx.arc(8, 8, 4.5, -Math.PI / 2, Math.PI / 2)
            ctx.closePath()
            ctx.fill()
            ctx.beginPath()
            ctx.arc(8, 8, 4.5, 0, Math.PI * 2)
            ctx.stroke()
        } else if (root.icon_kind === "group") {
            ctx.moveTo(2, 4); ctx.lineTo(6, 4); ctx.lineTo(7.5, 5.5)
            ctx.lineTo(14, 5.5); ctx.lineTo(14, 13); ctx.lineTo(2, 13); ctx.closePath()
            ctx.moveTo(2, 7.5); ctx.lineTo(14, 7.5)
            ctx.stroke()
        } else {
            ctx.moveTo(8, 1.8); ctx.lineTo(13.5, 5); ctx.lineTo(13.5, 11)
            ctx.lineTo(8, 14.2); ctx.lineTo(2.5, 11); ctx.lineTo(2.5, 5); ctx.closePath()
            ctx.moveTo(2.5, 5); ctx.lineTo(8, 8.2); ctx.lineTo(13.5, 5)
            ctx.moveTo(8, 8.2); ctx.lineTo(8, 14.2)
            ctx.stroke()
        }
    }
}
