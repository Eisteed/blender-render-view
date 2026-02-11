import json
import os
import socket
import selectors
import threading
import bpy # type: ignore
from . import global_vars
from .functions import render_region, set_render_pass, mat_override

class SocketServer:
    HOST = '127.0.0.1'
    listener_thread = None
    server_socket = None
    stop_event = threading.Event()
    sel = selectors.DefaultSelector()
    clients = {}

    @classmethod
    def start(cls, host=HOST, port=global_vars.PORT):
        if cls.is_port_in_use(host, port):
           print(f"[BRV] Error port {port} already in use")
        else:
            cls.stop_event.clear()
            cls.listener_thread = threading.Thread(target=cls.listen_for_commands, args=(host, port))
            cls.listener_thread.daemon = True
            cls.listener_thread.start()

    @classmethod
    def is_port_in_use(cls, host, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as temp_socket:
            try:
                temp_socket.bind((host, port))
                return False
            except socket.error:
                return True

    @classmethod
    def listen_for_commands(cls, host, port):
        cls.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cls.server_socket.bind((host, port))
        cls.server_socket.listen()
        cls.server_socket.setblocking(False)
        cls.sel.register(cls.server_socket, selectors.EVENT_READ, cls.accept)

        if(global_vars.debug):print(f"[BRV] Socket Server Started. Listening on {host}:{port}...")
        while not cls.stop_event.is_set():
            events = cls.sel.select(timeout=1)
            for key, mask in events:
                callback = key.data
                callback(key.fileobj, mask)
        cls.server_socket.close()
        if(global_vars.debug):print(f"[BRV] Socket server stopped.")

    @classmethod
    def accept(cls, sock, mask):
        conn, addr = sock.accept()
        #if(global_vars.debug):print(f"[BRV] Connection from {addr}")
        conn.setblocking(False)
        cls.sel.register(conn, selectors.EVENT_READ, cls.handle_client)
        cls.clients[conn] = addr

    @classmethod
    def handle_client(cls, conn, mask):
        try:
            data = conn.recv(1024)
            if data:
                try:
                    received_json = json.loads(data.decode('utf-8'))
                    cls.handle_message(received_json, conn)
                    #if(global_vars.debug):print(f"[BRV] Received: {received_json}")
                except json.JSONDecodeError as e:
                    if(global_vars.debug):print(f"[BRV] JSONDecodeError: {e}")
                    if(global_vars.debug):print(f"[BRV] Raw data: {data}")
            else:
                cls.disconnect(conn)
        except ConnectionResetError:
            cls.disconnect(conn)
        except Exception as e:
            print(f"[BRV] Unexpected error: {e}")

    @classmethod
    def handle_message(cls, message, conn):
        if 'status' in message:
            cls.update_local_status(message['status'])
        if 'resolution' in message:
            cls.update_resolution(message['resolution'])
        if 'render_region' in message:
            if(message['render_region'] == "true"):
                global_vars.rr_enabled = True
                global_vars.xmin = message['xmin']
                global_vars.ymin = message['ymin']
                global_vars.xmax = message['xmax']
                global_vars.ymax = message['ymax']
            else:
                global_vars.rr_enabled = False
            render_region.run(bpy, global_vars.xmin, global_vars.ymin, global_vars.xmax, global_vars.ymax, global_vars.rr_enabled)
        if 'render_pass' in message:
            global_vars.renderPass = message['render_pass']
            set_render_pass.run(bpy, global_vars.renderWindow, global_vars.renderPass)
        if 'mat_override' in message:
            print("mat_override")
            if message['mat_override'] == 'clay':
                mat_override.clay(bpy)
            elif message['mat_override'] == 'wireframe':
                mat_override.wireframe(bpy)
            else:
                mat_override.disable(bpy)
        if 'snapshot_path' in message:
            if(global_vars.debug):print(f"[BRV] Received snapshot_path: {message['snapshot_path']}")
            cls.save_snapshot_path_to_blend(message['snapshot_path'])
        if 'save_snapshots_enabled' in message:
            if(global_vars.debug):print(f"[BRV] Received save_snapshots_enabled: {message['save_snapshots_enabled']}")
            cls.save_snapshot_setting_to_blend(message['save_snapshots_enabled'])

    @classmethod
    def get_snapshot_folder_path(cls):
        """Get snapshot folder path: brv-snapshots/{project_name}/ next to blend file."""
        blend_path = bpy.data.filepath
        if blend_path:
            # Check if custom path is saved in scene
            scene = bpy.context.scene
            if "brv_snapshot_path" in scene and scene["brv_snapshot_path"]:
                return scene["brv_snapshot_path"]

            # Default: brv-snapshots/{project_name}/ next to blend file
            project_name = os.path.splitext(os.path.basename(blend_path))[0]
            folder_path = os.path.join(os.path.dirname(blend_path), "brv-snapshots", project_name)
        else:
            # Unsaved file - use temp folder
            folder_path = os.path.join(os.path.expanduser("~"), "brv-snapshots-unsaved")
        return folder_path

    @classmethod
    def send_snapshot_folder_to_ui(cls):
        """Send snapshot folder path and settings to UI."""
        folder_path = cls.get_snapshot_folder_path()

        # Check if saving is enabled (default True)
        scene = bpy.context.scene
        save_enabled = scene.get("brv_save_snapshots", True)

        if global_vars.debug:
            print(f"[BRV] Sending snapshot folder to UI: {folder_path}, save_enabled: {save_enabled}")
        cls.notify_clients_data({
            "snapshot_folder": folder_path,
            "save_snapshots_enabled": save_enabled
        })

    @classmethod
    def save_snapshot_path_to_blend(cls, path):
        """Save custom snapshot path to Blender scene."""
        def _save():
            try:
                bpy.context.scene["brv_snapshot_path"] = path
                if global_vars.debug:
                    print(f"[BRV] Saved snapshot path to scene: {path}")
            except Exception as e:
                print(f"[BRV] Error saving snapshot path: {e}")
            return None
        bpy.app.timers.register(_save, first_interval=0.0)

    @classmethod
    def save_snapshot_setting_to_blend(cls, enabled):
        """Save snapshot save enabled setting to Blender scene."""
        def _save():
            try:
                bpy.context.scene["brv_save_snapshots"] = enabled
                if global_vars.debug:
                    print(f"[BRV] Saved snapshot setting: save_enabled={enabled}")
            except Exception as e:
                print(f"[BRV] Error saving snapshot setting: {e}")
            return None
        bpy.app.timers.register(_save, first_interval=0.0)
    @classmethod
    def update_local_status(cls, new_status):
        global_vars.status = new_status
        #if(global_vars.debug):print("[BRV] status Received: " + str(new_status))

    @classmethod
    def update_status(cls, new_status):
        global_vars.status = new_status
        cls.notify_clients_status()
        #if(global_vars.debug):print("[BRV] status Updated: " + str(status))

    @classmethod
    def notify_clients_status(cls):
        status_data = json.dumps({"status": global_vars.status}).encode('utf-8')
        for conn in list(cls.clients):
            try:
                conn.sendall(status_data)
            except Exception as e:
                if(global_vars.debug):print(f"[BRV] Error notifying client: {e}")
                cls.disconnect(conn)
    
    @classmethod
    def notify_clients_data(cls, dictionary):
        # Convert the data dictionary to a JSON string and encode it to bytes
        message = json.dumps(dictionary).encode('utf-8')
        # Send data to each client
        for conn in list(cls.clients):
            try:
                conn.sendall(message)
            except Exception as e:
                if(global_vars.debug):print(f"[BRV] Error notifying client: {e}")
                cls.disconnect(conn)
    @classmethod
    def disconnect(cls, conn):
        if(global_vars.debug):print(f"[BRV] Disconnecting {cls.clients[conn]}")
        cls.sel.unregister(conn)
        conn.close()
        del cls.clients[conn]

    @classmethod
    def stop(cls):
        try:
            cls.stop_event.set()

            if cls.server_socket:
                try:
                    cls.sel.unregister(cls.server_socket)
                except Exception:
                    pass
                cls.server_socket.close()
                cls.server_socket = None

            for conn in list(cls.clients):
                cls.disconnect(conn)

            # Close and clear selector
            cls.sel.close()
            cls.sel = selectors.DefaultSelector()

            if cls.listener_thread and cls.listener_thread.is_alive():
                cls.listener_thread.join(timeout=2)
                cls.listener_thread = None

        except Exception as e:
            if(global_vars.debug):print(f"[BRV] Can't stop socket server properly: {e}")  
