import sys
sys.dont_write_bytecode = True

import json
import multiprocessing
import subprocess
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
#from .functions.showMessage import msgbox
from . import global_Vars
from .functions import setRenderPass

# Change port number to avoid conflict with other addons,
# Use the same inside renderview_ui/init.py if conflict with other addons
PORT = 42082

script_dir = os.path.dirname(os.path.abspath(__file__))
addon_keymaps = []

class SocketServer:
    global PORT
    HOST = '127.0.0.1'
    listener_thread = None
    server_socket = None
    stop_event = threading.Event()
    sel = selectors.DefaultSelector()
    clients = {}

    @classmethod
    def start(cls, host=HOST, port=PORT):
        if cls.is_port_in_use(host, port):
           print(f"[BRV] Error port {port} already in use")
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

        if(global_Vars.debug):print(f"[BRV] Socket Server Started. Listening on {host}:{port}...")
        while not cls.stop_event.is_set():
            events = cls.sel.select(timeout=1)
            for key, mask in events:
                callback = key.data
                callback(key.fileobj, mask)
        cls.server_socket.close()
        if(global_Vars.debug):print(f"[BRV] Socket server stopped.")

    @classmethod
    def accept(cls, sock, mask):
        conn, addr = sock.accept()
        #if(global_Vars.debug):print(f"[BRV] Connection from {addr}")
        conn.setblocking(False)
        cls.sel.register(conn, selectors.EVENT_READ, cls.handle_client)
        cls.clients[conn] = addr

    @classmethod
    def handle_client(cls, conn, mask):
        try:
            data = conn.recv(1024)
            if data:
                try:
                    received_json = json.loads(data.decode('utf-8'))
                    cls.handle_message(received_json, conn)
                    #if(global_Vars.debug):print(f"[BRV] Received: {received_json}")
                except json.JSONDecodeError as e:
                    if(global_Vars.debug):print(f"[BRV] JSONDecodeError: {e}")
                    if(global_Vars.debug):print(f"[BRV] Raw data: {data}")
            else:
                cls.disconnect(conn)
        except ConnectionResetError:
            cls.disconnect(conn)
        except Exception as e:
            print(f"[BRV] Unexpected error: {e}")

    @classmethod
    def handle_message(cls, message, conn):
        if 'status' in message:
            cls.update_local_status(message['status'])
        if 'resolution' in message:
            cls.update_resolution(message['resolution'])
        if 'render_region' in message:
            if(message['render_region'] == "true"):
                global_Vars.rr_enabled = True
                global_Vars.xmin = message['xmin']
                global_Vars.ymin = message['ymin']
                global_Vars.xmax = message['xmax']
                global_Vars.ymax = message['ymax']
            else:
                global_Vars.rr_enabled = False
            bpy.app.timers.register(run_render_region_operator, first_interval=0.1)
        if 'render_pass' in message:
            global_Vars.renderPass = message['render_pass']
            #if(global_Vars.debug):print(f"received render_pass: {message['render_pass']}")
            setRenderPass.run(bpy.context)
    @classmethod
    def update_local_status(cls, new_status):
        global_Vars.status = new_status
        if global_Vars.status == 'extui_exited':
            bpy.app.timers.register(closeRenderWindow, first_interval=1)
        #if(global_Vars.debug):print("[BRV] status Received: " + str(status))

    @classmethod
    def update_status(cls, new_status):
        global_Vars.status = new_status
        cls.notify_clients_status()
        #if(global_Vars.debug):print("[BRV] status Updated: " + str(status))

    @classmethod
    def notify_clients_status(cls):
        status_data = json.dumps({"status": global_Vars.status}).encode('utf-8')
        for conn in list(cls.clients):
            try:
                conn.sendall(status_data)
            except Exception as e:
                if(global_Vars.debug):print(f"[BRV] Error notifying client: {e}")
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
                if(global_Vars.debug):print(f"[BRV] Error notifying client: {e}")
                cls.disconnect(conn)
    @classmethod
    def disconnect(cls, conn):
        if(global_Vars.debug):print(f"[BRV] Disconnecting {cls.clients[conn]}")
        cls.sel.unregister(conn)
        conn.close()
        del cls.clients[conn]

    @classmethod
    def stop(cls):
        try:
            cls.stop_event.set()

            if cls.server_socket:
                try:
                    cls.sel.unregister(cls.server_socket)
                except Exception:
                    pass
                cls.server_socket.close()
                cls.server_socket = None

            for conn in list(cls.clients):
                cls.disconnect(conn)

            # Close and clear selector
            cls.sel.close()
            cls.sel = selectors.DefaultSelector()

            if cls.listener_thread and cls.listener_thread.is_alive():
                cls.listener_thread.join(timeout=2)
                cls.listener_thread = None

        except Exception as e:
            if(global_Vars.debug):print(f"[BRV] Can't stop socket server properly: {e}")  

class OP_CenterCam(Operator):
    
    """Aligns the 3D View to the active camera and zooms"""
    bl_idname = "brv.align_camera"
    bl_label = "Align Camera and Zoom"
    
    def execute(self, context):

        for window in bpy.context.window_manager.windows:
            if window == global_Vars.renderWindow:
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
    
class OP_RenderRegion(Operator):
    global rr_enabled, xmin, ymin, xmax, ymax
    """Set and enable render region"""
    bl_idname = "brv.set_render_region"
    bl_label = "Set Renger Region"

    def execute(self, context):
        #if(global_Vars.debug):print(f"[BRV] Set render region to :{rr_enabled}")
        bpy.context.scene.render.border_min_x = float(xmin)
        bpy.context.scene.render.border_min_y = float(ymin)
        bpy.context.scene.render.border_max_x = float(xmax)
        bpy.context.scene.render.border_max_y = float(ymax)
        bpy.context.scene.render.use_border = rr_enabled
        return {'FINISHED'}
    
def run_render_region_operator():
    bpy.ops.brv.set_render_region()
    return None 

class OP_CreateCleanRenderedView(Operator):
    bl_idname = "brw.create_clean_rendered_view"
    bl_label = "[BRV] Blender RenderWindow"
    bl_description = "Create a new Blender instance with no UI elements and rendered viewport shading to be used with external RenderWindow UI."

    def execute(self, context):
        if global_Vars.extUiProc is not None:
            if is_process_running(global_Vars.extUiProc):
                print(f"[BRV] External UI is already running: {global_Vars.extUiProc}")
                return {'FINISHED'}

        global_Vars.monitor = True
        global_Vars.firstRun = True

        bpy.app.timers.register(monitoring, first_interval=1)

        start_external_script()
        tries = 0
        while tries <= 5:
            if global_Vars.status == "extui_waiting":
                if(global_Vars.debug):print(f"[BRV] Connected to external ui..")

                # Step 1: Create a new main window
                bpy.ops.wm.window_new_main()

                # Get the new window and its screen
                new_window = bpy.context.window_manager.windows[-1]
                global_Vars.renderWindow = new_window
                new_screen = new_window.screen

                # Step 2: Change an existing area to a 3D Viewport
                new_area = new_screen.areas[0] 
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

                global_Vars.resX = bpy.context.scene.render.resolution_x
                global_Vars.resY = bpy.context.scene.render.resolution_y
                global_Vars.resP = bpy.context.scene.render.resolution_percentage

                SocketServer.update_status('viewport_created')
                return {'FINISHED'}

            tries += 1
            time.sleep(0.5)
        if tries > 5:
            if(global_Vars.debug):print(f"[BRV] Failed to load / connect to external ui..")
            #msgbox(context, "External UI failed to start", icon='ERROR', message_type='ERROR')
            return {'FINISHED'}

def start_external_script():
    site_packages_dir = None

    for path in sys.path:
        if path.endswith(r'extensions\.local\lib\python3.11\site-packages'):
            site_packages_dir = path
            break 

    if not site_packages_dir:
        if(global_Vars.debug):print(f"[BRV] Could not find site-packages directory in sys.path")
        if(global_Vars.debug):print(f"[BRV] Cannot start Blender Render View without it's dependencies.")
        return False

    addon_dir = os.path.dirname(__file__)
    run_script = os.path.join(addon_dir, "renderview_ui\\__init__.py")
    blender_exe = bpy.app.binary_path
    print(f"[BRV] Starting external UI..")
    flags = ['--background', '--factory-startup', '--quiet', '--python']
    global_Vars.extUiProc = Popen([blender_exe] + flags + [run_script])
    return True

def is_process_running(process):
    if process.poll() is None:
        return True 
    else:
        return False 

def closeRenderWindow():
    if global_Vars.renderWindow:
        try:
            with bpy.context.temp_override(window=global_Vars.renderWindow):
                if(global_Vars.debug):print("[BRV] Blender Rendered viewport closed.")
                bpy.ops.wm.window_close()
        except Exception as e:
            if(global_Vars.debug):print(f"[BRV] Blender Rendered viewport close failed: {str(e)}")
    global_Vars.renderWindow = None        
    status = "init"
    global_Vars.monitor = False
    global_Vars.extUiProc = None

def monitoring():
    if (global_Vars.monitor):
        if global_Vars.status == "extui_running":
            if (global_Vars.firstRun):
                resolution_data = {
                    "resolution_x": bpy.context.scene.render.resolution_x,
                    "resolution_y": bpy.context.scene.render.resolution_y,
                    "resolution_percentage": bpy.context.scene.render.resolution_percentage,
                    "first_run" : "true"
                }
                SocketServer.notify_clients_data(resolution_data)
                global_Vars.firstRun = False
            else:
                bpy.ops.brv.align_camera()
                if (not global_Vars.res_updating):
                    check_and_send_resolution()
        if global_Vars.status == "extui_exited":
            bpy.app.timers.register(closeRenderWindow, first_interval=0.1)
            return None
        return 1.0
    else:
        if(global_Vars.debug):print(f"[BRV] Monitoring stopped")
        return None
    
@persistent
def load_pre_handler(idk):
    bpy.app.timers.register(closeRenderWindow, first_interval=0.1)
    
def check_and_send_resolution():

    current_res_x = bpy.context.scene.render.resolution_x
    current_res_y = bpy.context.scene.render.resolution_y
    current_res_p = bpy.context.scene.render.resolution_percentage
    if (global_Vars.resX != current_res_x) or (global_Vars.resY != current_res_y) or (global_Vars.resX != current_res_x):
        global_Vars.resX = current_res_x
        global_Vars.resY = current_res_y
        global_Vars.resP = current_res_p
        if(global_Vars.debug):print(f"[BRV] Res Changed to : {global_Vars.resX}x{global_Vars.resY}@{global_Vars.resP}")
        resolution_data = {
            "resolution_x": global_Vars.resX,
            "resolution_y": global_Vars.resY,
            "resolution_percentage": global_Vars.resP
        } 
        SocketServer.notify_clients_data(resolution_data)

    global_Vars.res_updating = False

def register():
    bpy.types.TOPBAR_MT_render.prepend(draw_ipr_button)
    bpy.app.handlers.load_post.append(load_pre_handler)

    bpy.utils.register_class(OP_CenterCam)
    bpy.utils.register_class(OP_RenderRegion)
    bpy.utils.register_class(OP_CreateCleanRenderedView)

    # Add the hotkey
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = wm.keyconfigs.addon.keymaps.new(name='GLOBAL', space_type='VIEW_3D')

        # Register hotkey for Starting render view (default: ctrl alt R)
        kmi1 = km.keymap_items.new(OP_CreateCleanRenderedView.bl_idname, 'R', 'PRESS', ctrl=True, alt=True)
        addon_keymaps.append((km, kmi1))

    import importlib
    SocketServer.start()

def unregister():
    global_Vars.monitor = False
    SocketServer.stop()
    
    bpy.types.TOPBAR_MT_render.remove(draw_ipr_button)
    bpy.app.handlers.load_post.remove(load_pre_handler)

    bpy.utils.unregister_class(OP_CenterCam)
    bpy.utils.unregister_class(OP_RenderRegion)
    bpy.utils.unregister_class(OP_CreateCleanRenderedView)

    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except ValueError:
            pass
    addon_keymaps.clear()

    try:
        Popen.kill(global_Vars.extUiProc)
        if(global_Vars.debug):print("[BRV] Killing external Ui. Exiting.")
    except:
        if(global_Vars.debug):print("[BRV] No active external Ui Found. Exiting.")
    global_Vars.extUiProc = None

def draw_ipr_button(self, context):
    layout = self.layout
    layout.operator("brw.create_clean_rendered_view", text="Render View (IPR)", icon='IMAGE_DATA')

if __name__ == "__main__":
    register()