pragma Singleton
import QtQuick

QtObject {
    readonly property color background: "#f7f7fa"
    readonly property color surface: "#ffffff"
    readonly property color surface_muted: "#f7f7fa"
    readonly property color ink: "#292943"
    readonly property color muted: "#9292a6"
    readonly property color line: "#ecebf3"
    readonly property color sidebar: "#25253f"
    readonly property color sidebar_hover: "#34344e"
    readonly property color primary: "#5948cc"
    readonly property color primary_hover: "#4938b7"
    readonly property color primary_soft: "#efecfc"
    readonly property color yellow: "#ffcc00"
    readonly property color orange: "#f59300"
    readonly property color green: "#83ae29"
    readonly property color error: "#cd4c63"
    readonly property string font_family: "Microsoft YaHei UI"
    readonly property int card_radius: 22

    function format_number(value, decimals) {
        return Number(value || 0).toLocaleString(Qt.locale("en_US"), "f", decimals || 0)
    }
}
