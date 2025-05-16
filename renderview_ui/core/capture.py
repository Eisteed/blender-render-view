
from PySide6.QtCore import QThread, Signal, QObject   # type: ignore
from PySide6.QtGui import QPixmap, QImage  # type: ignore
import ctypes
import win32gui  # type: ignore
import win32ui  # type: ignore
from core import signal
from blender import data

WIN_HANDLES = None

class ScreenshotThread(QThread):
    imageCaptured = Signal(QPixmap)

    def __init__(self, window_handle):
        super().__init__()
        self.window_handle = window_handle
        self._is_running = True

    def run(self):
        while self._is_running:
            self.window_handle = data.Blender.windowHandle
            if data.Blender.windowHandle is not None:
                try:
                    pixmap = self.screenshot_window(self.window_handle)
                    if pixmap:
                        self.imageCaptured.emit(pixmap)
                except Exception as e:
                    print(f"[BRV-UI] Error capturing viewport: {e}")  
                    signal.signal_emitter.close_mainwindow.emit()
                    break

 
    def stop(self):
        self._is_running = False
        self.wait()

    def screenshot_window(self, hwnd):
        global WIN_HANDLES
        if hwnd == 0:
            return None

        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        width = right - left
        height = bottom - top

        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
        saveDC.SelectObject(saveBitMap)

        result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
        if result != 1:
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            return None

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        image = QImage(bmpstr, bmpinfo['bmWidth'], bmpinfo['bmHeight'], QImage.Format_ARGB32)
        pixmap = QPixmap.fromImage(image)

        win32gui.ReleaseDC(hwnd, hwndDC)
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()

        return pixmap