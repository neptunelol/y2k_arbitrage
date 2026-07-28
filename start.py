"""
Unified One-Click Launcher for Y2K Arbitrage Platform
Starts Python Backend (Port 8000) and Next.js Frontend (Port 3000) simultaneously.
"""

import os
import subprocess
import sys
import time
import signal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def cleanup(signum=None, frame=None):
    print("\n\n[LAUNCHER] Stopping Y2K Arbitrage Platform...")
    try:
        if sys.platform != "win32":
            subprocess.run("kill -9 $(lsof -t -i:8000) 2>/dev/null", shell=True)
            subprocess.run("kill -9 $(lsof -t -i:3000) 2>/dev/null", shell=True)
    except Exception:
        pass
    print("[LAUNCHER] Services stopped cleanly.")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("============================================================")
    print("🚀 Starting Y2K Digital Camera Arbitrage Platform")
    print("============================================================")

    # Free ports 8000 and 3000
    subprocess.run("kill -9 $(lsof -t -i:8000) 2>/dev/null", shell=True)
    subprocess.run("kill -9 $(lsof -t -i:3000) 2>/dev/null", shell=True)

    venv_python = os.path.join(SCRIPT_DIR, "venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    backend_main = os.path.join(SCRIPT_DIR, "backend", "main.py")
    frontend_dir = os.path.join(SCRIPT_DIR, "arbitrage_command_center")

    print("[1/2] Starting Python Backend & API (http://localhost:8000)...")
    backend_proc = subprocess.Popen([venv_python, backend_main], cwd=os.path.dirname(backend_main))

    time.sleep(2)

    print("[2/2] Starting Next.js Command Center (http://localhost:3000)...")
    frontend_proc = subprocess.Popen(["npm", "run", "dev"], cwd=frontend_dir)

    print("============================================================")
    print("✅ Both services running successfully!")
    print("   🖥️ Command Center: http://localhost:3000")
    print("   ⚡ Backend API:     http://localhost:8000")
    print("============================================================")
    print("Press Ctrl+C anytime to stop both services.\n")

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
