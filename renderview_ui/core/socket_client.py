import socket, threading, json, time
from blender import data

class SocketClient:
    HOST = '127.0.0.1'
    client_socket = None
    listener_thread = None
    status = {'status': 'initial'}
    status_lock = threading.Lock()


    @classmethod
    def start(cls, host=HOST, port=42082):
        # Retry connection in case the server isn't ready yet
        max_retries = 20
        for attempt in range(max_retries):
            try:
                cls.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                cls.client_socket.connect((host, port))
                break
            except (ConnectionRefusedError, OSError):
                if cls.client_socket:
                    cls.client_socket.close()
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                else:
                    print(f"[BRV-UI] Could not connect to Blender socket server after {max_retries} attempts")
                    return
        cls.listener_thread = threading.Thread(target=cls.listen_for_updates)
        cls.listener_thread.daemon = True
        cls.listener_thread.start()
    
    @classmethod
    def listen_for_updates(cls):
        while True:
            try:
                datas = cls.client_socket.recv(4096)
                if not datas:
                    if(data.Blender.debug):print(f"[BRV-UI] Socket connection closed")
                    return
                else:
                    # Split on newlines to handle multiple messages in one recv
                    for line in datas.decode('utf-8').splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            message = json.loads(line)
                            cls.handle_message(message)
                        except json.JSONDecodeError as e:
                            if(data.Blender.debug):
                                print(f"[BRV-UI] JSON decode error: {e}")
                        except Exception as e:
                            if(data.Blender.debug):
                                print(f"[BRV-UI] Error handling message: {e}")
                                print(f"[BRV-UI] Message was: {line}")
            except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                if(data.Blender.debug):
                    print(f"[BRV-UI] Socket connection error: {e}")
                break
            except Exception as e:
                if(data.Blender.debug):
                    print(f"[BRV-UI] Unexpected error in listen_for_updates: {e}")
                break

    @classmethod
    def handle_message(cls, message):
        if 'status' in message:
            cls.update_local_status(message['status'])
            if(data.Blender.debug):print(f"[BRV-UI] Status received: {message['status']}")
        if 'resolution_x' in message:
            data.Blender.resolution_x = message['resolution_x']
            data.Blender.resolution_y = message['resolution_y']
            data.Blender.resolution_percentage = message['resolution_percentage']
            if(data.Blender.debug):print(f"[BRV-UI] Resolution received: {data.Blender.resolution_x}x{data.Blender.resolution_y}@{data.Blender.resolution_percentage}%")

            from blender.monitor import BlenderWindowMonitor
            BlenderWindowMonitor.resize_window_to_resolution()

            # Only fit to window on first run
            if message.get('first_run') == "true":
                while True:
                    if data.main_window is not None:
                        data.main_window.fitToWindow()
                        break
                    time.sleep(0.1)

        if 'render_passes' in message:
            data.Blender.renderPass = message['render_passes']
            if data.Blender.debug:
                print(f"[BRV-UI] Render passes received: {data.Blender.renderPass}")
            # Update dropdown on Qt main thread
            if data.main_window is not None:
                from PySide6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(data.main_window, "updateRenderPassDropdown",
                                        Qt.QueuedConnection)

        if 'snapshot_folder' in message:
            folder_path = message['snapshot_folder']
            save_enabled = message.get('save_snapshots_enabled', True)
            cls.load_snapshots_from_folder(folder_path, save_enabled)

    @classmethod
    def load_snapshots_from_folder(cls, folder_path, save_enabled=True):
        """Load all snapshots from the project's snapshot folder."""
        if data.Blender.debug:
            print(f"[BRV-UI] Received snapshot folder: {folder_path}, save_enabled: {save_enabled}")

        # Wait for main window and load on main thread using Qt signal
        def _load():
            import os
            import glob

            while data.main_window is None:
                time.sleep(0.1)

            # Set the save path and setting
            data.main_window.snapshot_save_path = folder_path
            data.main_window.save_snapshots_enabled = save_enabled

            # Update UI checkbox and path input
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(data.main_window, "updateSaveCheckbox",
                                    Qt.QueuedConnection)
            QMetaObject.invokeMethod(data.main_window, "updateSnapshotPathInput",
                                    Qt.QueuedConnection)

            # Check if folder exists
            if not os.path.exists(folder_path):
                if data.Blender.debug:
                    print(f"[BRV-UI] Snapshot folder does not exist: {folder_path}")
                return

            # Scan for PNG files in the folder
            pattern = os.path.join(folder_path, "snapshot_*.png")
            snapshot_files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

            if data.Blender.debug:
                print(f"[BRV-UI] Found {len(snapshot_files)} snapshots in folder")

            # Load each snapshot - use QTimer to ensure we're on main thread
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            for file_path in snapshot_files:
                if data.Blender.debug:
                    print(f"[BRV-UI] Loading snapshot: {file_path}")
                # Schedule on Qt main thread
                QMetaObject.invokeMethod(data.main_window, "loadSnapshot",
                                        Qt.QueuedConnection,
                                        Q_ARG(str, file_path))

        # Run in a thread
        import threading
        load_thread = threading.Thread(target=_load)
        load_thread.daemon = True
        load_thread.start()


    @classmethod
    def update_local_status(cls, new_status):
            with cls.status_lock:
                cls.status = new_status

    @classmethod
    def update_status(cls, new_status):
            #if(data.Blender.debug): print("[BRV-UI] New Status:", {new_status})
            with cls.status_lock:
                cls.status = new_status
                cls.send_message({"status": cls.status})

    @classmethod
    def send_message(cls, data):
        try:
            message_data = (json.dumps(data) + '\n').encode('utf-8')
            cls.client_socket.sendall(message_data)
        except Exception as e:
            print(f"[BRV-UI] Failed to send message to blender: {e}")

    @classmethod
    def stop(cls):
        try:
            if cls.listener_thread and cls.listener_thread.is_alive():
                cls.listener_thread.join()
            if cls.client_socket:
                cls.client_socket.close()
        except Exception as e:
            print(f"[BRV-UI] Socket stop error: {e}")