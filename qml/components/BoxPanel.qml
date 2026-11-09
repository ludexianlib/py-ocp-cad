import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: root
    property var active_model: ({})
    property string editor_model_id: ""
    property bool editor_is_imported: false
    property bool is_ready: false
    signal create_requested(real length, real width, real height)
    padding: 18
    implicitHeight: root.editor_is_imported ? 250 : 300
    Behavior on implicitHeight { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    function dimension_text(value, fallback) {
        if (value === null || value === undefined || !Number.isFinite(Number(value)))
            return String(fallback)
        return String(value)
    }
    function sync_fields() {
        root.editor_is_imported = Boolean(root.active_model.is_imported)
        length_input.value_text = dimension_text(root.active_model.length, 40)
        width_input.value_text = dimension_text(root.active_model.width, 30)
        height_input.value_text = dimension_text(root.active_model.height, 10)
        root.editor_model_id = root.active_model.model_id || ""
    }
    function start_new_model() {
        root.editor_is_imported = false
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
        property bool read_only: false
        property alias value_text: text_field.text
        readonly property bool input_valid: text_field.acceptableInput
        function focus_editor() { text_field.forceActiveFocus(); text_field.selectAll() }
        spacing: 14
        Label { text: dimension_root.label_text; color: Theme.ink; font.pixelSize: 12; Layout.preferredWidth: 36 }
        TextField {
            id: text_field
            objectName: dimension_root.editor_name
            Layout.fillWidth: true
            implicitHeight: 36
            font.pixelSize: 14
            color: Theme.ink
            leftPadding: 14
            rightPadding: 38
            selectByMouse: true
            readOnly: dimension_root.read_only
            inputMethodHints: Qt.ImhFormattedNumbersOnly
            validator: dimension_root.read_only ? null : dimension_validator
            DoubleValidator {
                id: dimension_validator
                bottom: 0.01
                top: 10000
                decimals: 2
                notation: DoubleValidator.StandardNotation
                locale: "C"
            }
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
            Label { text: root.editor_is_imported ? "模型尺寸" : "参数设置"; color: Theme.ink; font.pixelSize: 19; font.weight: Font.DemiBold; Layout.fillWidth: true }
            Rectangle {
                implicitWidth: 40; implicitHeight: 24; radius: 7; color: Theme.primary_soft
                Label { anchors.centerIn: parent; text: root.editor_is_imported ? "STEP" : "BOX"; color: Theme.primary; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1 }
            }
        }
        Label { text: root.editor_is_imported ? "导入模型的包围盒尺寸" : "从简单的几何，开始一次构建"; color: Theme.muted; font.pixelSize: 11; Layout.topMargin: 6 }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.topMargin: 14
            spacing: 8
            DimensionField { id: length_input; label_text: "长度"; editor_name: "length_editor"; read_only: root.editor_is_imported; Layout.fillWidth: true }
            DimensionField { id: width_input; label_text: "宽度"; editor_name: "width_editor"; read_only: root.editor_is_imported; Layout.fillWidth: true }
            DimensionField { id: height_input; label_text: "高度"; editor_name: "height_editor"; read_only: root.editor_is_imported; Layout.fillWidth: true }
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 10 }
        Button {
            id: create_button
            objectName: "create_model_button"
            Layout.fillWidth: true
            implicitHeight: 38
            text: "创建模型  →"
            visible: !root.editor_is_imported
            enabled: !root.editor_is_imported && length_input.input_valid && width_input.input_valid && height_input.input_valid
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
            Layout.topMargin: 10
            text: root.editor_is_imported ? "尺寸单位 mm · 导入模型尺寸仅供查看" : create_button.enabled ? "尺寸单位 mm · 支持 2 位小数" : "请输入 0.01–10000 之间的有效尺寸"
            color: root.editor_is_imported || create_button.enabled ? Theme.muted : Theme.error
            Behavior on color { ColorAnimation { duration: 150 } }
            font.pixelSize: 10
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }
    }
}
