import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: root
    property var active_model: ({})
    property string editor_model_id: ""
    property bool is_ready: false
    signal create_requested(real length, real width, real height)
    padding: 22

    function sync_fields() {
        length_input.value_text = String(root.active_model.length || 40)
        width_input.value_text = String(root.active_model.width || 30)
        height_input.value_text = String(root.active_model.height || 10)
        root.editor_model_id = root.active_model.model_id || ""
    }
    function start_new_model() {
        length_input.value_text = "40"
        width_input.value_text = "30"
        height_input.value_text = "10"
        length_input.focus_editor()
    }
    Component.onCompleted: {
        root.is_ready = true
        root.sync_fields()
    }
    onActive_modelChanged: {
        if (root.is_ready && (root.active_model.model_id || "") !== root.editor_model_id)
            root.sync_fields()
    }

    component DimensionField: RowLayout {
        id: dimension_root
        required property string label_text
        property string editor_name: ""
        property alias value_text: text_field.text
        readonly property bool input_valid: text_field.acceptableInput
        function focus_editor() { text_field.forceActiveFocus(); text_field.selectAll() }
        spacing: 14
        Label { text: dimension_root.label_text; color: Theme.ink; font.pixelSize: 12; Layout.preferredWidth: 36 }
        TextField {
            id: text_field
            objectName: dimension_root.editor_name
            Layout.fillWidth: true
            implicitHeight: 42
            font.pixelSize: 14
            color: Theme.ink
            leftPadding: 14
            rightPadding: 38
            selectByMouse: true
            inputMethodHints: Qt.ImhFormattedNumbersOnly
            validator: DoubleValidator { bottom: 0.01; top: 10000; decimals: 2; notation: DoubleValidator.StandardNotation; locale: "C" }
            background: Rectangle {
                radius: 10
                color: text_field.activeFocus ? "white" : Theme.surface_muted
                border.color: text_field.activeFocus ? Theme.primary : "#efedf4"
                Behavior on border.color { ColorAnimation { duration: 150 } }
            }
            Label { anchors.right: parent.right; anchors.rightMargin: 13; anchors.verticalCenter: parent.verticalCenter; text: "mm"; color: Theme.muted; font.pixelSize: 11 }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Label { text: "参数设置"; color: Theme.ink; font.pixelSize: 19; font.weight: Font.DemiBold; Layout.fillWidth: true }
            Rectangle {
                implicitWidth: 40; implicitHeight: 24; radius: 7; color: Theme.primary_soft
                Label { anchors.centerIn: parent; text: "BOX"; color: Theme.primary; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1 }
            }
        }
        Label { text: "从简单的几何，开始一次构建"; color: Theme.muted; font.pixelSize: 11; Layout.topMargin: 8 }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.topMargin: 25
            spacing: 12
            DimensionField { id: length_input; label_text: "长度"; editor_name: "length_editor"; Layout.fillWidth: true }
            DimensionField { id: width_input; label_text: "宽度"; editor_name: "width_editor"; Layout.fillWidth: true }
            DimensionField { id: height_input; label_text: "高度"; editor_name: "height_editor"; Layout.fillWidth: true }
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 20 }
        Button {
            id: create_button
            objectName: "create_model_button"
            Layout.fillWidth: true
            implicitHeight: 44
            text: "创建模型  →"
            enabled: length_input.input_valid && width_input.input_valid && height_input.input_valid
            onClicked: root.create_requested(Number(length_input.value_text), Number(width_input.value_text), Number(height_input.value_text))
            background: Rectangle {
                radius: 11
                color: !create_button.enabled ? "#d7d2eb" : create_button.hovered ? Theme.primary_hover : Theme.primary
                Behavior on color { ColorAnimation { duration: 150 } }
            }
            contentItem: Label { text: create_button.text; color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        }
        Label {
            Layout.fillWidth: true
            Layout.topMargin: 14
            text: create_button.enabled ? "尺寸单位 mm · 支持 2 位小数" : "请输入 0.01–10000 之间的有效尺寸"
            color: create_button.enabled ? Theme.muted : Theme.error
            font.pixelSize: 10
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }
    }
}
