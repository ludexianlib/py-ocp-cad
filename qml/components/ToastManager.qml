pragma ComponentBehavior: Bound
import QtQuick

Item {
    id: root
    readonly property int maximum_count: 3
    readonly property int display_duration: 3000
    readonly property int count: toast_items.length
    property var toast_items: []
    property var pending_toasts: []
    property int next_toast_id: 0
    property int spacing: 10

    implicitHeight: {
        let total_height = 0
        for (let index = 0; index < root.toast_items.length; ++index)
            total_height += root.toast_items[index].height
        return total_height + Math.max(0, root.count - 1) * root.spacing
    }
    height: implicitHeight

    function show_toast(message, is_error) {
        const message_text = String(message || "").trim()
        if (!message_text.length)
            return
        root.next_toast_id += 1
        const notice = {
            message_text: message_text,
            is_error: !!is_error,
            expires_at: Date.now() + root.display_duration,
            toast_id: root.next_toast_id
        }
        root.pending_toasts = root.pending_toasts.concat([notice]).slice(-root.maximum_count)
        root.flush_pending()
    }

    function relayout() {
        let target_y = 0
        for (let index = 0; index < root.toast_items.length; ++index) {
            const toast = root.toast_items[index]
            toast.y = target_y
            target_y += toast.height + root.spacing
        }
    }

    function remove_toast(toast) {
        root.toast_items = root.toast_items.filter(item => item !== toast)
        toast.destroy()
        root.relayout()
        root.flush_pending()
    }

    function flush_pending() {
        // Expiry starts at the notification event, including time waiting for a slot.
        root.pending_toasts = root.pending_toasts.filter(notice => notice.expires_at > Date.now())
        while (root.pending_toasts.length && root.count < root.maximum_count) {
            const pending = root.pending_toasts.slice()
            const notice = pending.shift()
            root.pending_toasts = pending
            const toast = toast_component.createObject(root, notice)
            if (toast)
                root.toast_items = [toast].concat(root.toast_items)
        }

        // Outgoing cards occupy their slots until fully faded, so even rapid bursts
        // never display a fourth card alongside the three existing cards.
        let excess = root.count + root.pending_toasts.length - root.maximum_count
        for (let index = root.count - 1; index >= 0 && excess > 0; --index) {
            root.toast_items[index].dismiss()
            excess -= 1
        }
        root.relayout()
    }

    Component {
        id: toast_component
        ToastCard {
            width: root.width
            onHeightChanged: root.relayout()
            onDismissed: toast => root.remove_toast(toast)
        }
    }
}
