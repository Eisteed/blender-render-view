import bpy # type: ignore
from bpy.types import Operator # type: ignore

def msgbox(context, message, icon='INFO', message_type='ERROR'):

    if message_type == 'ERROR':
        # Show as a popup dialog with a close button
        def draw_popup(self, context):
            self.layout.label(text=message, icon=icon)
            self.layout.operator("wm.confirm_message", text="OK").message = message

        bpy.context.window_manager.popup_menu(draw_popup, title="Error", icon=icon)
    elif message_type == 'INFO':
        # Show in the status bar
        bpy.ops.wm.message_post(
            message=message,
            icon=icon,
            title="Info"
        )
    elif message_type == 'DEBUG':
        # Show in the system console (for developers)
        bpy.utils.message_set(message, icon)