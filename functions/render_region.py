def run(bpy, xmin, ymin, xmax, ymax, rr_enabled):
    bpy.context.scene.render.border_min_x = float(xmin)
    bpy.context.scene.render.border_min_y = float(ymin)
    bpy.context.scene.render.border_max_x = float(xmax)
    bpy.context.scene.render.border_max_y = float(ymax)
    bpy.context.scene.render.use_border = rr_enabled