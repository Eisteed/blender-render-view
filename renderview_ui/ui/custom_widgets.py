from PySide6.QtWidgets import QPushButton, QGraphicsLineItem, QGraphicsItem, QGraphicsRectItem, QLabel, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPen, QColor
from PySide6.QtCore import Qt, QSize, QRectF, QEvent, QObject, Signal, QPointF, QObject

class CustomPushButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._normal_icon = None
        self._hover_icon = None

    def setNormalIcon(self, icon):
        self._normal_icon = icon
        self.setIcon(icon)

    def setHoverIcon(self, icon):
        self._hover_icon = icon

    def enterEvent(self, event):
        if self._hover_icon is not None:
            self.setIcon(self._hover_icon)
        self.setCursor(Qt.PointingHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._normal_icon is not None:
            self.setIcon(self._normal_icon)
        self.unsetCursor()
        super().leaveEvent(event)

class CustomLineItem(QGraphicsLineItem):
    def __init__(self, x1, y1, x2, y2, color, width, parent=None):
        super().__init__(x1, y1, x2, y2, parent)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        pen = QPen(color, width)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setAcceptHoverEvents(True)

class CustomRectItem(QGraphicsRectItem):
    def __init__(self, x, y, width, height, color, parent=None):
        super().__init__(x, y, width, height, parent)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.rect_pen = QPen(color)
        self.rect_pen.setWidth(2)
        self.setPen(self.rect_pen)
    def paint(self, painter, option, widget=None):
        pass
    
class SnapshotThumbs(QLabel):
    clicked = Signal(object)

    def __init__(self, fullres, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.snapshot_fullres = fullres
        self.toggled = False
        self.is_set_as_a = False  # Flag to track if set as A
        self.is_set_as_b = False  # Flag to track if set as B
        self.file_path = None  # Path to saved file on disk
        self.setStyleSheet("border: 1px solid transparent;")
        self.label = QLabel(self)
        self.label.setStyleSheet("color: white; background-color: black;")
        self.label.move(5, 5)
        self.label.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)  # Emit self as the argument
        elif event.button() == Qt.RightButton:
            self.showContextMenu(event.position().toPoint())

    def enterEvent(self, event):
        self.setStyleSheet("border: 1px solid grey;")

    def leaveEvent(self, event):
        if not self.toggled:
            self.setStyleSheet("border: 1px solid transparent;")

    def showContextMenu(self, pos):
        context_menu = QMenu(self)
        
        set_a_action = context_menu.addAction("Set as A" if not self.is_set_as_a else "Unset A")
        set_b_action = context_menu.addAction("Set as B" if not self.is_set_as_b else "Unset B")
        delete_action = context_menu.addAction("Delete")

        action = context_menu.exec(self.mapToGlobal(pos))

        if action == set_a_action:
            if self.is_set_as_a:
                # Unset A
                self.unmark()
                self.main_window.unsetOverlayA()
            else:
                # Set as A
                self.main_window.setOverlayA(self.snapshot_fullres, self)  # Set overlay

        elif action == set_b_action:
            if self.is_set_as_b:
                # Unset B
                self.unmark()
                self.main_window.unsetOverlayB()
            else:
                # Set as B
                self.mark_as("B")
                self.main_window.setOverlayB(self.snapshot_fullres, self)  # Set overlay
        
        elif action == delete_action:
            self.unmark()
            # Delete file from disk via main_window
            self.main_window.deleteSnapshotFile(self)
            parent_widget = self.parent()
            if parent_widget is not None:
                parent_widget.layout().removeWidget(self)
                self.deleteLater()  # Properly delete the widget
            # Update panel visibility
            self.main_window.updateSnapshotPanelVisibility()

    def mark_as(self, overlay_letter):
        if overlay_letter == "A":
            self.is_set_as_a = True
            self.is_set_as_b = False
        if overlay_letter == "B":
            self.is_set_as_a = False
            self.is_set_as_b = True

        self.label.setText(overlay_letter)
        self.label.show()

    def unmark(self):
        if self.is_set_as_a: self.is_set_as_a = False;self.main_window.unsetOverlayA()
        if self.is_set_as_b: self.is_set_as_b = False;self.main_window.unsetOverlayB()
        self.label.hide()
        self.label.setText("")

