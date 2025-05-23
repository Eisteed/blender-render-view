def run(bpy, renderWindow, renderPass):
    for window in bpy.context.window_manager.windows:
        if window == renderWindow:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'RENDERED'
                            space.shading.cycles.render_pass = renderPass