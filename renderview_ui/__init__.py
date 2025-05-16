
import sys, os
sys.dont_write_bytecode = True

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.socket_client import SocketClient
SocketClient.start()

# Load pywin32 post install
from core.win32_loader import loadWin32
loadWin32()

try:
    from PySide6.QtWidgets import QApplication # type: ignore
    from PySide6.QtGui import QPalette, QColor, QIcon # type: ignore
    from PySide6.QtCore import Qt, QObject, Signal# type: ignore
except ImportError as e:
    print(f"[BRV-UI] Error loading wheels: Please reload addon or restart blender {e}")
    SocketClient.update_status('extui_exited')
    sys.exit(1)  # Stop program if PySide6 is missing

from core.paths import *
from core import signal
from blender.monitor import BlenderWindowMonitor
from ui.main_window import MainWindow
from blender import data

BlenderWindowMonitor.start()

# Qt App
app = QApplication(sys.argv + ['-platform', 'windows:darkmode=1'])
app.setStyle('Fusion')

icon_path = os.path.join(current_dir, "ui", "icons", "brv.ico")
app.setWindowIcon(QIcon(icon_path))

# Dark theme
dark_palette = QPalette()
dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
dark_palette.setColor(QPalette.WindowText, Qt.white)
dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
dark_palette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
dark_palette.setColor(QPalette.ToolTipText, Qt.white)
dark_palette.setColor(QPalette.Text, Qt.white)
dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
dark_palette.setColor(QPalette.ButtonText, Qt.white)
dark_palette.setColor(QPalette.BrightText, Qt.red)
dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
dark_palette.setColor(QPalette.HighlightedText, Qt.black)
app.setPalette(dark_palette)

def on_exit():
    print("[BRV-UI] External window exiting..")
    data.main_window.close()
    SocketClient.update_status('extui_exited')
    SocketClient.stop()

app.aboutToQuit.connect(on_exit)

data.main_window = MainWindow()
data.main_window.show()
signal.signal_emitter.close_mainwindow.connect(data.main_window.close)

sys.exit(app.exec())