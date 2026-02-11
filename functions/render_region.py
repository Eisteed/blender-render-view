def run(bpy, xmin, ymin, xmax, ymax, rr_enabled):
    """
    Set render region for both final render and viewport render.
    Must be called from main thread (use bpy.app.timers if calling from socket thread).
    """
    def _set_render_region():
        try:
            # Set scene render border (for F12 renders)
            bpy.context.scene.render.border_min_x = float(xmin)
            bpy.context.scene.render.border_min_y = float(ymin)
            bpy.context.scene.render.border_max_x = float(xmax)
            bpy.context.scene.render.border_max_y = float(ymax)
            bpy.context.scene.render.use_border = rr_enabled

            # Set viewport render border on all 3D views
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                space.use_render_border = rr_enabled

        except Exception as e:
            print(f"[BRV] Error setting render region: {e}")
        return None  # Don't repeat timer

    # Schedule on main thread using timer
    bpy.app.timers.register(_set_render_region, first_interval=0.0)