pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "cad"
import "point_cloud"

ApplicationWindow {
    id: root
    objectName: "workbench_window"
    required property var cad_controller
    required property var cloud_controller
    required property url documents_folder
    property var startup_controller: null
    property string active_page: "cad"
    width: 1360
    height: 900
    minimumWidth: 1080
    minimumHeight: 760
    visible: !root.startup_controller
    opacity: root.startup_controller ? 0 : 1
    title: "CAD Studio · 几何工作空间"
    color: Theme.background
    font.family: Theme.font_family

    NumberAnimation {
        id: reveal_animation
        target: root
        property: "opacity"
        from: 0
        to: 1
        duration: 180
        easing.type: Easing.OutCubic
    }
    Connections {
        target: root.startup_controller
        function onSplash_dismissed() { reveal_animation.start() }
    }

    RowLayout {
        objectName: "workspace_content"
        enabled: (!root.startup_controller || root.startup_controller.workspace_visible) && !reveal_animation.running
        anchors.fill: parent
        spacing: 0
        Sidebar {
            Layout.preferredWidth: 190
            Layout.minimumWidth: 190
            Layout.maximumWidth: 190
            Layout.fillHeight: true
            active_page: root.active_page
            onPage_requested: (page_name) => root.active_page = page_name
            onHelp_requested: {
                if (root.active_page === "cad") cad_page.open_help()
                else toast_manager.show_toast("导入 PLY、PCD、XYZ；左键旋转，右键平移，滚轮缩放，双击适配。", false)
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.surface
            CadPage {
                id: cad_page
                objectName: "cad_page"
                anchors.fill: parent
                cad_controller: root.cad_controller
                documents_folder: root.documents_folder
                active: root.active_page === "cad"
                onNotice_requested: (message, is_error) => toast_manager.show_toast(message, is_error)
            }
            PointCloudPage {
                anchors.fill: parent
                cloud_controller: root.cloud_controller
                documents_folder: root.documents_folder
                active: root.active_page === "point_cloud"
                onNotice_requested: (message, is_error) => toast_manager.show_toast(message, is_error)
            }
        }
    }
    ToastManager {
        id: toast_manager
        objectName: "toast_manager"
        parent: Overlay.overlay
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.topMargin: 20
        width: Math.max(0, Math.min(480, parent.width - 48))
        z: 1000
    }
}
