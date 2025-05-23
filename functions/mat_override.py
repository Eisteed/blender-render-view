def clay(bpy):
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
    principled.inputs['Base Color'].default_value = (0.340352, 0.328571, 0.242888, 1.0)  # Clay color
    principled.inputs['Roughness'].default_value = 0.9


    # Connect nodes
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])

    # Apply material override to current view layer (CORRECT)
    bpy.context.view_layer.material_override = clay_mat

    print("[BRV] Clay material override ON")

def wireframe(bpy):

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
    wireframe_node.use_pixel_size = True  # Use pixel-based sizing instead of Blender units
    wireframe_node.inputs['Size'].default_value = 1.0  # Wireframe thickness in pixels

    # Configure ColorRamp to invert: white background, black wireframes
    color_ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)  # White (faces)
    color_ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)  # Black (wireframes)

    # Set emission strength (unlit)
    emission_node.inputs['Strength'].default_value = 1.0

    # Connect nodes: Wireframe -> ColorRamp (invert) -> Emission -> Output
    links.new(wireframe_node.outputs['Fac'], color_ramp.inputs['Fac'])
    links.new(color_ramp.outputs['Color'], emission_node.inputs['Color'])
    links.new(emission_node.outputs['Emission'], output.inputs['Surface'])

    # Apply material override to current view layer
    bpy.context.view_layer.material_override = wireframe_mat

    print("Inverted wireframe override applied (black wireframes on white)")

def disable(bpy):
    bpy.context.view_layer.material_override = None

    # Optional: Remove override materials
    if "ClayOverride" in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials["ClayOverride"])
    if "WireframeOverride" in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials["WireframeOverride"])

    print("[BRV] Material override OFF")