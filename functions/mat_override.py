def clay(bpy):
    """Apply clay material override. Uses timer to ensure main thread execution."""
    def _apply_clay():
        try:
            # Create clay material
            clay_mat = bpy.data.materials.new(name="ClayOverride")
            clay_mat.use_nodes = True
            nodes = clay_mat.node_tree.nodes
            links = clay_mat.node_tree.links

            # Clear default nodes
            nodes.clear()

            # Create clay shader
            principled = nodes.new('ShaderNodeBsdfPrincipled')
            output = nodes.new('ShaderNodeOutputMaterial')

            # Set clay properties
            principled.inputs['Base Color'].default_value = (0.340352, 0.328571, 0.242888, 1.0)
            principled.inputs['Roughness'].default_value = 0.9

            # Connect nodes
            links.new(principled.outputs['BSDF'], output.inputs['Surface'])

            # Apply material override to current view layer
            bpy.context.view_layer.material_override = clay_mat
        except Exception as e:
            print(f"[BRV] Error applying clay override: {e}")
        return None

    bpy.app.timers.register(_apply_clay, first_interval=0.0)

def wireframe(bpy):
    """Apply wireframe material override. Uses timer to ensure main thread execution."""
    def _apply_wireframe():
        try:
            # Create unlit wireframe material (inverted - black wireframes on white)
            wireframe_mat = bpy.data.materials.new(name="WireframeOverride")
            wireframe_mat.use_nodes = True
            nodes = wireframe_mat.node_tree.nodes
            links = wireframe_mat.node_tree.links

            # Clear default nodes
            nodes.clear()

            # Create wireframe shader nodes
            wireframe_node = nodes.new('ShaderNodeWireframe')
            color_ramp = nodes.new('ShaderNodeValToRGB')
            emission_node = nodes.new('ShaderNodeEmission')
            output = nodes.new('ShaderNodeOutputMaterial')

            # Set wireframe properties
            wireframe_node.use_pixel_size = True
            wireframe_node.inputs['Size'].default_value = 1.0

            # Configure ColorRamp to invert: white background, black wireframes
            color_ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
            color_ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

            # Set emission strength (unlit)
            emission_node.inputs['Strength'].default_value = 1.0

            # Connect nodes: Wireframe -> ColorRamp (invert) -> Emission -> Output
            links.new(wireframe_node.outputs['Fac'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], emission_node.inputs['Color'])
            links.new(emission_node.outputs['Emission'], output.inputs['Surface'])

            # Apply material override to current view layer
            bpy.context.view_layer.material_override = wireframe_mat
        except Exception as e:
            print(f"[BRV] Error applying wireframe override: {e}")
        return None

    bpy.app.timers.register(_apply_wireframe, first_interval=0.0)

def disable(bpy):
    """Disable material override. Uses timer to ensure main thread execution."""
    def _disable_override():
        try:
            bpy.context.view_layer.material_override = None

            # Remove override materials
            if "ClayOverride" in bpy.data.materials:
                bpy.data.materials.remove(bpy.data.materials["ClayOverride"])
            if "WireframeOverride" in bpy.data.materials:
                bpy.data.materials.remove(bpy.data.materials["WireframeOverride"])
        except Exception as e:
            print(f"[BRV] Error disabling override: {e}")
        return None

    bpy.app.timers.register(_disable_override, first_interval=0.0)