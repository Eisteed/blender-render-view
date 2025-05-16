
import os, sys, ctypes, importlib
def find_site_packages_path():
    for path in sys.path:
        if path and "site-packages" in path.replace("\\", "/").lower():
            if os.path.isdir(path):
                return path
    return None

site_packages_dir = find_site_packages_path()
if site_packages_dir:
    sys.path.append(site_packages_dir)
    #print("✅ Found site-packages at:", site_packages_dir)
else:
    print("❌ Could not find site-packages in sys.path")
    sys.exit()

def loadWin32():
    import importlib
    # Dictionary to store loaded modules
    loaded_modules = {}
    
    if not site_packages_dir:
        print("Could not find site-packages directory in sys.path")
    
    # Define the pywin32_system32 directory
    pywin32_system32 = os.path.join(site_packages_dir, "pywin32_system32")
    
    # Add the pywin32_system32 directory to PATH for DLL loading
    if os.path.exists(pywin32_system32):
        os.environ["PATH"] = pywin32_system32 + os.pathsep + os.environ["PATH"]
        #print(f"Added to PATH: {pywin32_system32}")
    
    # Ensure all necessary directories are in sys.path
    win32_dirs = [
        os.path.join(site_packages_dir, "win32"),
        os.path.join(site_packages_dir, "win32", "lib"),
        os.path.join(site_packages_dir, "pythonwin"),
        pywin32_system32
    ]
    
    for path in win32_dirs:
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)
            #print(f"Added to sys.path: {path}")
    
    # Load pywintypes DLL first (important for dependencies)
    pywintypes_dll = os.path.join(pywin32_system32, "pywintypes311.dll")
    if os.path.exists(pywintypes_dll):
        try:
            ctypes.CDLL(pywintypes_dll)
            #print(f"Loaded DLL: {pywintypes_dll}")
        except Exception as e:
            print(f"Error loading {pywintypes_dll}: {e}")
    #print(f"Starting win32 modules import")
    # Try importing modules in a specific order
    modules_to_load = ["pywintypes", "win32con", "win32gui", "win32process", "win32ui"]
    
    for module_name in modules_to_load:
        try:
            module = importlib.import_module(module_name)
            loaded_modules[module_name] = module
            #print(f"✅ Successfully imported {module_name}")
        except ImportError as e:
            print(f"❌ Failed to import {module_name}: {e}")
            
            # Special handling for modules that might need extra attention
            if module_name == "win32ui":
                win32ui_pyd = os.path.join(site_packages_dir, "pywin32_system32", "win32ui.pyd")
                if os.path.exists(win32ui_pyd):
                    try:
                        import importlib.machinery
                        import importlib.util
                        
                        loader = importlib.machinery.ExtensionFileLoader("win32ui", win32ui_pyd)
                        spec = importlib.machinery.ModuleSpec(name="win32ui", loader=loader, origin=win32ui_pyd)
                        win32ui = importlib.util.module_from_spec(spec)
                        sys.modules["win32ui"] = win32ui
                        loader.exec_module(win32ui)
                        loaded_modules["win32ui"] = win32ui
                        print("✅ Successfully loaded win32ui via ExtensionFileLoader")
                    except Exception as e2:
                        print(f"Failed to load win32ui via ExtensionFileLoader: {e2}")