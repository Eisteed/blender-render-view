
from PySide6.QtCore import QThread, Signal, QObject   # type: ignore
from PySide6.QtGui import QPixmap, QImage  # type: ignore
import ctypes
import time
import win32gui  # type: ignore
import win32ui  # type: ignore
from core import signal
from blender import data

WIN_HANDLES = None

# PrintWindow flags
PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002

class ScreenshotThread(QThread):
    imageCaptured = Signal(QPixmap)

    def __init__(self, window_handle):
        super().__init__()
        self.window_handle = window_handle
        self._is_running = True
        self._target_fps = 30
        self._frame_time = 1.0 / self._target_fps
        self._debug_counter = 0

    def run(self):
        while self._is_running:
            start_time = time.perf_counter()

            self._debug_counter += 1
            self.window_handle = data.Blender.windowHandle

            if data.Blender.windowHandle is not None:
                try:
                    pixmap = self.screenshot_window(self.window_handle)
                    if pixmap:
                        self.imageCaptured.emit(pixmap)
                except Exception as e:
                    print(f"[BRV-UI] Error capturing viewport: {e}")

            # FPS limiting
            elapsed = time.perf_counter() - start_time
            sleep_time = self._frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

 
    def stop(self):
        self._is_running = False
        self.wait()

    def screenshot_window(self, hwnd):
        global WIN_HANDLES
        if hwnd == 0 or hwnd is None:
            return None

        # Check if window is valid
        if not win32gui.IsWindow(hwnd):
            print(f"[BRV-UI] Invalid window handle: {hwnd}")
            return None

        try:
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
        except Exception as e:
            print(f"[BRV-UI] GetClientRect failed: {e}")
            return None

        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            print(f"[BRV-UI] Invalid window size: {width}x{height}")
            return None

        hwndDC = None
        mfcDC = None
        saveDC = None
        saveBitMap = None
        pixmap = None

        try:
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            # Try different PrintWindow flags
            # PW_RENDERFULLCONTENT (2) - best for DWM/hardware accelerated windows
            # PW_CLIENTONLY (1) - client area only
            # Flag 0 - basic PrintWindow
            flags_to_try = [
                PW_RENDERFULLCONTENT | PW_CLIENTONLY,  # 3 - combined flags
                PW_RENDERFULLCONTENT,                   # 2 - full content
                PW_CLIENTONLY,                          # 1 - client only
                0                                       # 0 - basic
            ]

            result = 0
            for flag in flags_to_try:
                result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), flag)
                if result == 1:
                    break

            if result != 1:
                print(f"[BRV-UI] PrintWindow failed for hwnd {hwnd}, all flags failed")
                return None

            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            image = QImage(bmpstr, bmpinfo['bmWidth'], bmpinfo['bmHeight'], QImage.Format_ARGB32)
            pixmap = QPixmap.fromImage(image)

        except Exception as e:
            print(f"[BRV-UI] Screenshot exception: {e}")
            return None

        finally:
            # Cleanup in reverse order of creation
            # Use try/except for each to ensure all resources are released
            try:
                if saveBitMap:
                    win32gui.DeleteObject(saveBitMap.GetHandle())
            except:
                pass
            try:
                if saveDC:
                    saveDC.DeleteDC()
            except:
                pass
            # Don't call mfcDC.DeleteDC() - it doesn't own the DC, just wraps hwndDC
            try:
                if hwndDC and hwnd:
                    win32gui.ReleaseDC(hwnd, hwndDC)
            except:
                pass

        return pixmap