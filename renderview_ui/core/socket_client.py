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
        cls.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.client_socket.connect((host, port))
        cls.listener_thread = threading.Thread(target=cls.listen_for_updates)
        cls.listener_thread.daemon = True
        cls.listener_thread.start()
    
    @classmethod
    def listen_for_updates(cls):
        while True:
            try:
                datas = cls.client_socket.recv(1024)
                if not datas:
                    return
                else:
                    message = json.loads(datas.decode('utf-8'))
                    cls.handle_message(message)
            except Exception as e:
                if(data.Blender.debug): 
                    print(f"[BRV-UI] Message Error: {e}")
                    print(message)
                break

    @classmethod
    def handle_message(cls, message):
        if 'status' in message:
            cls.update_local_status(message['status'])
            print(f"[BRV-UI] Status received: {message['status']}")
        if 'resolution_x' in message:
            data.Blender.resolution_x = message['resolution_x']
            data.Blender.resolution_y = message['resolution_y']
            data.Blender.resolution_percentage = message['resolution_percentage']
            from blender.monitor import BlenderWindowMonitor
            BlenderWindowMonitor.resize_window_to_resolution()
            if message['first_run'] == "true":
                while True:
                    if data.main_window is not None:
                        data.main_window.fitToWindow()
                        break
                    time.sleep(0.1)


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
            message_data = json.dumps(data).encode('utf-8')
            cls.client_socket.sendall(message_data)
        except Exception as e:
            if(data.Blender.debug): print("[BRV-UI] Failed to send message to blender: ", {e})
            pass

    @classmethod
    def stop(cls):
        try:
            if cls.listener_thread and cls.listener_thread.is_alive():
                cls.listener_thread.join()
            if cls.client_socket:
                cls.client_socket.close()
        except Exception as e:
            print(f"[BRV-UI] Socket stop error: {e}")