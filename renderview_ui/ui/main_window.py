import os
import uuid
import threading
from PySide6.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QMainWindow, QScrollArea, QComboBox, QLineEdit, QLabel, QPushButton, QFrame, QCheckBox # type: ignore
from PySide6.QtGui import QAction, QPainter, QPainterPath, QPixmap, QImage, QIcon, QPolygonF, QMouseEvent, QTransform # type: ignore
from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QRectF, QSize, Slot  # type: ignore
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
        self.cached_pixmap = None
        self.tempOverlay = None
        self.overlay_A = None
        self.overlay_B = None
        self.alpha_A = 0.0
        self.alpha_B = 0.0
        self.current_a_thumb = None  # Store the current "A" thumbnail
        self.current_b_thumb = None  # Store the current "B" thumbnail
        self.current_selected_index = -1  # Store the current selected thumbnail index
        self.snapshots = []
        self.snapshot_save_path = ""  # Will be set from Blender file path
        self.snapshot_panel_visible = False  # Track if user manually toggled panel
        self.snapshot_panel_auto_hidden = True  # Auto-hide when no snapshots
        self.save_snapshots_enabled = True  # Whether to save snapshots to disk

        # Initialize UI after attributes are set
        self.initUI()

        self.setFocusPolicy(Qt.StrongFocus)  # Ensure the main window can receive key events
        self.screenshot_thread = ScreenshotThread(data.Blender.windowHandle)
        self.screenshot_thread.imageCaptured.connect(self.updateImage)
        self.screenshot_thread.start()

        self.lastHeight = 0
        self.lastWidth = 0

        self.clayOverrideEnabled = False
        self.wireframeOverrideEnabled = False

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

        # Create the snapshot bottom panel (settings + thumbnails + toggle)
        self.createSnapshotPanel()

        # Create the horizontal menu with buttons
        self.createButtonMenu()
        
        # Create the main layout and add the viewer and button menu
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.button_menu)
        main_layout.addWidget(self.viewer)
        main_layout.addWidget(self.snapshot_panel)

        # Set the central widget with the main layout
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.createMenus()
        self.setWindowTitle('Blender Render View (IPR)')
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

    def createSnapshotPanel(self):
        """Create the bottom panel with settings, thumbnails, and toggle button."""
        # Main container for the entire bottom panel
        self.snapshot_panel = QWidget()
        panel_layout = QVBoxLayout(self.snapshot_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Top bar with just the toggle buttons (always visible)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(2)

        # Toggle button (arrow to show/hide panel)
        self.panel_toggle_btn = CustomPushButton()
        self.panel_toggle_btn.setFixedSize(20, 20)
        self.panel_toggle_btn.setText("\u25BC")  # Down arrow (panel visible)
        self.panel_toggle_btn.setToolTip("Toggle snapshot panel")
        self.panel_toggle_btn.clicked.connect(self.toggleSnapshotPanel)
        self.panel_toggle_btn.setStyleSheet("font-size: 10px;")

        # Settings toggle button (gear icon)
        self.settings_toggle_btn = CustomPushButton()
        self.settings_toggle_btn.setFixedSize(20, 20)
        self.settings_toggle_btn.setText("\u2699")  # Gear unicode
        self.settings_toggle_btn.setToolTip("Toggle snapshot settings")
        self.settings_toggle_btn.clicked.connect(self.toggleSettingsPanel)
        self.settings_toggle_btn.setStyleSheet("font-size: 12px;")

        top_bar.addWidget(self.panel_toggle_btn)
        top_bar.addWidget(self.settings_toggle_btn)
        top_bar.addStretch()
        panel_layout.addLayout(top_bar)

        # Content area (collapsible) - contains settings and thumbnails
        self.snapshot_content = QWidget()
        content_layout = QHBoxLayout(self.snapshot_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Settings panel (gear icon opens this)
        self.settings_panel = QFrame()
        self.settings_panel.setFrameStyle(QFrame.StyledPanel)
        self.settings_panel.setFixedWidth(250)
        settings_layout = QVBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(5, 5, 5, 5)
        settings_layout.setSpacing(5)

        # Save path label and input
        path_label = QLabel("Snapshot Save Path:")
        path_label.setStyleSheet("color: white; font-size: 10px;")
        settings_layout.addWidget(path_label)

        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("./brv-snapshots")
        # Save path when user finishes editing (Enter or loses focus), not on every keystroke
        self.path_input.editingFinished.connect(self.onSnapshotPathChanged)
        path_row.addWidget(self.path_input)

        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(30)
        browse_btn.clicked.connect(self.browseSnapshotPath)
        path_row.addWidget(browse_btn)
        settings_layout.addLayout(path_row)

        # Save to disk checkbox
        self.save_checkbox = QCheckBox("Save snapshots to disk")
        self.save_checkbox.setChecked(self.save_snapshots_enabled)
        self.save_checkbox.setStyleSheet("color: white; font-size: 10px;")
        self.save_checkbox.stateChanged.connect(self.onSaveCheckboxChanged)
        settings_layout.addWidget(self.save_checkbox)

        settings_layout.addStretch()
        self.settings_panel.hide()  # Hidden by default
        content_layout.addWidget(self.settings_panel)

        # Scrollable thumbnail area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QHBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(0)
        self.scroll_widget.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setFixedHeight(100 * self.devicePixelRatio())
        self.scroll_layout.setAlignment(Qt.AlignLeft)
        content_layout.addWidget(self.scroll_area)

        # Add content area to panel
        panel_layout.addWidget(self.snapshot_content)

        # Initially hide the panel (auto-hide when no snapshots)
        self.updateSnapshotPanelVisibility()

    def toggleSettingsPanel(self):
        """Toggle the settings panel visibility."""
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
        else:
            self.settings_panel.show()

    def toggleSnapshotPanel(self):
        """Toggle the snapshot panel visibility manually."""
        if self.snapshot_content.isVisible():
            self.snapshot_content.hide()
            self.settings_toggle_btn.hide()
            self.panel_toggle_btn.setText("\u25B2")  # Up arrow (panel hidden)
            self.snapshot_panel_visible = False
        else:
            self.snapshot_content.show()
            self.settings_toggle_btn.show()
            self.panel_toggle_btn.setText("\u25BC")  # Down arrow (panel visible)
            self.snapshot_panel_visible = True

    def updateSnapshotPanelVisibility(self):
        """Auto-show/hide panel based on snapshot count, unless manually toggled."""
        has_snapshots = self.scroll_layout.count() > 0

        if has_snapshots:
            # Always show when there are snapshots
            self.snapshot_panel.show()
            if not self.snapshot_panel_visible:
                self.snapshot_content.show()
                self.settings_toggle_btn.show()
                self.panel_toggle_btn.setText("\u25BC")
                self.snapshot_panel_visible = True
        else:
            # Hide when no snapshots (unless user manually showed it)
            if self.snapshot_panel_auto_hidden:
                self.snapshot_panel.hide()

    def onSnapshotPathChanged(self):
        """Handle snapshot path change (when user finishes editing)."""
        self.snapshot_save_path = self.path_input.text()
        # Save to Blender project
        SocketClient.send_message({"snapshot_path": self.snapshot_save_path})
        print(f"[BRV-UI] Snapshot path saved: {self.snapshot_save_path}")

    def onSaveCheckboxChanged(self, state):
        """Handle save checkbox change."""
        # In PySide6, state is Qt.CheckState enum, use .value or compare with int 2
        self.save_snapshots_enabled = (state == 2)  # Qt.CheckState.Checked == 2
        # Save to Blender project
        SocketClient.send_message({"save_snapshots_enabled": self.save_snapshots_enabled})
        print(f"[BRV-UI] Save checkbox changed: {self.save_snapshots_enabled}")

        # If enabled, save any existing unsaved snapshots
        if self.save_snapshots_enabled:
            self.saveExistingUnsavedSnapshots()

    @Slot()
    def updateSaveCheckbox(self):
        """Update checkbox state from settings."""
        self.save_checkbox.blockSignals(True)
        self.save_checkbox.setChecked(self.save_snapshots_enabled)
        self.save_checkbox.blockSignals(False)

    @Slot()
    def updateSnapshotPathInput(self):
        """Update path input from settings."""
        self.path_input.blockSignals(True)
        self.path_input.setText(self.snapshot_save_path)
        self.path_input.blockSignals(False)

    @Slot()
    def updateRenderPassDropdown(self):
        """Update render pass dropdown with passes received from Blender."""
        self.render_pass_dropdown.blockSignals(True)
        self.render_pass_dropdown.clear()
        self.render_pass_dropdown.addItems(data.Blender.renderPass)
        self.render_pass_dropdown.blockSignals(False)

    def browseSnapshotPath(self):
        """Open folder browser for snapshot save path."""
        folder = QFileDialog.getExistingDirectory(self, "Select Snapshot Folder")
        if folder:
            self.path_input.setText(folder)

    def setSnapshotSavePath(self, path):
        """Set the snapshot save path (called from Blender)."""
        self.snapshot_save_path = path
        self.path_input.setText(path)

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
            (os.path.join(script_dir, 'ui/icons/clay.png'), self.clayOverride, "Clay"),
            (os.path.join(script_dir, 'ui/icons/wireframe.png'), self.wireframeOverride, "Wireframe"),
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
                button.setProperty("normal_icon", QIcon(normal_pixmap))
                button.setProperty("hover_icon", QIcon(hover_pixmap))  
                button.clicked.connect(function) 
                button.setToolTip(tooltip)
                h_layout.addWidget(button)
                self.buttons[function.__name__] = button

        # Add render pass Dropdown Menu
        self.render_pass_dropdown = QComboBox()
        self.render_pass_dropdown.setObjectName("RenderPassDropdown")
        self.render_pass_dropdown.addItems(data.Blender.renderPass)

        # Connect dropdown selection to a function
        def on_dropdown_selected(index):
            data.Blender.renderPassActive = self.render_pass_dropdown.currentText()

        self.render_pass_dropdown.currentIndexChanged.connect(on_dropdown_selected)

        h_layout.addWidget(self.render_pass_dropdown)

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

    def add_image(self, pixmap, file_path=None):
        if pixmap.isNull():
            print(f"[BRV-UI] No image to add")
            return

        scaled_pixmap = pixmap.scaled(QSize(130, 130), Qt.KeepAspectRatio, Qt.SmoothTransformation)

        image_label = SnapshotThumbs(pixmap, self)
        image_label.setPixmap(scaled_pixmap)
        image_label.setScaledContents(False)  # Ensure pixmap scales with label size
        image_label.clicked.connect(self.image_clicked)  # Connect directly to image_clicked

        # Store file path if provided, or save new snapshot to disk in background
        if file_path:
            image_label.file_path = file_path
        elif self.save_snapshots_enabled:
            # Save snapshot to disk in background thread
            image_label.file_path = None  # Will be set when save completes
            self.saveSnapshotInBackground(pixmap, image_label)
        else:
            image_label.file_path = None  # Not saving to disk

        self.scroll_layout.insertWidget(0, image_label)
        self.updateSnapshotPanelVisibility()

    def saveSnapshotInBackground(self, pixmap, image_label):
        """Save snapshot to disk in a background thread."""
        # Convert pixmap to QImage for thread-safe saving
        image = pixmap.toImage()

        def _save():
            if not self.snapshot_save_path:
                save_dir = os.path.join(os.getcwd(), "brv-snapshots")
            else:
                save_dir = self.snapshot_save_path

            # Create directory if it doesn't exist
            try:
                os.makedirs(save_dir, exist_ok=True)
            except Exception as e:
                print(f"[BRV-UI] Error creating snapshot directory: {e}")
                return

            # Generate unique filename
            filename = f"snapshot_{uuid.uuid4().hex[:8]}.png"
            file_path = os.path.join(save_dir, filename)

            # Save the image
            try:
                image.save(file_path, "PNG")
                image_label.file_path = file_path
                print(f"[BRV-UI] Snapshot saved: {file_path}")
            except Exception as e:
                print(f"[BRV-UI] Error saving snapshot: {e}")

        save_thread = threading.Thread(target=_save)
        save_thread.daemon = True
        save_thread.start()

    def saveExistingUnsavedSnapshots(self):
        """Save all existing snapshots that don't have a file_path to disk."""
        # Iterate through all snapshot widgets in scroll_layout
        for i in range(self.scroll_layout.count()):
            widget = self.scroll_layout.itemAt(i).widget()
            if isinstance(widget, SnapshotThumbs):
                # Check if this snapshot doesn't have a file path yet
                if not widget.file_path:
                    # Save it in background
                    self.saveSnapshotInBackground(widget.snapshot_fullres, widget)
                    print(f"[BRV-UI] Saving existing unsaved snapshot to disk")

    @Slot(str)
    def loadSnapshot(self, file_path):
        """Load a snapshot from disk. Can be called from any thread via Qt signal."""
        if not os.path.exists(file_path):
            print(f"[BRV-UI] Snapshot file not found: {file_path}")
            return

        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            print(f"[BRV-UI] Failed to load snapshot: {file_path}")
            return

        self.add_image(pixmap, file_path)
    
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
                # Delete file from disk
                self.deleteSnapshotFile(widget)
            widget.deleteLater()

        # Update panel visibility
        self.updateSnapshotPanelVisibility()

    def deleteSnapshotFile(self, snapshot_widget):
        """Delete snapshot file from disk."""
        if hasattr(snapshot_widget, 'file_path') and snapshot_widget.file_path:
            file_path = snapshot_widget.file_path
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"[BRV-UI] Snapshot file deleted: {file_path}")
            except Exception as e:
                print(f"[BRV-UI] Error deleting snapshot file: {e}")

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


    def clayOverride(self):
        if hasattr(self, 'clayOverrideEnabled') and self.clayOverrideEnabled:
            # Disable clay override
            SocketClient.send_message({"mat_override": "false"})
            self.clayOverrideEnabled = False
            # Reset button to normal state
            self.buttons["clayOverride"].setStyleSheet("background-color: rgb(53, 53, 53);")
            # Restore normal icon
            button = self.buttons["clayOverride"]
            normal_icon = button.property("normal_icon")
            if normal_icon:
                button.setIcon(normal_icon)
        else:
            # Enable clay override
            SocketClient.send_message({"mat_override": "clay"})  # Changed to clay_override
            self.clayOverrideEnabled = True
            
            # Disable wireframe if it was enabled
            if hasattr(self, 'wireframeOverrideEnabled') and self.wireframeOverrideEnabled:
                self.wireframeOverrideEnabled = False
                wireframe_button = self.buttons["wireframeOverride"]
                wireframe_button.setStyleSheet("background-color: rgb(53, 53, 53);")
                # Restore wireframe button normal icon
                wireframe_normal_icon = wireframe_button.property("normal_icon")
                if wireframe_normal_icon:
                    wireframe_button.setIcon(wireframe_normal_icon)
            
            # Set button to active state
            self.buttons["clayOverride"].setStyleSheet("background-color: rgb(6, 84, 101);")
            # Set inverted icon
            button = self.buttons["clayOverride"]
            hover_icon = button.property("hover_icon")
            if hover_icon:
                button.setIcon(hover_icon)

    def wireframeOverride(self):
        if hasattr(self, 'wireframeOverrideEnabled') and self.wireframeOverrideEnabled:
            # Disable wireframe override
            SocketClient.send_message({"mat_override": "false"})
            self.wireframeOverrideEnabled = False
            # Reset button to normal state
            self.buttons["wireframeOverride"].setStyleSheet("background-color: rgb(53, 53, 53);")
            # Restore normal icon
            button = self.buttons["wireframeOverride"]
            normal_icon = button.property("normal_icon")
            if normal_icon:
                button.setIcon(normal_icon)
        else:
            # Enable wireframe override
            SocketClient.send_message({"mat_override": "wireframe"})  # Changed to wireframe_override
            self.wireframeOverrideEnabled = True
            
            # Disable clay if it was enabled
            if hasattr(self, 'clayOverrideEnabled') and self.clayOverrideEnabled:
                self.clayOverrideEnabled = False
                clay_button = self.buttons["clayOverride"]
                clay_button.setStyleSheet("background-color: rgb(53, 53, 53);")
                # Restore clay button normal icon
                clay_normal_icon = clay_button.property("normal_icon")
                if clay_normal_icon:
                    clay_button.setIcon(clay_normal_icon)
            
            # Set button to active state
            self.buttons["wireframeOverride"].setStyleSheet("background-color: rgb(6, 84, 101);")
            # Set inverted icon
            button = self.buttons["wireframeOverride"]
            hover_icon = button.property("hover_icon")
            if hover_icon:
                button.setIcon(hover_icon)
                
    def closeEvent(self, event):
        self.screenshot_thread.stop()
        event.accept()