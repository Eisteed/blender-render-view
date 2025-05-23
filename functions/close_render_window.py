def run(bpy, renderWindow, status, monitor, extUiProc):
    if renderWindow:
        try:
            with bpy.context.temp_override(window=renderWindow):
                bpy.ops.wm.window_close()
        except Exception as e:
            print(f"[BRV] Blender Rendered viewport close failed: {str(e)}")
    renderWindow = None        
    status = "init"
    monitor = False
    extUiProc = None
    return renderWindow, status, monitor, extUiProc