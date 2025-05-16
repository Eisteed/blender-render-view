class Blender:
    resolution_x = 10
    resolution_y = 10
    resolution_percentage = 100
    titleHeight = 0
    mainWindow = None
    windowBorderWidth = 0
    window = None
    windowHandle = None
    blenderHandle = None
    debug = True
    renderPass = ['COMBINED', 'EMISSION', 'BACKGROUND', 'AO', 'SHADOW_CATCHER', 'DIFFUSE_DIRECT', 'DIFFUSE_INDIRECT', 'DIFFUSE_COLOR', 'GLOSSY_DIRECT', 'GLOSSY_INDIRECT', 'GLOSSY_COLOR', 'TRANSMISSION_DIRECT', 'TRANSMISSION_INDIRECT', 'TRANSMISSION_COLOR', 'VOLUME_DIRECT', 'VOLUME_INDIRECT', 'POSITION', 'NORMAL', 'UV', 'MIST', 'DENOISING_ALBEDO', 'DENOISING_NORMAL', 'SAMPLE_COUNT']
    renderPassActive = 'COMBINED'
#ext ui
main_window = None