import bpy # type: ignore
from .. import global_Vars

def run(context):
    for window in bpy.context.window_manager.windows:
        if window == global_Vars.renderWindow:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'RENDERED'
                            space.shading.cycles.render_pass = global_Vars.renderPass
                            if(global_Vars.debug):print(f"[BRV] Set render_pass to: {global_Vars.renderPass}")
    return {'FINISHED'}