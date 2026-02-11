
import threading, os, ctypes
from time import sleep 
from core.socket_client import SocketClient
import pygetwindow as gw # type: ignore
import win32con, win32gui  # type: ignore
from blender import data
from core import signal

class BlenderWindowMonitor:
    @classmethod
    def start(cls):
        cls.monitor_thread = threading.Thread(target=cls.monitor)
        cls.monitor_thread.daemon = True
        cls.monitor_thread.start()
        cls.sending_data = False

    @classmethod
    def monitor(cls):
        last_render_pass = None

        while True:
            if SocketClient.status == "extui_running":
                current_pass = data.Blender.renderPassActive
                if current_pass != last_render_pass:
                    SocketClient.send_message({"render_pass": f"{current_pass}"})
                    last_render_pass = current_pass
                sleep(0.1)

            if SocketClient.status == "extui_exited" or not (cls.is_window_handle_valid(data.Blender.windowHandle)):
                break
            sleep(1)

    @classmethod
    def find_blender_windows(cls):
        blender_windows = [window for window in gw.getWindowsWithTitle('- Blender ')]
        data.Blender.blenderHandle = blender_windows[0]._hWnd
        return blender_windows

    @classmethod
    def find_new_blender_window(cls):
        SocketClient.update_status('extui_waiting')
        if(data.Blender.debug):print(f"[BRV-UI] Waiting for viewport window...")
        existingWindow = cls.find_blender_windows()
        if(data.Blender.debug):print(f"[BRV-UI] Existing windows count: {len(existingWindow)}")
        tries = 0
        max_tries = 30  # 30 x 0.5s = 15 seconds max wait
        while tries <= max_tries:
            if(data.Blender.debug and tries % 5 == 0):print(f"[BRV-UI] Try {tries}, status: {SocketClient.status}")
            if SocketClient.status == "viewport_created":
                current_windows = cls.find_blender_windows()
                if(data.Blender.debug):print(f"[BRV-UI] Current windows count: {len(current_windows)}")
                new_window = [w for w in current_windows if w not in existingWindow]
                if new_window:
                    data.Blender.window = new_window[0]
                    data.Blender.windowHandle = data.Blender.window._hWnd
                    if(data.Blender.debug):
                        print(f"[BRV-UI] Blender viewport window found: {data.Blender.window._hWnd}")
                        print(f"[BRV-UI] Window title: {data.Blender.window.title}")
                        print(f"[BRV-UI] Window size: {data.Blender.window.width}x{data.Blender.window.height}")
                    cls.resize_window_to_resolution()
                    SocketClient.update_status("extui_running")
                    return True
                else:
                    if(data.Blender.debug):print(f"[BRV-UI] No new window found yet...")
            tries += 1
            sleep(0.5)
        if(data.Blender.debug):print(f"[BRV-UI] Failed to find viewport window after {tries} attempts")
        return False

    @classmethod
    def is_window_handle_valid(cls, handle):
        return handle is not None and win32gui.IsWindow(handle)

    @classmethod
    def resize_window_to_resolution(cls):
        if not data.Blender.windowHandle:
            if(data.Blender.debug):print(f"[BRV-UI] Blender Window is null !")
            return

        hwnd = data.Blender.windowHandle

        # Validate window handle before operations
        if not win32gui.IsWindow(hwnd):
            if(data.Blender.debug):print(f"[BRV-UI] Window handle {hwnd} is not valid!")
            return

        try:
            if(data.Blender.debug):print(f"[BRV-UI] Resizing window {hwnd}...")

            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            style = style & ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME)
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style = ex_style & ~(win32con.WS_EX_DLGMODALFRAME | win32con.WS_EX_WINDOWEDGE |
                                    win32con.WS_EX_CLIENTEDGE | win32con.WS_EX_STATICEDGE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

            resx = int(data.Blender.resolution_x * (data.Blender.resolution_percentage / 100))
            resy = int(data.Blender.resolution_y * (data.Blender.resolution_percentage / 100))

            # Ensure minimum size
            resx = max(resx, 100)
            resy = max(resy, 100)

            if(data.Blender.debug):print(f"[BRV-UI] Setting window size to {resx}x{resy}")

            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, resx, resy,
                                win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED)
            cls.move_window_offscreen()
        except Exception as e:
            if(data.Blender.debug):print(f"[BRV-UI] Error resizing window: {e}")


    @classmethod
    def move_window_offscreen(cls):
        if not data.Blender.windowHandle:
            if(data.Blender.debug):print(f"[BRV-UI] Blender Window is null !")
            return

        hwnd = data.Blender.windowHandle

        # Validate window handle
        if not win32gui.IsWindow(hwnd):
            if(data.Blender.debug):print(f"[BRV-UI] Window handle {hwnd} is not valid for move!")
            return

        try:
            # Get virtual screen metrics (all monitors)
            SM_XVIRTUALSCREEN = 76
            SM_CXVIRTUALSCREEN = 78

            virtual_x = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            virtual_width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)

            # Position window just off the right edge of all monitors
            # Keep 1 pixel visible to ensure PrintWindow can still capture
            off_x = virtual_x + virtual_width - 1

            if(data.Blender.debug):print(f"[BRV-UI] Moving window to offscreen position: ({off_x}, 0)")

            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, off_x, 0, 0, 0,
                                win32con.SWP_NOSIZE)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        except Exception as e:
            if(data.Blender.debug):print(f"[BRV-UI] Error moving window offscreen: {e}")