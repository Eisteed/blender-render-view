
import threading, os, ctypes
from time import sleep 
from core.socket_client import SocketClient
import pygetwindow as gw # type: ignore
import win32con, win32gui  # type: ignore
from blender import data

class BlenderWindowMonitor:
    @classmethod
    def start(cls):
        cls.find_new_blender_window()
        cls.monitor_thread = threading.Thread(target=cls.monitor)
        cls.monitor_thread.daemon = True
        cls.monitor_thread.start()
        cls.sending_data = False

    @classmethod
    def monitor(cls):

        while True:
            if SocketClient.status == "extui_running":
                SocketClient.send_message({"render_pass": f"{data.Blender.renderPassActive}"})
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
        tries = 0
        while tries <= 5:
            if SocketClient.status == "viewport_created":
                current_windows = cls.find_blender_windows()
                new_window = [w for w in current_windows if w not in existingWindow]
                if new_window:
                    data.Blender.window = new_window[0]
                    data.Blender.windowHandle = data.Blender.window._hWnd
                    if(data.Blender.debug):print(f"[BRV-UI] Blender viewport window found :", {data.Blender.window._hWnd})
                    cls.resize_window_to_resolution()
                    SocketClient.update_status("extui_running")
                    break
            tries += 1
            sleep(0.5)

    @classmethod
    def is_window_handle_valid(cls, handle):
        return handle is not None and win32gui.IsWindow(handle)

    @classmethod
    def resize_window_to_resolution(cls):
        if not data.Blender.windowHandle:
            if(data.Blender.debug):print(f"[BRV-UI] Blender Window is null !")
        else:
            hwnd = data.Blender.windowHandle

            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            style = style & ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME)
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style = ex_style & ~(win32con.WS_EX_DLGMODALFRAME | win32con.WS_EX_WINDOWEDGE |
                                    win32con.WS_EX_CLIENTEDGE | win32con.WS_EX_STATICEDGE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

            resx = int(data.Blender.resolution_x * (data.Blender.resolution_percentage / 100))
            resy = int(data.Blender.resolution_y * (data.Blender.resolution_percentage / 100))
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, resx, resy,
                                win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED)
            cls.move_window_offscreen()


    @classmethod
    def move_window_offscreen(cls):
        if not data.Blender.windowHandle:
            if(data.Blender.debug):print(f"[BRV-UI] Blender Window is null !")
        else:
            hwnd = data.Blender.windowHandle
            screensize = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, screensize[0] - 2, screensize[1] - 2, 0, 0,
                                win32con.SWP_NOSIZE)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)