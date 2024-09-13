bl_info = {
    "name": "[BRV] Blender Render View",
    "blender": (4, 2, 0),
    "version": (0, 1, 0),
    "category": "Interface",
    "author": "Eisteed"
}

import json
import selectors
import socket
from subprocess import Popen
import threading
import os
import time
from time import sleep
import bpy # type: ignore
from bpy.props import StringProperty, PointerProperty # type: ignore
from bpy.types import AddonPreferences, Operator # type: ignore
from bpy.app.handlers import persistent # type: ignore

PORT = 42069

addon_keymaps = []
extUiLog = ""
extUiReady = False
extUiProc = None
firstRun = True
status = {'status': 'initial'}  # Global status variable
status_lock = threading.Lock()  # Lock for thread-safe access to status
renderWindow = None
resX = ""
resY = ""
resP = ""
xmin = 1
ymin = 1
xmax = 1
ymax = 1

script_dir = os.path.dirname(os.path.abspath(__file__))

class render:
    Window = None
     
class CenterCam(Operator):
    
    """Aligns the 3D View to the active camera and zooms"""
    bl_idname = "brv.align_camera"
    bl_label = "Align Camera and Zoom"
    
    def execute(self, context):
        global firstRun
        for window in bpy.context.window_manager.windows:
            if window == render.Window:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        region = next((region for region in area.regions if region.type == 'WINDOW'), None)
                        if region:
                            with bpy.context.temp_override(window=window, area=area, region=region):
                                if bpy.ops.view3d.view_center_camera.poll():
                                    bpy.ops.view3d.view_center_camera()
                                if bpy.ops.view3d.zoom_camera_1_to_1.poll():
                                    bpy.ops.view3d.zoom_camera_1_to_1()
        return {'FINISHED'}
    
def run_align_camera_operator():
    bpy.ops.brv.align_camera()
    return None  # To stop the timer from repeating

class RenderRegion(Operator):
    global xmin, ymin, xmax, ymax
    """Set and enable render region"""
    bl_idname = "brv.set_render_region"
    bl_label = "Set Renger Region"
    
    def execute(self, context):
        bpy.context.scene.render.border_min_x = float(xmin)
        bpy.context.scene.render.border_min_y = float(ymin)
        bpy.context.scene.render.border_max_x = float(xmax)
        bpy.context.scene.render.border_max_y = float(ymax)
        bpy.context.scene.render.use_border = True
        return {'FINISHED'}
    
def run_render_region_operator():
    bpy.ops.brv.set_render_region()
    return None  # To stop the timer from repeating

# Wrapper function
def check_resolution_wrapper():
    global firstRun
    if status == "extui_running":
        if firstRun: bpy.app.timers.register(run_align_camera_operator, first_interval=1)
        #BlenderMonitor.check_resolution()
        if status == "extui_exited":
            bpy.app.timers.register(closeRenderWindow, first_interval=1)
            firstRun = True
    return 2.0  # Return interval for next call (in seconds)

class SocketServer:

    HOST = '127.0.0.1'
    PORT = 42069
    listener_thread = None
    server_socket = None
    stop_event = threading.Event()
    sel = selectors.DefaultSelector()
    clients = {}

    @classmethod
    def start(cls, host=HOST, port=PORT):
        if cls.is_port_in_use(host, port):
            print(f"[brv] Error port {port} already in use")
        else:
            cls.stop_event.clear()
            cls.listener_thread = threading.Thread(target=cls.listen_for_commands, args=(host, port))
            cls.listener_thread.daemon = True
            cls.listener_thread.start()

    @classmethod
    def is_port_in_use(cls, host, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as temp_socket:
            try:
                temp_socket.bind((host, port))
                return False
            except socket.error:
                return True

    @classmethod
    def listen_for_commands(cls, host, port):
        cls.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cls.server_socket.bind((host, port))
        cls.server_socket.listen()
        cls.server_socket.setblocking(False)
        cls.sel.register(cls.server_socket, selectors.EVENT_READ, cls.accept)

        print(f"[BRV] Socket Server Started. Listening on {host}:{port}...")
        while not cls.stop_event.is_set():
            events = cls.sel.select(timeout=1)
            for key, mask in events:
                callback = key.data
                callback(key.fileobj, mask)
        cls.server_socket.close()
        print(f"[BRV] Socket server stopped.")

    @classmethod
    def accept(cls, sock, mask):
        conn, addr = sock.accept()
        print(f"[BRV] Connection from {addr}")
        conn.setblocking(False)
        cls.sel.register(conn, selectors.EVENT_READ, cls.handle_client)
        cls.clients[conn] = addr

    @classmethod
    def handle_client(cls, conn, mask):
        try:
            data = conn.recv(1024)
            if data:
                received_json = json.loads(data.decode('utf-8'))
                cls.handle_message(received_json, conn)
            else:
                cls.disconnect(conn)
        except ConnectionResetError:
            cls.disconnect(conn)

    @classmethod
    def handle_message(cls, message, conn):
        if 'status' in message:
            cls.update_local_status(message['status'])
        if 'resolution' in message:
            cls.update_resolution(message['resolution'])
        if 'resized' in message:
            bpy.app.timers.register(run_align_camera_operator, first_interval=0.5)
        if 'render_region' in message:
            global xmin, ymin, xmax, ymax
            xmin = message['xmin']
            ymin = message['ymin']
            xmax = message['xmax']
            ymax = message['ymax']
            bpy.app.timers.register(run_render_region_operator, first_interval=0.5)
    @classmethod
    def update_local_status(cls, new_status):
        global status
        status = new_status
        if status == 'extui_exited':
            status = "init"
            bpy.app.timers.register(closeRenderWindow, first_interval=1)
        #print("[BRV] Status Updated Locally: " + str(status))

    @classmethod
    def update_status(cls, new_status):
        global status
        status = new_status
        cls.notify_clients_status()
        #print("[BRV] Status Updated: " + str(status))

    @classmethod
    def notify_clients_status(cls):
        global status
        status_data = json.dumps({"status": status}).encode('utf-8')
        for conn in list(cls.clients):
            try:
                conn.sendall(status_data)
            except Exception as e:
                print(f"[BRV] Error notifying client: {e}")
                cls.disconnect(conn)
    
    @classmethod
    def notify_clients_data(cls, dictionary):
        # Convert the data dictionary to a JSON string and encode it to bytes
        message = json.dumps(dictionary).encode('utf-8')
        # Send data to each client
        for conn in list(cls.clients):
            try:
                conn.sendall(message)
            except Exception as e:
                print(f"[BRV] Error notifying client: {e}")
                cls.disconnect(conn)
    @classmethod
    def disconnect(cls, conn):
        print(f"[BRV] Disconnecting {cls.clients[conn]}")
        cls.sel.unregister(conn)
        conn.close()
        del cls.clients[conn]

    @classmethod
    def stop(cls):
        try:
            cls.stop_event.set()
            if cls.listener_thread.is_alive():
                cls.listener_thread.join()
            for conn in list(cls.clients):
                cls.disconnect(conn)
            if cls.server_socket:
                cls.server_socket.close()
        except Exception as e:
            print(f"[BRV] Can't stop socket server error, please restart blender. {e}")

class CreateCleanRenderedViewOperator(Operator):
    bl_idname = "brw.create_clean_rendered_view"
    bl_label = "[BRV] Blender RenderWindow"
    bl_description = "Create a new Blender instance with no UI elements and rendered viewport shading to be used with external RenderWindow UI."

    def execute(self, context):
        global resX,resY,resP, status, renderWindow

        start_external_script()
     
        while True:
            tries = 0
            if status == "extui_waiting":
                break
            else:
                tries = tries + 1
            time.sleep(1)
            if tries > 5:
                print("[BRV] Failed to load / connect to external ui..")
                return('FINISHED')
            break
        # Send Scene resolution to external ui
        check_and_send_resolution()

        # Step 1: Create a new main window
        bpy.ops.wm.window_new_main()

        # Get the new window and its screen
        new_window = bpy.context.window_manager.windows[-1]
        renderWindow = new_window
        new_screen = new_window.screen

        # Step 2: Change an existing area to a 3D Viewport
        new_area = new_screen.areas[0]  # We'll just take the first area for simplicity
        new_area.type = 'VIEW_3D'
        # Set the new area to use the active camera and rendered shading mode
        for space in new_area.spaces:
            if space.type == 'VIEW_3D':
                space.region_3d.view_perspective = 'CAMERA'
                space.shading.type = 'RENDERED'
                space.overlay.show_overlays = False
                space.show_region_header = False
                space.show_region_toolbar = False
                space.show_gizmo = False

                new_region = next((region for region in new_area.regions if region.type == 'WINDOW'), None)

                with bpy.context.temp_override(window=new_window, area=new_area, region=new_region):
                    bpy.ops.screen.screen_full_area(use_hide_panels=True)

        render.Window = new_window

        bpy.context.scene.camera.data.show_passepartout = False
        bpy.context.scene.camera.data.passepartout_alpha = 0
        resX = bpy.context.scene.render.resolution_x
        resY = bpy.context.scene.render.resolution_y
        resP = bpy.context.scene.render.resolution_percentage
        SocketServer.update_status('viewport_created')

        return {'FINISHED'}
    
def closeRenderWindow():
    if render.Window:
        with bpy.context.temp_override(window=render.Window):
            print("[BRV] Blender Render View closed.")
            bpy.ops.wm.window_close()
            render.Window = None
        return None

load_post_done = False
@persistent
def load_pre_handler(idk):
    bpy.app.timers.register(closeRenderWindow, first_interval=1)
    
def check_and_send_resolution():
    global res_updating
    global resX, resY, resP
    current_res_x = bpy.context.scene.render.resolution_x
    current_res_y = bpy.context.scene.render.resolution_y
    current_res_p = bpy.context.scene.render.resolution_percentage
    if current_res_x != resX or current_res_y != resY or current_res_p != resP:
        resX = current_res_x
        resY = current_res_y
        resP = current_res_p
        resolution_data = {
            "resolution_x": resX,
            "resolution_y": resY,
            "resolution_percentage": resP
        } 
        SocketServer.notify_clients_data(resolution_data)
    res_updating = False

res_updating = False
def desgraph_post_handler(scene, depsgraph):
    global res_updating, status

    if not res_updating:
        res_updating = True
        print("checking res")
        bpy.app.timers.register(check_and_send_resolution, first_interval=1)

def register():

    bpy.app.handlers.load_post.append(load_pre_handler)
    bpy.app.handlers.depsgraph_update_post.append(desgraph_post_handler)
    #bpy.app.timers.register(check_resolution_wrapper)
    bpy.utils.register_class(CenterCam)
    bpy.utils.register_class(RenderRegion)
    bpy.utils.register_class(CreateCleanRenderedViewOperator)
    # Add the hotkey
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')

    # Register hotkey for Starting render view (default: ctrl alt R)
        kmi = km.keymap_items.new(CreateCleanRenderedViewOperator.bl_idname, 'R', 'PRESS', ctrl=True, alt=True)
        addon_keymaps.append((km, kmi))

    SocketServer.start()

    #BlenderMonitor.start()

def unregister():
    SocketServer.stop()
    bpy.app.handlers.load_post.remove(load_pre_handler)
    bpy.app.handlers.depsgraph_update_post.remove(desgraph_post_handler)
    bpy.utils.unregister_class(CenterCam)
    bpy.utils.unregister_class(RenderRegion)
    bpy.utils.unregister_class(CreateCleanRenderedViewOperator)

    # Remove keymap entry
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except ValueError:
            pass  # Keymap item was already removed or never added
    addon_keymaps.clear()

    global extUiProc
    try:
        Popen.kill(extUiProc)
        extUiProc = None
        print("[BRV] Killing external Ui. Exiting.")
    except:
        print("[BRV] No active external Ui. Exiting.")

def run_compiled_script():
    global extUiProc
    # Define the path to the compiled executabl
    executable_path = os.path.join(script_dir,"dist/RenderWindow_ui.exe")  
    extUiProc = Popen([executable_path])

def start_external_script():
    
    global extUiProc
    executable_path = os.path.join(script_dir,"dist/RenderWindow_ui.exe")  
    filepath = os.path.join(script_dir,"RenderView_ui.py")

    # # path to python.exe
    # python_exe = os.path.join(sys.prefix, 'bin', 'python.exe')
    
    # # upgrade pip
    # subprocess.call([python_exe, "-m", "ensurepip"])
    # subprocess.call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])
    
    # # install required packages
    # subprocess.call([python_exe, "-m", "pip", "install", "pyside6"])
    # subprocess.call([python_exe, "-m", "pip", "install", "pyautogui"])
    # subprocess.call([python_exe, "-m", "pip", "install", "pygetwindow"])
    # subprocess.call([python_exe, "-m", "pip", "install", "pywin32"])
    # print("DONE")

    #exec(compile(open(filepath).read(), filepath, 'exec'))
    extUiProc = Popen(['python', filepath])
    #extUiProc = Popen([executable_path])

if __name__ == "__main__":
    register()

    