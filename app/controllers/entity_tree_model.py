"""Qt list adapter for an expandable entity hierarchy; no geometry operations."""

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSlot


class EntityTreeModel(QAbstractListModel):
    role_names = ("node_id", "node_name", "node_kind", "node_depth", "has_children",
                  "is_expanded", "is_selected", "is_partial", "is_visible", "is_partly_visible")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tree = None
        self._rows = []
        self._expanded_ids = set()

    def roleNames(self):
        return {int(Qt.ItemDataRole.UserRole) + index: name.encode() for index, name in enumerate(self.role_names)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        node, depth = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return node["name"]
        role_index = int(role) - int(Qt.ItemDataRole.UserRole)
        if not 0 <= role_index < len(self.role_names):
            return None
        node_id = node["node_id"]
        descendants = self._tree.descendants[node_id]
        selected = descendants & self._tree.selected_ids
        visible = descendants & self._tree.visible_ids
        values = (node_id, node["name"], node["kind"], depth, bool(node["children"]),
                  node_id in self._expanded_ids, descendants <= self._tree.selected_ids,
                  bool(selected) and selected != descendants, bool(visible),
                  bool(visible) and visible != descendants)
        return values[role_index]

    def _flatten(self, node, depth):
        rows = [(node, depth)]
        if node["node_id"] in self._expanded_ids:
            for child in node["children"]:
                rows.extend(self._flatten(child, depth + 1))
        return rows

    def set_tree(self, tree):
        if tree is self._tree:
            return
        self.beginResetModel()
        self._tree = tree
        self._expanded_ids = set()
        if tree is not None:
            root = tree.metadata["root"]
            self._expanded_ids = {root["node_id"]} | {child["node_id"] for child in root["children"]}
            self._rows = self._flatten(root, 0)
        else:
            self._rows = []
        self.endResetModel()

    def refresh_states(self):
        if self._rows:
            self.dataChanged.emit(self.index(0), self.index(len(self._rows) - 1), [])

    @pyqtSlot(str)
    def toggle_expanded(self, node_id):
        for row, (node, depth) in enumerate(self._rows):
            if node["node_id"] != node_id or not node["children"]:
                continue
            if node_id in self._expanded_ids:
                end = row + 1
                while end < len(self._rows) and self._rows[end][1] > depth:
                    end += 1
                self.beginRemoveRows(QModelIndex(), row + 1, end - 1)
                del self._rows[row + 1:end]
                self._expanded_ids.remove(node_id)
                self.endRemoveRows()
            else:
                children = []
                for child in node["children"]:
                    children.extend(self._flatten(child, depth + 1))
                self.beginInsertRows(QModelIndex(), row + 1, row + len(children))
                self._rows[row + 1:row + 1] = children
                self._expanded_ids.add(node_id)
                self.endInsertRows()
            self.dataChanged.emit(self.index(row), self.index(row), [])
            return
