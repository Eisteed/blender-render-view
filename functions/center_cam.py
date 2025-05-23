def run(bpy, renderWindow):
        for window in bpy.context.window_manager.windows:
            if window == renderWindow:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        region = next((region for region in area.regions if region.type == 'WINDOW'), None)
                        if region:
                            with bpy.context.temp_override(window=window, area=area, region=region):
                                if bpy.ops.view3d.view_center_camera.poll():
                                    bpy.ops.view3d.view_center_camera()
                                if bpy.ops.view3d.zoom_camera_1_to_1.poll():
                                    bpy.ops.view3d.zoom_camera_1_to_1()