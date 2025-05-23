import sys
sys.dont_write_bytecode = True


import os

from time import sleep
from subprocess import Popen
import bpy # type: ignore
from bpy.props import StringProperty, PointerProperty # type: ignore
from bpy.types import AddonPreferences, Operator # type: ignore
from bpy.app.handlers import persistent # type: ignore
from . import global_vars
from .socket_server import SocketServer
from .functions import center_cam

script_dir = os.path.dirname(os.path.abspath(__file__))
addon_keymaps = []

class OP_CreateCleanRenderedView(Operator):
    bl_idname = "brw.create_clean_rendered_view"
    bl_label = "[BRV] Blender RenderWindow"
    bl_description = "Create a new Blender instance with no UI elements and rendered viewport shading to be used with external RenderWindow UI."

    def execute(self, context):
        if global_vars.extUiProc is not None:
            if is_process_running(global_vars.extUiProc):
                print(f"[BRV] External UI is already running: {global_vars.extUiProc}")
                return {'FINISHED'}

        global_vars.monitor = True
        global_vars.firstRun = True

        bpy.app.timers.register(monitoring, first_interval=1)

        start_external_script()
        tries = 0
        while tries <= 5:
            if global_vars.status == "extui_waiting":
                if(global_vars.debug):print(f"[BRV] Connected to external ui..")

                # Step 1: Create a new main window
                bpy.ops.wm.window_new_main()

                # Get the new window and its screen
                new_window = bpy.context.window_manager.windows[-1]
                global_vars.renderWindow = new_window
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

                global_vars.resX = bpy.context.scene.render.resolution_x
                global_vars.resY = bpy.context.scene.render.resolution_y
                global_vars.resP = bpy.context.scene.render.resolution_percentage

                SocketServer.update_status('viewport_created')
                return {'FINISHED'}

            tries += 1
            sleep(0.5)
        if tries > 5:
            if(global_vars.debug):print(f"[BRV] Failed to load / connect to external ui..")
            #msgbox(context, "External UI failed to start", icon='ERROR', message_type='ERROR')
            return {'FINISHED'}

def start_external_script():
    site_packages_dir = None

    for path in sys.path:
        if path.endswith(r'extensions\.local\lib\python3.11\site-packages'):
            site_packages_dir = path
            break 

    if not site_packages_dir:
        if(global_vars.debug):print(f"[BRV] Could not find site-packages directory in sys.path")
        if(global_vars.debug):print(f"[BRV] Cannot start Blender Render View without it's dependencies.")
        return False

    addon_dir = os.path.dirname(__file__)
    run_script = os.path.join(addon_dir, "renderview_ui\\__init__.py")
    blender_exe = bpy.app.binary_path
    print(f"[BRV] Starting external UI..")
    flags = ['--background', '--factory-startup', '--quiet', '--python']
    global_vars.extUiProc = Popen([blender_exe] + flags + [run_script])
    return True

def is_process_running(process):
    if process.poll() is None:
        return True 
    else:
        return False 

def closeRenderWindow():
    if global_vars.renderWindow:
        try:
            with bpy.context.temp_override(window=global_vars.renderWindow):
                if(global_vars.debug):print("[BRV] Blender Rendered viewport closed.")
                bpy.ops.wm.window_close()
        except Exception as e:
            if(global_vars.debug):print(f"[BRV] Blender Rendered viewport close failed: {str(e)}")
    global_vars.renderWindow = None        
    status = "init"
    global_vars.monitor = False
    global_vars.extUiProc = None

def monitoring():
    if (global_vars.monitor):
        if global_vars.status == "extui_running":
            if (global_vars.firstRun):
                resolution_data = {
                    "resolution_x": bpy.context.scene.render.resolution_x,
                    "resolution_y": bpy.context.scene.render.resolution_y,
                    "resolution_percentage": bpy.context.scene.render.resolution_percentage,
                    "first_run" : "true"
                }
                SocketServer.notify_clients_data(resolution_data)
                global_vars.firstRun = False
            else:
                center_cam.run(bpy, global_vars.renderWindow)
                if (not global_vars.res_updating):
                    check_and_send_resolution()
        if global_vars.status == "extui_exited":
            bpy.app.timers.register(closeRenderWindow, first_interval=0.1)
            return None
        return 1.0
    else:
        if(global_vars.debug):print(f"[BRV] Monitoring stopped")
        return None
    
@persistent
def load_pre_handler(idk):
    bpy.app.timers.register(closeRenderWindow, first_interval=0.1)
    
def check_and_send_resolution():

    current_res_x = bpy.context.scene.render.resolution_x
    current_res_y = bpy.context.scene.render.resolution_y
    current_res_p = bpy.context.scene.render.resolution_percentage
    if (global_vars.resX != current_res_x) or (global_vars.resY != current_res_y) or (global_vars.resX != current_res_x):
        global_vars.resX = current_res_x
        global_vars.resY = current_res_y
        global_vars.resP = current_res_p
        if(global_vars.debug):print(f"[BRV] Res Changed to : {global_vars.resX}x{global_vars.resY}@{global_vars.resP}")
        resolution_data = {
            "resolution_x": global_vars.resX,
            "resolution_y": global_vars.resY,
            "resolution_percentage": global_vars.resP
        } 
        SocketServer.notify_clients_data(resolution_data)

    global_vars.res_updating = False

def register():
    bpy.types.TOPBAR_MT_render.prepend(draw_ipr_button)
    bpy.app.handlers.load_post.append(load_pre_handler)
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
    SocketServer.start("127.0.0.1", global_vars.PORT)

def unregister():
    global_vars.monitor = False
    SocketServer.stop()
    
    bpy.types.TOPBAR_MT_render.remove(draw_ipr_button)
    bpy.app.handlers.load_post.remove(load_pre_handler)
    bpy.utils.unregister_class(OP_CreateCleanRenderedView)

    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except ValueError:
            pass
    addon_keymaps.clear()

    try:
        Popen.kill(global_vars.extUiProc)
        if(global_vars.debug):print("[BRV] Killing external Ui. Exiting.")
    except:
        if(global_vars.debug):print("[BRV] No active external Ui Found. Exiting.")
    global_vars.extUiProc = None

def draw_ipr_button(self, context):
    layout = self.layout
    layout.operator("brw.create_clean_rendered_view", text="Render View (IPR)", icon='IMAGE_DATA')

if __name__ == "__main__":
    register()