import os, sys

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

abs = resource_path(os.path.dirname(os.path.abspath(__file__)))
script_dir = os.path.dirname(abs)