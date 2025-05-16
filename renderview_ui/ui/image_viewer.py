from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QMenu, QApplication # type: ignore
from PySide6.QtGui import QPainter, QPen, QWheelEvent, QCursor # type: ignore
from PySide6.QtCore import QRectF, Qt, QPointF # type: ignore
from ui.custom_widgets import CustomLineItem, CustomRectItem
from core.socket_client import SocketClient


class ImageViewer(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Basic ui stuff
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._original_drag_mode = self.dragMode()


        self.background_item = QGraphicsRectItem(-64000, -64000, 128000, 128000)
        self.background_item.setBrush(Qt.transparent)
        #self.scene.addItem(self.background_item)
        
        self.image_item = QGraphicsPixmapItem()
        self.scene.addItem(self.image_item)
        self.setSceneRect(self.scene.itemsBoundingRect())

        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.zoom_factor = 1.25
        self.linewidth = 1
        self.rect_item = CustomRectItem(-20, -32000, 40, 64000, Qt.transparent)
        self.scene.addItem(self.rect_item)

        # A/B Line
        self.line_item = CustomLineItem(0, -32000, 0, 32000, Qt.blue, self.linewidth, self.rect_item)
        self.line_item.setFlag(QGraphicsRectItem.ItemIsSelectable, False)
        self.line_item.setFlag(QGraphicsRectItem.ItemIsFocusable, False)
        self.line_item.setAcceptedMouseButtons(Qt.NoButton)  # This makes it non-interactive
        self.scene.addItem(self.line_item)

        self.setMouseTracking(True)
        self.middle_button_pressed = False
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)

        # Render region
        self._drawing_rect = False
        self._start_point = QPointF(50, 50)
        self._end_point =  QPointF(250, 250)
        self._rect_item = None
        self._debug_rect_item = None
        self._waiting_for_release = True
        self.setDragMode(QGraphicsView.NoDrag)

        self.region_rect = None
        self.renderRegionEnabled = False

        self.xmin_percent = 0
        self.xmax_percent = 0
        self.ymin_percent = 0
        self.ymax_percent = 0

        # Horizontal / Vertical Flip
        self.hFlip = False
        self.vFlip = False

    def centerOnImage(self):
        if self.image_item is not None and self.image_item.pixmap() is not None:
            image_rect = self.image_item.boundingRect()
            image_center = QPointF(image_rect.center())
            view_center = self.mapFromScene(image_center)
            self.centerOn(view_center)

    def getCurrentScale(self):
        matrix = self.transform()
        scale_x = matrix.m11()
        scale_y = matrix.m22()
        return (scale_x + scale_y) / 2

    def wheelEvent(self, event: QWheelEvent):
        zoom_in_factor = self.zoom_factor
        zoom_out_factor = 1 / self.zoom_factor

        old_pos = self.mapToScene(event.position().toPoint())

        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        self.scale(zoom_factor, zoom_factor)

        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

        rectZoom = 1/self.getCurrentScale()
        # Keep the rectangle's width constant
        self.rect_item.setRect(-20*rectZoom, -128000, 40*rectZoom, 256000)

    def getImage(self):
        return self.image_item

    def setImage(self, pixmap):        
        self.image_item.setPixmap(pixmap)
        self.image_item.setTransformationMode(Qt.SmoothTransformation)
        #self.setSceneRect(QRectF(pixmap.rect()))

    def mousePressEvent(self, event):
        #if event.button() == Qt.LeftButton:
        
            #if self._debug_rect_item and self._debug_rect_item.scene() == self.scene: self.scene.removeItem(self._debug_rect_item) 
            #if self._waiting_for_release and self._drawing_rect:

        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.middle_button_pressed = True
            self.setCursor(Qt.ClosedHandCursor)
            self.last_mouse_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing_rect and self._start_point is not None:
            self._end_point = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._start_point, self._end_point)
            self._rect_item.setRect(rect)
        elif self.middle_button_pressed:
            delta = event.position().toPoint() - self.last_mouse_pos
            self.last_mouse_pos = event.position().toPoint()
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drawing_rect = False
        self._waiting_for_release = True
        
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.NoDrag)
            self.middle_button_pressed = False
            self.setCursor(Qt.ArrowCursor)
        if event.button() == Qt.LeftButton and self._rect_item is not None:
            if self._rect_item: self.scene.removeItem(self._rect_item)
            self.scene.removeItem(self._debug_rect_item) 
            # Get the drawn rectangle in scene coordinates
            rect = self._rect_item.rect()
            top_left = rect.topLeft()
            bottom_right = rect.bottomRight()
            
            # Normalize the coordinates if drawn from right to left or bottom to top
            if top_left.x() > bottom_right.x():
                top_left.setX(rect.bottomRight().x())
                bottom_right.setX(rect.topLeft().x())
            if top_left.y() > bottom_right.y():
                top_left.setY(rect.bottomRight().y())
                bottom_right.setY(rect.topLeft().y())

            # Get the image bounding rectangle in scene coordinates
            image_rect = self.image_item.mapRectToScene(self.image_item.boundingRect())

            # Calculate intersection rectangle within image bounds
            intersected_left = max(image_rect.left(), top_left.x())
            intersected_top = max(image_rect.top(), top_left.y())
            intersected_right = min(image_rect.right(), bottom_right.x())
            intersected_bottom = min(image_rect.bottom(), bottom_right.y())

            if intersected_left < intersected_right and intersected_top < intersected_bottom:
                # Draw the intersection rectangle for debugging
                intersection_rect = QRectF(intersected_left, intersected_top, 
                                        intersected_right - intersected_left, 
                                        intersected_bottom - intersected_top)
                self._debug_rect_item = QGraphicsRectItem(intersection_rect)

                # Save render region pixels
                image_x = intersected_left  - image_rect.left()
                image_y = intersected_top   - image_rect.top()
                region_w = intersected_right  - intersected_left
                region_h = intersected_bottom - intersected_top
                self.region_rect = QRectF(int(image_x), int(image_y),
                                        int(region_w), int(region_h))
                pen = QPen()
                pen.setStyle(Qt.DashDotLine)
                pen.setCosmetic(True)
                pen.setColor(Qt.white)
                pen.setWidth(1)
                pen.setDashPattern
                self._debug_rect_item.setPen(pen)
                self.scene.addItem(self._debug_rect_item)

                # Calculate percentage coordinates relative to image size
                image_width = image_rect.width()
                image_height = image_rect.height()

                self.xmin_percent = (intersected_left - image_rect.left()) / image_width
                self.xmax_percent = (intersected_right - image_rect.left()) / image_width
                self.ymin_percent = (image_rect.bottom() - intersected_bottom) / image_height
                self.ymax_percent = (image_rect.bottom() - intersected_top) / image_height

                SocketClient.send_message({
                    "render_region": "true",
                    "xmin": f"{self.xmin_percent:.6f}",
                    "ymin": f"{self.ymin_percent:.6f}",
                    "xmax": f"{self.xmax_percent:.6f}",
                    "ymax": f"{self.ymax_percent:.6f}"
                })

        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        copy_action = menu.addAction("Copy to Clipboard")
        vflip_action = menu.addAction("Flip vertically")
        hflip_action = menu.addAction("Flip horizontally")
        selected_action = menu.exec_(event.globalPos())
        
        if selected_action == copy_action:
            self.copyToClipboard()
        if selected_action == vflip_action:
            self.hFlip = not self.hFlip
        if selected_action == hflip_action:
            self.vFlip = not self.vFlip
    def copyToClipboard(self):
        app = QApplication.instance()
        pixmap = self.image_item.pixmap()
        if pixmap:
            app.clipboard().setPixmap(pixmap)

    def startRenderRegionDrawing(self):
        self.region_rect = None
        self._drawing_rect = True
        cursor_pos = QCursor.pos()  # global cursor position
        local_pos = self.mapFromGlobal(cursor_pos)  # map to widget coords
        self._start_point = self.mapToScene(local_pos)  # map to scene coords
        self._rect_item = QGraphicsRectItem()
        pen = QPen()
        pen.setStyle(Qt.DashDotLine)
        pen.setCosmetic(True)
        pen.setColor(Qt.red)
        pen.setWidth(1)
        pen.setDashPattern
        self._rect_item.setPen(pen)
        self._rect_item.setRect(QRectF(self._start_point, self._start_point))
        self.scene.addItem(self._rect_item)