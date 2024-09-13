import atexit
import os
import PySide6
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsLineItem, QGraphicsRectItem, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QFileDialog, QMainWindow, QScrollArea, QLabel, QMenuBar, QMenu
from PySide6.QtGui import QAction, QPainter, QPainterPath, QPen, QPixmap, QImage, QColor, QPalette, QIcon, QPolygonF, QWheelEvent
from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QThread, Signal, QRectF, QSize,  QTimer
import pygetwindow as gw
import threading
import win32con, win32gui, win32ui, win32process
import ctypes
import socket
import time
import json
import sys
import pywintypes

HOST = '127.0.0.1' 
status = {'status': 'initial'}  # Global status variable
status_lock = threading.Lock()  # Lock for thread-safe access to status
WIN_HANDLES = None
script_dir = os.path.dirname(os.path.abspath(__file__))

########################################
### Blender Data & window Monitoring ###
########################################

class Blender:
    resolution_x = 1920
    resolution_y = 1080
    resolution_percentage = 100
    titleHeight = 0
    mainWindow = None
    windowBorderWidth = 0
    window = None
    windowHandle = None
    blenderHandle = None

class BlenderWindowMonitor:
    @classmethod
    def start(cls):
        cls.find_new_blender_window()
    
    @classmethod
    def find_blender_windows(cls):
        # Get all windows with 'Blender' in their title
        blender_windows = [window for window in gw.getWindowsWithTitle('Blender')]
        Blender.blenderHandle = blender_windows[0]._hWnd
        return blender_windows
    
    @classmethod
    def find_new_blender_window(cls):
        global status
        print(f"[BlenderRenderView] Waiting for viewport window...")
        SocketClient.update_status('extui_waiting')
        existingWindow = cls.find_blender_windows()
        while True:
            
            if status == "viewport_created":
                current_windows = cls.find_blender_windows()
                # Find the window that is not in existing_windows
                new_window = [window for window in current_windows if window not in existingWindow]
                if new_window:
                    Blender.window =  new_window[0]
                    Blender.windowHandle = Blender.window._hWnd
                    break
        cls.resize_window_to_resolution()
        SocketClient.update_status("extui_running")
        

    @classmethod    
    def get_new_blender_window_handle(cls):
        new_blender_window = cls.find_new_blender_window()
        if new_blender_window:
            return new_blender_window._hWnd  # Assuming _hWnd is the handle attribute
        else:
            return None
    
    @classmethod
    def resize_window_to_resolution(cls):
        if not Blender.window:
            return
        hwnd = Blender.windowHandle

        # Remove window borders and title bar
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style = style & ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME)
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

        # Remove extended window styles
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex_style = ex_style & ~(win32con.WS_EX_DLGMODALFRAME | win32con.WS_EX_WINDOWEDGE | win32con.WS_EX_CLIENTEDGE | win32con.WS_EX_STATICEDGE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
        
        # Resize the window
        resx = int(Blender.resolution_x * (Blender.resolution_percentage / 100))
        resy = int(Blender.resolution_y * (Blender.resolution_percentage / 100))
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, int(resx), int(resy), win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED)
        SocketClient.send_message({"resized":"true"})
        print(f"[BlenderRenderView] Blender viewport resized to {resx} x {resy} ({Blender.resolution_x} x {Blender.resolution_y} @ {Blender.resolution_percentage}%)")
        cls.move_window_offscreen()
        #win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
    
    @classmethod   
    def move_window_offscreen(cls):
        if not Blender.window:
            return
        hwnd = Blender.windowHandle

        user32 = ctypes.windll.user32
        screensize = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    
        #print(screensize[0])
        #print(screensize[1])
        # Move the window
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, screensize[0] - 1, screensize[1] -1, 0, 0,win32con.SWP_NOSIZE)
        
        # Ensure the window is visible and active
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

#################################################
### Socket CLient to communicate with blender ###
#################################################

class SocketClient:
    HOST = '127.0.0.1'
    PORT = 42069
    client_socket = None
    listener_thread = None

    @classmethod
    def start(cls, host=HOST, port=PORT):
        cls.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.client_socket.connect((host, port))
        cls.listener_thread = threading.Thread(target=cls.listen_for_updates)
        cls.listener_thread.daemon = True
        cls.listener_thread.start()

    @classmethod
    def listen_for_updates(cls):
        while True:
            try:
                data = cls.client_socket.recv(1024)
                if not data:
                    break
                try:
                    received_message = json.loads(data.decode('utf-8'))
                except:
                    print("Error in data")
                    continue
                cls.handle_message(received_message)
            except ConnectionResetError:
                print("Disconnected from server.")
                break
        time.sleep(1)

    @classmethod
    def handle_message(cls, message):
        if 'status' in message:
            cls.update_local_status(message['status'])
        if 'resolution_x' in message:
            Blender.resolution_x = message['resolution_x']
            Blender.resolution_y = message['resolution_y']
            Blender.resolution_percentage = message['resolution_percentage']
            BlenderWindowMonitor.resize_window_to_resolution()
        if 'renderview_running' in message:
            print("ok")
            mainWin.fitToZoom()

    @classmethod
    def update_local_status(cls, new_status):
        with status_lock:
            global status
            status = new_status
            #print(f"[BlenderRenderView] Updated status from blender:", status)

    @classmethod
    def update_status(cls, new_status):
        with status_lock:
            global status
            status = new_status
            cls.send_message({"status": status})
            #print(f"[BlenderRenderView] Updated status from External Ui:", status)

    @classmethod
    def send_message(cls, data):
        message_data = json.dumps(data).encode('utf-8')
        cls.client_socket.sendall(message_data)

    @classmethod
    def stop(cls):
        try:
            if cls.listener_thread and cls.listener_thread.is_alive():
                cls.listener_thread.join()
            if cls.client_socket:
                cls.client_socket.close()
        except Exception as e:
           print(f"[BlenderRenderView] [BRV] Can't stop socket client error: {e}")

################################
### Blender viewport capture ###
################################
class SignalEmitter(QObject):
    exit_signal = PySide6.QtCore.Signal()
    
# Initialize your signal emitter
signal_emitter = SignalEmitter()

class ScreenshotThread(QThread):
    imageCaptured = Signal(QPixmap)

    def __init__(self, window_handle):
        super().__init__()
        self.window_handle = Blender.windowHandle
        self._is_running = True
        
    def run(self):
        print("[BlenderRenderView] Capturing window..")
        while self._is_running:
            try:
                pixmap = self.screenshot_window(self.window_handle)
                if pixmap:
                    self.imageCaptured.emit(pixmap)
            except Exception as e:
                print(f"[BlenderRenderView] Fail to find blender window (closed). Exiting External UI.")
                signal_emitter.exit_signal.emit()
                break

    def stop(self):
        self._is_running = False
        self.wait()

    def capture_window(self, hwnd):
        global WIN_HANDLES

        from ctypes import windll

        import win32gui
        import win32ui

        if WIN_HANDLES is None:
            windll.user32.SetProcessDPIAware()
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            w = right - left
            h = bottom - top
            #print(f"Client rect: {left}, {top}, {right}, {bottom}")

            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()

            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, w, h)

            WIN_HANDLES = (hwnd, hwnd_dc, mfc_dc, save_dc, bitmap)

        (hwnd, hwnd_dc, mfc_dc, save_dc, bitmap) = WIN_HANDLES
        save_dc.SelectObject(bitmap)

        # If Special K is running, this number is 3. If not, 1
        result = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

        bmpinfo = bitmap.GetInfo()
        bmpstr = bitmap.GetBitmapBits(True)



        if result != 1:
            win32gui.DeleteObject(bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            WIN_HANDLES = None
            raise RuntimeError(f"Unable to acquire screenshot! Result: {result}")

        
        image = QImage(bmpstr, bmpinfo['bmWidth'], bmpinfo['bmHeight'], QImage.Format_ARGB32)
        pixmap = QPixmap.fromImage(image)
        return pixmap
        
    def screenshot_window(self, window_handle):
        global WIN_HANDLES
        hwnd = Blender.windowHandle
        if hwnd == 0:
            print(f"[BlenderRenderView] Window '{window_handle}' not found!")
            return None

        # whole window or just the client area.
        left, top, right, bottom = win32gui.GetClientRect(hwnd)

        #left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        #print(f"Client rect: {left}, {top}, {right}, {bottom}")
        
        hwndDC = None
        mfcDC = None
        saveDC = None
        saveBitMap = None

        try:
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            #result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 1)
            result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
            if result != 1:
                print(f"[BlenderRenderView] Failed to capture the window!")
                return None

            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)

            image = QImage(bmpstr, bmpinfo['bmWidth'], bmpinfo['bmHeight'], QImage.Format_ARGB32)
            pixmap = QPixmap.fromImage(image)
        except Exception as e:
            print(f"[BlenderRenderView] Error occurred: {e}")
            return None
        finally:
            if hwndDC:
                win32gui.ReleaseDC(hwnd, hwndDC)
            if saveBitMap:
                win32gui.DeleteObject(saveBitMap.GetHandle())
            if saveDC:
                saveDC.DeleteDC()
        return pixmap

##########
### UI ###
##########

### UI ELEMENTS ###
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
        self.setCursor(Qt.PointingHandCursor)  # Set the cursor to a pointing hand cursor
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._normal_icon is not None:
            self.setIcon(self._normal_icon)
        self.unsetCursor()  # Restore the default cursor
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        size = self.iconSize().width() - 5
        self.setIconSize(QSize(size, size))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        size = self.iconSize().width() + 5
        self.setIconSize(QSize(size, size))
        super().mouseReleaseEvent(event)

class CustomLineItem(QGraphicsLineItem):
    def __init__(self, x1, y1, x2, y2, color, width, parent=None):
        super().__init__(x1, y1, x2, y2, parent)
        
        # Set flags for selection and movement
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        # Set the pen for the line
        pen = QPen(color, width)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setAcceptHoverEvents(True)

    def setFiltersChildEvents(self, enabled: bool) -> None:
        return super().setFiltersChildEvents(enabled)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event) 

    def updateLineWidth(self, zoom_factor):
        # Adjust the line width based on the zoom factor to keep it consistent
        new_pen = QPen(self.pen.color(), self.width / zoom_factor)
        self.setPen(new_pen)

class CustomRectItem(QGraphicsRectItem):
    def __init__(self, x, y, width, height, color, parent=None):
        super().__init__(x, y, width, height, parent)

        # Set flags for selection and movement
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # Set the pen for the rectangle
        self.rect_pen = QPen(color)
        self.rect_pen.setWidth(2)  # Adjust the width of the pen as needed
        self.setPen(self.rect_pen)

    def boundingRect(self):
        # Return the bounding rectangle of the item (for collision detection)
        return super().boundingRect()

    def paint(self, painter, option, widget):
        # Draw the rectangle with the set pen
        painter.setPen(self.rect_pen)
        painter.drawRect(self.rect())

    def shape(self):
        # Define the shape of the item for collision detection
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        # Change cursor shape on hover
        self.setCursor(Qt.SizeHorCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        # Restore default cursor shape
        self.setCursor(Qt.OpenHandCursor)
        super().hoverLeaveEvent(event)

### Main image display ###
class ImageViewer(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._original_drag_mode = self.dragMode()

        # Create and add a large background rectangle item
        self.background_item = QGraphicsRectItem(-64000, -64000, 128000, 128000)
        self.background_item.setBrush(Qt.transparent)
        self.scene.addItem(self.background_item)

        self.image_item = QGraphicsPixmapItem()
        self.scene.addItem(self.image_item)

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

        self.line_item = CustomLineItem(0, -32000, 0, 32000, Qt.blue, self.linewidth, self.rect_item)
        self.line_item.setFlag(QGraphicsRectItem.ItemIsSelectable, False)
        self.line_item.setFlag(QGraphicsRectItem.ItemIsFocusable, False)
        self.line_item.setAcceptedMouseButtons(Qt.NoButton)  # This makes it non-interactive
        self.scene.addItem(self.line_item)

        self.setMouseTracking(True)
        self.middle_button_pressed = False
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)

        self._drawing_rect = False
        self._start_point = None
        self._rect_item = None
        self._debug_rect_item = None
        self._waiting_for_release = False
        self.setDragMode(QGraphicsView.NoDrag)
    
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
        if event.button() == Qt.LeftButton:
            if self._debug_rect_item and  self._debug_rect_item.scene() == self.scene: self.scene.removeItem(self._debug_rect_item) 
            if self._waiting_for_release and self._drawing_rect:
                self._waiting_for_release = False
                self._drawing_rect = True
                self._start_point = self.mapToScene(event.position().toPoint())
                self._rect_item = QGraphicsRectItem()
                pen = QPen()
                pen.setStyle(Qt.DashDotLine)
                pen.setCosmetic(True)
                pen.setColor(Qt.gray)
                pen.setWidth(1)
                pen.setDashPattern
                self._rect_item.setPen(pen)
                self._rect_item.setRect(QRectF(self._start_point, self._start_point))
                self.scene.addItem(self._rect_item)
        elif event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.middle_button_pressed = True
            self.setCursor(Qt.ClosedHandCursor)
            self.last_mouse_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing_rect and self._start_point is not None:
            end_point = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._start_point, end_point)
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
                pen = QPen()
                pen.setStyle(Qt.DashDotLine)
                pen.setCosmetic(True)
                pen.setColor(Qt.gray)
                pen.setWidth(1)
                pen.setDashPattern
                self._debug_rect_item.setPen(pen)
                #self.scene.addItem(self._debug_rect_item)

                # Calculate percentage coordinates relative to image size
                image_width = image_rect.width()
                image_height = image_rect.height()

                xmin_percent = (intersected_left - image_rect.left()) / image_width
                xmax_percent = (intersected_right - image_rect.left()) / image_width
                ymin_percent = (image_rect.bottom() - intersected_bottom) / image_height
                ymax_percent = (image_rect.bottom() - intersected_top) / image_height
                
                SocketClient.send_message({
                    "render_region": "true",
                    "xmin": f"{xmin_percent:.2f}",
                    "ymin": f"{ymin_percent:.2f}",
                    "xmax": f"{xmax_percent:.2f}",
                    "ymax": f"{ymax_percent:.2f}"
                })

        super().mouseReleaseEvent(event)

    def startRenderRegionDrawing(self):
        self._drawing_rect = True

### Bottom Horizontal Scrollbar for snapshot ###
class SnapshotThumbs(QLabel):
    clicked = Signal(object)

    def __init__(self, fullres, parent=None):
        super().__init__(parent)
        self.snapshot_fullres = fullres
        self.toggled = False
        self.is_set_as_a = False  # Flag to track if set as A
        self.is_set_as_b = False  # Flag to track if set as B
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
                mainWin.unsetOverlayA()
            else:
                # Set as A
                mainWin.setOverlayA(self.snapshot_fullres, self)  # Set overlay

        elif action == set_b_action:
            if self.is_set_as_b:
                # Unset B
                self.unmark()
                mainWin.unsetOverlayB()
            else:
                # Set as B
                self.mark_as("B")
                mainWin.setOverlayB(self.snapshot_fullres, self)  # Set overlay
        
        elif action == delete_action:
            self.unmark()
            parent_widget = self.parent()
            if parent_widget is not None:
                parent_widget.layout().removeWidget(self)
                self.deleteLater()  # Properly delete the widget

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
        if self.is_set_as_a: self.is_set_as_a = False;mainWin.unsetOverlayA()
        if self.is_set_as_b: self.is_set_as_b = False;mainWin.unsetOverlayB()
        self.label.hide()
        self.label.setText("")

### Global Hotkeys ###
class KeyPressFilter(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Left:
                self.main_window.navigate_thumbnails(-1)
                return True
            elif event.key() == Qt.Key_Right:
                self.main_window.navigate_thumbnails(1)
                return True
            elif event.key() == Qt.Key_Delete:
                self.main_window.deleteCurrent()
        return False

### Main UI ###
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.blender_hwnd = None
        self.initUI()
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
        self.screenshot_thread = ScreenshotThread(Blender.windowHandle)
        self.screenshot_thread.imageCaptured.connect(self.updateImage)
        self.screenshot_thread.start()

        self.lastHeight = 0
        self.lastWidth = 0
        # Install the event filter on the main window
        self.key_press_filter = KeyPressFilter(self)
        QApplication.instance().installEventFilter(self.key_press_filter)

        self.setWindowFlags(self.windowFlags() | Qt.Window)  # Ensure it's a top-level window

    def initUI(self):

        #self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)  # Set the window as top-most

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
        self.setWindowTitle('Blender RenderView (0.1)')
        self.showMaximized()  # Start the main window maximized
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
        # List of tuples containing image paths and corresponding functions
        button_data = [
            (os.path.join(script_dir, 'icons/save.png'), self.saveAs),
            (os.path.join(script_dir, 'icons/snapshot.png'), self.snapshot),
            (os.path.join(script_dir, 'icons/ratio.png'), self.fitToZoom),
            (os.path.join(script_dir, 'icons/region.png'), self.renderRegion),
        ]

        icon_size_px = QSize(25, 25)

        # Get the device pixel ratio for scaling
        scale_factor = QApplication.primaryScreen().devicePixelRatio()
        scaled_size = icon_size_px * scale_factor

        # Create buttons with custom images and connect to functions
        for image_path, function in button_data:
            button = CustomPushButton()
            normal_pixmap = QPixmap(image_path).scaled(scaled_size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            hover_image = QImage(image_path).scaled(scaled_size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            hover_image.invertPixels()  # Invert the hover icon colors
            hover_pixmap = QPixmap.fromImage(hover_image)
            button.setNormalIcon(QIcon(normal_pixmap))
            button.setHoverIcon(QIcon(hover_pixmap))
            button.setIconSize(icon_size_px)  # Set the icon size to the original defined size (in pixels)
            button.setFixedSize(scaled_size)  # Set the button size to the scaled size (in physical pixels)
            button.clicked.connect(function)  # Connect the click signal to the corresponding function
            h_layout.addWidget(button)

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
        print("removed overlay A")

    def unsetOverlayB(self):
        self.overlay_B = None
        self.current_b_thumb = None
        print("removed overlay B")

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

        if overlay_A and overlay_B:
            self.viewer.line_item.setVisible(True)
            self.viewer.rect_item.setVisible(True)
            #painter.drawPixmap(0, 0, self.apply_line_mask(base_pixmap, overlay_A, overlay_B, self.viewer.line_item))
            masked_pixmap = self.apply_line_mask(base_pixmap, overlay_A, overlay_B, self.viewer.line_item)
            x_offset, y_offset = get_centered_offset(masked_pixmap, max_width, max_height)
            painter.drawPixmap(x_offset, y_offset, masked_pixmap)
        else:
            self.viewer.line_item.setVisible(False)
            self.viewer.rect_item.setVisible(False)
        painter.end()
        return QPixmap.fromImage(result_image)
        
    def updateImage(self, pixmap):
        current_transform = self.viewer.transform()
        liveview = pixmap
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

        self.viewer.setImage(blended_pixmap)
        self.viewer.setTransform(current_transform)

    def add_image(self, pixmap):
        if pixmap.isNull():
            print(f"[BlenderRenderView] No image to add")
            return

        # Scale the pixmap to fit within a 200x200 bounding box while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(QSize(200, 200), Qt.KeepAspectRatio, Qt.SmoothTransformation)

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
        self.viewer.startRenderRegionDrawing()

    def closeEvent(self, event):
        self.screenshot_thread.stop()
        event.accept()

def on_exit():
    SocketClient.update_status('extui_exited')
    SocketClient.stop()

if __name__ == "__main__":
    SocketClient.start()

    app = QApplication(sys.argv + ['-platform', 'windows:darkmode=1'])
    app.setStyle('Fusion')

    # Define a dark theme stylesheet for Fusion style
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark_palette)



    BlenderWindowMonitor.start()
    mainWin = MainWindow()
    mainWin.show()

    # Connect the exit signal to the application's quit method
    signal_emitter.exit_signal.connect(app.quit)

    atexit.register(on_exit)
    sys.exit(app.exec())