pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"

Card {
    id: root
    required property var cloud_controller
    readonly property var cloud: cloud_controller.active_cloud
    readonly property bool has_cloud: cloud_controller.has_cloud
    padding: 20
    implicitHeight: content.implicitHeight + padding * 2

    component InfoRow: RowLayout {
        required property string label_text
        required property string value_text
        Layout.fillWidth: true
        spacing: 8
        Label { text: parent.label_text; color: Theme.muted; font.pixelSize: 12 }
        Label { text: parent.value_text; color: Theme.ink; font.pixelSize: 12; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; elide: Text.ElideMiddle }
    }

    ColumnLayout {
        id: content
        anchors.fill: parent
        spacing: 16
        Label { text: "点云信息"; color: Theme.ink; font.pixelSize: 19; font.weight: Font.DemiBold }
        Label { text: root.cloud.name || "等待导入点云"; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideMiddle }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.line }
        InfoRow { label_text: "有效点数"; value_text: root.has_cloud ? Theme.format_number(root.cloud.point_count, 0) : "—" }
        InfoRow { label_text: "移除无效点"; value_text: root.has_cloud ? Theme.format_number(root.cloud.removed_count, 0) : "—" }
        InfoRow { label_text: "原始颜色"; value_text: root.has_cloud ? (root.cloud.has_colors ? "RGB" : "无") : "—" }
        Label { text: "包围盒尺寸"; color: Theme.ink; font.pixelSize: 13; font.weight: Font.DemiBold; Layout.topMargin: 6 }
        Repeater {
            model: ["X", "Y", "Z"]
            delegate: InfoRow {
                required property int index
                required property string modelData
                label_text: modelData
                value_text: root.cloud.dimensions ? Theme.format_number(root.cloud.dimensions[index], 3) : "—"
            }
        }
        Label { text: "尺寸沿用源文件坐标单位"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.line; Layout.topMargin: 6 }
        Label { text: "显示设置"; color: Theme.ink; font.pixelSize: 16; font.weight: Font.DemiBold }
        RowLayout {
            Layout.fillWidth: true
            Label { text: "点大小"; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
            Label { text: root.cloud_controller.point_size.toFixed(1) + " px"; color: Theme.ink; font.pixelSize: 12 }
        }
        Slider {
            objectName: "point_size_slider"
            Layout.fillWidth: true
            from: 1; to: 12; stepSize: 0.5
            value: root.cloud_controller.point_size
            enabled: root.has_cloud
            onMoved: root.cloud_controller.point_size = value
            background: Rectangle { x: parent.leftPadding; y: (parent.height - height) / 2; implicitWidth: 180; width: parent.availableWidth; height: 4; implicitHeight: 4; radius: 2; color: Theme.primary_soft; Rectangle { width: parent.width * parent.parent.visualPosition; height: parent.height; radius: 2; color: Theme.primary } }
            handle: Rectangle { x: parent.leftPadding + parent.visualPosition * (parent.availableWidth - width); y: (parent.height - height) / 2; implicitWidth: 16; implicitHeight: 16; radius: 8; color: Theme.primary; scale: parent.pressed ? 1.12 : 1; Behavior on scale { NumberAnimation { duration: 120 } } }
        }
        CheckBox {
            text: "使用原始 RGB 颜色"
            enabled: root.has_cloud && Boolean(root.cloud.has_colors)
            checked: root.cloud_controller.use_rgb
            onToggled: root.cloud_controller.use_rgb = checked
            indicator: Rectangle { implicitWidth: 18; implicitHeight: 18; radius: 5; x: parent.leftPadding; y: (parent.height - height) / 2; color: parent.checked ? Theme.primary : Theme.surface; border.color: parent.checked ? Theme.primary : Theme.line; Behavior on color { ColorAnimation { duration: 150 } } Label { anchors.centerIn: parent; text: "✓"; color: "white"; visible: parent.parent.checked } }
            contentItem: Label { text: parent.text; leftPadding: parent.indicator.width + parent.spacing; color: parent.enabled ? Theme.ink : Theme.muted; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter }
        }
        Label { text: "左键拖动旋转\n右键拖动平移\n滚轮缩放 · 双击适配"; color: Theme.muted; font.pixelSize: 11; lineHeight: 1.6; Layout.topMargin: 10 }
        Item { Layout.fillHeight: true }
    }
}
