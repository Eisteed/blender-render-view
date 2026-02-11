def run(bpy, renderWindow, renderPass):
    """
    Set render pass on the render window viewport.
    Uses timer to ensure execution on main thread.
    """
    def _set_render_pass():
        try:
            for window in bpy.context.window_manager.windows:
                if window == renderWindow:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            for space in area.spaces:
                                if space.type == 'VIEW_3D':
                                    space.shading.render_pass = renderPass
        except Exception as e:
            print(f"[BRV] Error setting render pass: {e}")
        return None  # Don't repeat timer

    # Schedule on main thread using timer
    bpy.app.timers.register(_set_render_pass, first_interval=0.0)