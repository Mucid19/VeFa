import subprocess
import sys
import os
import time
import webbrowser
import threading
import pystray
from pystray import MenuItem as item
from PIL import Image

# Start child processes globally so we can kill them later
backend_process = None
frontend_process = None

def get_base_dir():
    # Since this script will be moved to the backend folder, the root project dir is the parent folder
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def start_servers():
    global backend_process, frontend_process
    
    base_dir = get_base_dir()
    frontend_dir = os.path.join(base_dir, "frontend")
    
    # Flags to hide the CMD windows
    CREATE_NO_WINDOW = 0x08000000
    
    # Start Backend
    backend_cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--reload", "--port", "8000"]
    backend_process = subprocess.Popen(backend_cmd, cwd=base_dir, creationflags=CREATE_NO_WINDOW)
    
    # Start Frontend (npm run dev)
    # Using shell=True for npm command, but with creationflags to hide it
    frontend_cmd = "npm run dev"
    frontend_process = subprocess.Popen(frontend_cmd, cwd=frontend_dir, shell=True, creationflags=CREATE_NO_WINDOW)

def stop_servers():
    global backend_process, frontend_process
    
    if backend_process:
        backend_process.terminate()
    if frontend_process:
        # On Windows, terminating a shell process doesn't always kill children. 
        # But this is a good first step. taskkill is more robust.
        subprocess.run(f"taskkill /F /T /PID {frontend_process.pid}", shell=True, creationflags=0x08000000)
        
    # Just to be safe, kill all node and uvicorn processes started by us.
    # We will just kill the ones we spawned via pid tree.

def open_browser():
    webbrowser.open("http://localhost:5173")

def on_open(icon, item):
    open_browser()

def on_exit(icon, item):
    icon.stop()
    stop_servers()
    os._exit(0)

import socket

def check_single_instance():
    # Use a dummy local port to ensure only one instance of the tray app runs
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 51733)) # 51733 is arbitrary VeFa lock port
        return s
    except socket.error:
        return None

def main():
    lock_socket = check_single_instance()
    if lock_socket is None:
        # App is already running! Just open the browser and exit this duplicate process.
        open_browser()
        return

    # 1. Start servers in the background
    start_servers()
    
    # 2. Wait 3 seconds for servers to initialize
    time.sleep(3)
    
    # 3. Open the UI automatically on first launch
    open_browser()
    
    # 4. Setup Tray Icon
    base_dir = get_base_dir()
    logo_path = os.path.join(base_dir, "frontend", "public", "vefa_logo.jpg")
    
    if os.path.exists(logo_path):
        image = Image.open(logo_path)
    else:
        image = Image.new('RGB', (64, 64), color = (73, 109, 137))
    
    # Setting default=True makes it trigger when the user left-clicks (or double-clicks) the tray icon!
    menu = pystray.Menu(
        item('Arayüzü Aç', on_open, default=True),
        item('Çıkış Yap', on_exit)
    )
    
    icon = pystray.Icon("VeFa", image, "VeFa Akademik Asistan", menu)
    icon.run()
    
    # Keep the socket open until the app closes
    lock_socket.close()

if __name__ == "__main__":
    main()
