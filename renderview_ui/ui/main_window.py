import os
from PySide6.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QMainWindow, QScrollArea, QComboBox # type: ignore
from PySide6.QtGui import QAction, QPainter, QPainterPath, QPixmap, QImage, QIcon, QPolygonF, QMouseEvent, QTransform # type: ignore
from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QRectF, QSize  # type: ignore
from core.capture import ScreenshotThread
from ui.image_viewer import ImageViewer
from ui.custom_widgets import SnapshotThumbs, CustomPushButton
from core.paths import script_dir
from blender import data
from core.socket_client import SocketClient

######################
### Global Hotkeys ###
######################
class KeyPressFilter(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent

    def eventFilter(self, obj, event):
        # Handle key events
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Left:
                self.main_window.navigate_thumbnails(-1)
                return True
            
            elif event.key() == Qt.Key_Right:
                self.main_window.navigate_thumbnails(1)
                return True
            
            elif event.key() == Qt.Key_Delete:
                self.main_window.deleteCurrent()
                return True

            elif event.key() == Qt.Key_H:
                self.main_window.viewer.hFlip = not self.main_window.viewer.hFlip
                return True
            
            elif event.key() == Qt.Key_V:
                self.main_window.viewer.vFlip = not self.main_window.viewer.vFlip
                return True
        
        # Handle mouse click with modifier
        elif event.type() == QEvent.MouseButtonPress:
            if isinstance(event, QMouseEvent):
                if event.button() == Qt.LeftButton and (event.modifiers() & Qt.ShiftModifier):
                    self.main_window.viewer.startRenderRegionDrawing()
                    self.main_window.enableRenderRegionUI()

        return False
###############
### Main UI ###
###############
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.blender_hwnd = None
        self.buttons = None 
        self.initUI()
        self.cached_pixmap = None
        self.tempOverlay = None
        self.overlay_A = None
        self.overlay_B = None
        self.alpha_A = 0.0
        self.alpha_B = 0.0
        self.current_a_thumb = None  # Store the current "A" thumbnail
        self.current_b_thumb = None  # Store the current "B" thumbnail
        self.current_selected_index = -1  # Store the current selected thumbnail index
        self.setFocusPolicy(Qt.StrongFocus)  # Ensure the main window can receive key events
        self.snapshots = []
        self.screenshot_thread = ScreenshotThread(data.Blender.windowHandle)
        self.screenshot_thread.imageCaptured.connect(self.updateImage)
        self.screenshot_thread.start()

        self.lastHeight = 0
        self.lastWidth = 0
        # Install the event filter on the main window
        self.key_press_filter = KeyPressFilter(self)
        QApplication.instance().installEventFilter(self.key_press_filter)

        self.setWindowFlags(self.windowFlags() | Qt.Window)  # Ensure it's a top-level window

    def initUI(self):
        # Facultative Set the window as top-most
        # self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)  

        # Main ImageViewer
        self.viewer = ImageViewer()
        self.setCentralWidget(self.viewer)

        # Create the scrollable image gallery at the bottom
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QHBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(0)
        self.scroll_widget.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setFixedHeight(100 * self.devicePixelRatio())
        self.scroll_layout.setAlignment(Qt.AlignLeft) 

        # Create the horizontal menu with buttons
        self.createButtonMenu()
        
        # Create the main layout and add the viewer and button menu
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.button_menu)
        main_layout.addWidget(self.viewer)
        main_layout.addWidget(self.scroll_area)

        # Set the central widget with the main layout
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.createMenus()
        self.setWindowTitle('Blender Render View (IPR) v0.3')
        self.showMaximized() 
        self.viewer.centerOn(self.viewer.image_item.boundingRect().center())

    def createMenus(self):
        menubar = self.menuBar()

        # File menu
        fileMenu = menubar.addMenu('&File')

        saveAsAction = QAction('Save As...', self)
        saveAsAction.triggered.connect(self.saveAs)
        fileMenu.addAction(saveAsAction)

        # View menu
        viewMenu = menubar.addMenu('&View')

        fitToWindowAction = QAction('Fit Image to Window', self)
        fitToWindowAction.triggered.connect(self.fitToWindow)
        viewMenu.addAction(fitToWindowAction)

        fitToZoomAction = QAction('Zoom 1:1', self)
        fitToZoomAction.triggered.connect(self.fitToZoom)
        viewMenu.addAction(fitToZoomAction) 

    def createButtonMenu(self):
        self.button_menu = QWidget()
        h_layout = QHBoxLayout()
        h_layout.setSpacing(0)
        h_layout.setContentsMargins(0, 0, 0, 0)

        self.buttons = {}

        button_data = [
            (os.path.join(script_dir, 'ui/icons/save.png'), self.saveAs, "Save the current image"),
            (None, None, "Separator"),
            (os.path.join(script_dir, 'ui/icons/fit.png'), self.fitToWindow, "Fit image to window"),
            (os.path.join(script_dir, 'ui/icons/ratio.png'), self.fitToZoom, "Zoom to original ratio"),
            (None, None, "Separator"),
            (os.path.join(script_dir, 'ui/icons/region.png'), self.renderRegion, "Toggle render region (shift-click & drag to draw render region)"),
            (None, None, "Separator"),
            (os.path.join(script_dir, 'ui/icons/snapshot.png'), self.snapshot, "Take a snapshot"),
            (os.path.join(script_dir, 'ui/icons/copy.png'), self.viewer.copyToClipboard, "Copy to clipboard"),
            (None, None, "Separator"),
        ]

        icon_size_px = QSize(25, 25)

        # Get the device pixel ratio for scaling
        scale_factor = QApplication.primaryScreen().devicePixelRatio()
        scaled_size = icon_size_px * scale_factor

        # Create buttons with custom images and connect to functions
        for image_path, function, tooltip in button_data:
            if function is None:
                # Ajouter un séparateur
                separator = QWidget()
                separator.setFixedHeight(1)  
                separator.setFixedWidth(10)  
                h_layout.addWidget(separator)
            else:
                button = CustomPushButton()
                normal_pixmap = QPixmap(image_path).scaled(scaled_size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                hover_image = QImage(image_path).scaled(scaled_size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                hover_image.invertPixels()  # Invert the hover icon colors
                hover_pixmap = QPixmap.fromImage(hover_image)
                button.setNormalIcon(QIcon(normal_pixmap))
                button.setHoverIcon(QIcon(hover_pixmap))
                button.setIconSize(icon_size_px)  
                button.setFixedSize(scaled_size)  
                button.clicked.connect(function) 
                button.setToolTip(tooltip)
                h_layout.addWidget(button)
                self.buttons[function.__name__] = button

        # Add render pass Dropdown Menu
        dropdown = QComboBox()
        dropdown.setObjectName("RenderPassDropdown")  # Assign a unique name
        dropdown.addItems(data.Blender.renderPass)

        # Connect dropdown selection to a function 
        def on_dropdown_selected(index):
            dropdown_name = dropdown.objectName()
            data.Blender.renderPassActive = dropdown.currentText()
            #print(f"Dropdown '{dropdown_name}' selected: {dropdown.currentText()}")

        dropdown.currentIndexChanged.connect(on_dropdown_selected)

        h_layout.addWidget(dropdown)

        # Align buttons to the left
        h_layout.addStretch()

        self.button_menu.setLayout(h_layout)
    
    def setOverlayA(self, pixmap, thumb):
        if self.current_a_thumb:
            self.current_a_thumb.unmark()
        self.overlay_A = pixmap
        self.current_a_thumb = thumb
        if thumb:
            thumb.mark_as("A")

    def setOverlayB(self, pixmap, thumb):
        if self.current_b_thumb:
            self.current_b_thumb.unmark()
        self.overlay_B = pixmap
        self.current_b_thumb = thumb
        if thumb:
            thumb.mark_as("B")

    def unsetOverlayA(self):
        self.overlay_A = None
        self.current_a_thumb = None
        #print("removed overlay A")

    def unsetOverlayB(self):
        self.overlay_B = None
        self.current_b_thumb = None
        #print("removed overlay B")

    def apply_line_mask(self, base_pixmap, overlay_A, overlay_B, mask_line):
        if base_pixmap is None:
            return None

        result_image = QImage(base_pixmap.size(), QImage.Format_ARGB32)
        result_image.fill(Qt.blue)

        painter = QPainter(result_image)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw base image
        painter.drawPixmap(0, 0, base_pixmap)
        # Calculate the offsets
        offset_x = base_pixmap.width() / 2
        offset_y = base_pixmap.height() / 2
        p1_scene = mask_line.mapToScene(mask_line.line().p1())
        p2_scene = mask_line.mapToScene(mask_line.line().p2())

        # Apply the offset to the line points
        p1_scene.setX(p1_scene.x() + offset_x)
        p1_scene.setY(p1_scene.y() + offset_y)
        p2_scene.setX(p2_scene.x() + offset_x)
        p2_scene.setY(p2_scene.y() + offset_y)

        # Create a polygon for the left side of the line
        polygon = QPolygonF()
        polygon.append(QPointF(0, 0))
        polygon.append(p1_scene)
        polygon.append(p2_scene)
        polygon.append(QPointF(0, base_pixmap.height()))

        # Convert polygon to QPainterPath
        path = QPainterPath()
        path.addPolygon(polygon)

        # Draw overlay A on the left side
        painter.setClipPath(path)
        painter.setOpacity(1)
        painter.drawPixmap(0, 0, overlay_A)
        
        # Draw overlay B on the right side
        full_rect = QPainterPath()
        full_rect.addRect(QRectF(base_pixmap.rect()))
        inverse_path = full_rect.subtracted(path)
        
        painter.setClipPath(inverse_path)
        painter.setOpacity(1)
        painter.drawPixmap(0, 0, overlay_B)

        # Debug: Draw the polygon outline and fill it with a transparent color
        # debug_pen = QPen(Qt.red, 2, Qt.DashLine)
        # debug_brush = QBrush(QColor(255, 0, 0, 50))  # Semi-transparent red
        # painter.setPen(debug_pen)
        # painter.setBrush(debug_brush)
        # painter.drawPolygon(polygon)
        painter.end()
        return QPixmap.fromImage(result_image)
    
    def blend_images(self, base_pixmap, tempOverlay, overlay_A, overlay_B):
        if base_pixmap is None:
            return None

        # Determine the maximum width and height from the provided pixmaps
        max_width = base_pixmap.width()
        max_height = base_pixmap.height()
        for pixmap in [tempOverlay, overlay_A, overlay_B]:
            if pixmap:
                max_width = max(max_width, pixmap.width())
                max_height = max(max_height, pixmap.height())

        # Create a result image with the maximum dimensions
        result_image = QImage(max_width, max_height, QImage.Format_ARGB32)
        result_image.fill(Qt.transparent)

        painter = QPainter(result_image)
        painter.setOpacity(1.0)

        # Define a function to calculate the offset for centering
        def get_centered_offset(pixmap, result_width, result_height):
            x_offset = (result_width - pixmap.width()) // 2
            y_offset = (result_height - pixmap.height()) // 2
            return x_offset, y_offset


        
        if tempOverlay:
            x_offset, y_offset = get_centered_offset(tempOverlay, max_width, max_height)
            painter.drawPixmap(x_offset, y_offset, tempOverlay)
        else:
            x_offset, y_offset = get_centered_offset(base_pixmap, max_width, max_height)
            painter.drawPixmap(x_offset, y_offset, base_pixmap)

        if overlay_A or overlay_B:
            self.viewer.line_item.setVisible(True)
            self.viewer.rect_item.setVisible(True)

            if overlay_A and overlay_B:
                # Compare overlay_A to overlay_B directly (A/B mode)
                masked_pixmap = self.apply_line_mask(overlay_A, overlay_A, overlay_B, self.viewer.line_item)
                x_offset, y_offset = get_centered_offset(masked_pixmap, max_width, max_height)
                painter.drawPixmap(x_offset, y_offset, masked_pixmap)
            elif overlay_A:
                # Compare overlay_A to live view
                masked_pixmap = self.apply_line_mask(base_pixmap, overlay_A, base_pixmap, self.viewer.line_item)
                x_offset, y_offset = get_centered_offset(masked_pixmap, max_width, max_height)
                painter.drawPixmap(x_offset, y_offset, masked_pixmap)
            elif overlay_B:
                # Compare overlay_B to live view
                masked_pixmap = self.apply_line_mask(base_pixmap, base_pixmap, overlay_B, self.viewer.line_item)
                x_offset, y_offset = get_centered_offset(masked_pixmap, max_width, max_height)
                painter.drawPixmap(x_offset, y_offset, masked_pixmap)
                    
        else:
            self.viewer.line_item.setVisible(False)
            self.viewer.rect_item.setVisible(False)
        painter.end()
        return QPixmap.fromImage(result_image)
        
    def updateImage(self, pixmap):
        current_transform = self.viewer.transform()
        region = self.viewer.region_rect
        drawing  = self.viewer._drawing_rect 

        if self.viewer.renderRegionEnabled is False or region is None:
            if not drawing:
                self.cached_pixmap = pixmap     
            liveview = self.cached_pixmap or pixmap
        else:
            region = region.adjusted(0, 1, 0, 0)
            if self.cached_pixmap is None or \
            self.cached_pixmap.size() != pixmap.size():
                self.cached_pixmap = self.viewer.image_item.pixmap().copy()

            composed = QPixmap(self.cached_pixmap)
            with QPainter(composed) as p:
                p.drawPixmap(region, pixmap, region) 
            with QPainter(self.cached_pixmap) as p:  
                p.drawPixmap(region, pixmap, region)
            liveview = composed

        blended_pixmap = self.blend_images(liveview, self.tempOverlay, self.overlay_A, self.overlay_B)
        if blended_pixmap.width() != self.lastWidth or blended_pixmap.height() != self.lastHeight:
            
            # Set the image and apply the new transformation
            self.viewer.setImage(blended_pixmap)
            
            # Adjust the position of the image in the viewer to be centered
            offsetx = (blended_pixmap.width()/2) * -1
            offsety = (blended_pixmap.height()/2) * -1

            self.viewer.image_item.setPos(offsetx, offsety)

            self.lastHeight = blended_pixmap.height()
            self.lastWidth = blended_pixmap.width()


        # H / V Flip
        # Apply flipping based on viewer's hFlip and vFlip
        if self.viewer.hFlip or self.viewer.vFlip:
            transform = QTransform()
            scale_x = -1 if self.viewer.hFlip else 1
            scale_y = -1 if self.viewer.vFlip else 1
            transform.scale(scale_x, scale_y)
            blended_pixmap = blended_pixmap.transformed(transform)

        self.viewer.setImage(blended_pixmap)
        self.viewer.setTransform(current_transform)

    def add_image(self, pixmap):
        if pixmap.isNull():
            print(f"[BRV-UI] No image to add")
            return

        scaled_pixmap = pixmap.scaled(QSize(130, 130), Qt.KeepAspectRatio, Qt.SmoothTransformation)

        image_label = SnapshotThumbs(pixmap, self)
        image_label.setPixmap(scaled_pixmap)
        image_label.setScaledContents(False)  # Ensure pixmap scales with label size
        image_label.clicked.connect(self.image_clicked)  # Connect directly to image_clicked
        self.scroll_layout.insertWidget(0, image_label)
    
    def navigate_thumbnails(self, direction):
        count = self.scroll_layout.count()
        if count == 0:
            return
        
        # Unselect current thumbnail
        if self.current_selected_index >= 0:
            self.scroll_layout.itemAt(self.current_selected_index).widget().setStyleSheet("border: 1px solid transparent;")
        
        # Update the selected index
        self.current_selected_index = (self.current_selected_index + direction) % count
        
        # Select the new thumbnail
        selected_thumb = self.scroll_layout.itemAt(self.current_selected_index).widget()
        selected_thumb.setStyleSheet("border: 1px solid white;")
        
        # Update tempOverlay based on the new selection
        self.tempOverlay = selected_thumb.snapshot_fullres
        self.updateImage(self.viewer.image_item.pixmap())

    def image_clicked(self, label_image):
        if label_image.toggled:
            self.tempOverlay = None
            label_image.toggled = False
            self.current_selected_index = -1  # No thumbnail selected
        else:
            self.tempOverlay = label_image.snapshot_fullres
            for i in range(self.scroll_layout.count()):
                item = self.scroll_layout.itemAt(i).widget()
                item.toggled = False
                item.setStyleSheet("border: 1px solid transparent;")
                if item == label_image:
                    self.current_selected_index = i  # Update the selected index
            label_image.setStyleSheet("border: 1px solid white;")
            label_image.toggled = True
        self.updateImage(self.viewer.image_item.pixmap())
    
    def invertButtonImage(self):
        button = self.sender()
        icon = button.icon()
        pixmap = icon.pixmap(icon.availableSizes()[0])
        image = pixmap.toImage()
        image.invertPixels()
        button.setIcon(QIcon(QPixmap.fromImage(image)))

    def saveAs(self):
        fileName, _ = QFileDialog.getSaveFileName(self, "Save Image", "", "PNG Files (*.png)")
        if fileName:
            pixmap = self.viewer.image_item.pixmap()
            if pixmap:
                pixmap.save(fileName, "PNG")

    def fitToWindow(self):
        # Get the bounding rectangle of just the image item
        image_rect = self.viewer.getImage().boundingRect()

        # Fit the image item's bounding rectangle in the view, keeping aspect ratio
        self.viewer.fitInView(image_rect, Qt.KeepAspectRatio)
        self.viewer.centerOn(0,0)


    def fitToZoom(self):
        # Get the bounding rectangle of just the image item
        image_rect = self.viewer.getImage().boundingRect()
        self.viewer.fitInView(image_rect, Qt.KeepAspectRatio)
        self.viewer.resetTransform()
        screen = self.window().screen()
        device_pixel_ratio = screen.devicePixelRatio()
        scale = 1.0 / device_pixel_ratio
        self.viewer.scale(scale, scale)
        self.viewer.centerOn(0,0)

    def snapshot(self):
        self.add_image(self.viewer.image_item.pixmap())

    def deleteCurrent(self):
        item = self.scroll_layout.itemAt(self.current_selected_index)

        self.current_selected_index = -1
        if item is None:
            return
        
        # Remove the item from the layout
        widget = item.widget()

        self.scroll_layout.removeWidget(widget)
        
        # Optionally, delete the widget
        if widget is not None:
            if isinstance(widget, SnapshotThumbs):

                widget.unmark()
            widget.deleteLater()


    def renderRegion(self):
        if(self.viewer.renderRegionEnabled):
            SocketClient.send_message({
                "render_region": "false",
                "xmin": f"{self.viewer.xmin_percent:.6f}",
                "ymin": f"{self.viewer.ymin_percent:.6f}",
                "xmax": f"{self.viewer.xmax_percent:.6f}",
                "ymax": f"{self.viewer.ymax_percent:.6f}"
            })
            self.disableRenderRegionUI()
        else:
            SocketClient.send_message({
                "render_region": "true",
                "xmin": f"{self.viewer.xmin_percent:.6f}",
                "ymin": f"{self.viewer.ymin_percent:.6f}",
                "xmax": f"{self.viewer.xmax_percent:.6f}",
                "ymax": f"{self.viewer.ymax_percent:.6f}"
            })
            self.enableRenderRegionUI()

    def enableRenderRegionUI(self):
            self.buttons["renderRegion"].setStyleSheet("background-color: rgb(6, 84, 101);")
            self.viewer.renderRegionEnabled = True
            if self.viewer._debug_rect_item: self.viewer._debug_rect_item.setVisible(True)

    def disableRenderRegionUI(self):
            self.buttons["renderRegion"].setStyleSheet("background-color: rgb(53, 53, 53);")
            self.viewer.renderRegionEnabled = False
            if self.viewer._debug_rect_item: self.viewer._debug_rect_item.setVisible(False)
            
    def closeEvent(self, event):
        self.screenshot_thread.stop()
        event.accept()