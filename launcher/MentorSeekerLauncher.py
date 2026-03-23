import json
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "MentorSeeker Launcher"
BACKEND_PORT = 8000
FRONTEND_PORT = 3000


def _is_project_root(path: Path) -> bool:
    return (path / "backend").is_dir() and (path / "frontend").is_dir()


def _detect_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        start_dir = Path(sys.executable).resolve().parent
    else:
        start_dir = Path(__file__).resolve().parent

    candidates = [start_dir, *start_dir.parents]
    for candidate in candidates:
        if _is_project_root(candidate):
            return candidate

    # Fallback to original behavior if project markers are missing.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT_DIR = _detect_root_dir()

BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
RUNTIME_DIR = ROOT_DIR / ".runtime"
PID_FILE = RUNTIME_DIR / "launcher_state.json"
BACKEND_LOG = RUNTIME_DIR / "backend.log"
FRONTEND_LOG = RUNTIME_DIR / "frontend.log"


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_port(port: int, timeout_sec: int) -> bool:
    start = time.time()
    while time.time() - start < timeout_sec:
        if _port_is_open(port):
            return True
        time.sleep(0.3)
    return False


def _ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    if not PID_FILE.exists():
        return {}
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    _ensure_runtime_dir()
    PID_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_state() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink(missing_ok=True)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid_tree(pid: int) -> None:
    if pid <= 0:
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _spawn_hidden(cmd: list[str], cwd: Path, env: dict[str, str], log_file: Path) -> int:
    _ensure_runtime_dir()
    log_handle = open(log_file, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=_creation_flags(),
    )
    log_handle.close()
    return int(proc.pid)


def _backend_python_path() -> Path:
    return BACKEND_DIR / "venv" / "Scripts" / "python.exe"


def _check_prerequisites() -> tuple[bool, str]:
    backend_python = _backend_python_path()
    if not backend_python.exists():
        return (
            False,
            f"backend/venv not found under: {ROOT_DIR}. Please run 01-Setup-MentorSeeker.bat first.",
        )

    if not (FRONTEND_DIR / "node_modules").exists():
        return (
            False,
            f"frontend/node_modules not found under: {ROOT_DIR}. Please run 01-Setup-MentorSeeker.bat first.",
        )

    if shutil.which("npm") is None:
        return False, "npm not found. Please install Node.js 20+ first."

    return True, ""


def start_services() -> tuple[bool, str]:
    ok, msg = _check_prerequisites()
    if not ok:
        return False, msg

    state = _load_state()
    backend_pid = int(state.get("backend_pid", 0) or 0)
    frontend_pid = int(state.get("frontend_pid", 0) or 0)
    if _pid_exists(backend_pid) or _pid_exists(frontend_pid) or _port_is_open(BACKEND_PORT) or _port_is_open(FRONTEND_PORT):
        return False, 'Services may already be running. Please click "Stop Services" first.'

    backend_python = _backend_python_path()
    backend_cmd = [
        str(backend_python),
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(BACKEND_PORT),
    ]
    backend_env = os.environ.copy()

    frontend_cmd = ["npm", "run", "dev", "--", "--port", str(FRONTEND_PORT)]
    frontend_env = os.environ.copy()
    frontend_env["NEXT_PUBLIC_API_BASE"] = f"http://localhost:{BACKEND_PORT}"

    try:
        bpid = _spawn_hidden(backend_cmd, ROOT_DIR, backend_env, BACKEND_LOG)
        fpid = _spawn_hidden(frontend_cmd, FRONTEND_DIR, frontend_env, FRONTEND_LOG)
        _save_state({"backend_pid": bpid, "frontend_pid": fpid, "started_at": int(time.time())})
    except Exception as exc:
        return False, f"Failed to start services: {exc}"

    backend_ok = _wait_for_port(BACKEND_PORT, 25)
    frontend_ok = _wait_for_port(FRONTEND_PORT, 40)

    if not backend_ok or not frontend_ok:
        stop_services()
        return False, "Services did not become ready in time. Check logs under .runtime/."

    return True, "Started successfully: http://localhost:3000"


def stop_services() -> tuple[bool, str]:
    state = _load_state()
    backend_pid = int(state.get("backend_pid", 0) or 0)
    frontend_pid = int(state.get("frontend_pid", 0) or 0)

    if backend_pid <= 0 and frontend_pid <= 0 and (not _port_is_open(BACKEND_PORT)) and (not _port_is_open(FRONTEND_PORT)):
        _clear_state()
        return True, "No running services detected."

    if backend_pid > 0:
        _kill_pid_tree(backend_pid)
    if frontend_pid > 0:
        _kill_pid_tree(frontend_pid)

    # Fallback by ports for stale state.
    for port in (BACKEND_PORT, FRONTEND_PORT):
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-NetTCPConnection -LocalPort {port} -State Listen | Select-Object -ExpandProperty OwningProcess -Unique",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                creationflags=_creation_flags(),
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    _kill_pid_tree(int(line))
        except Exception:
            pass

    _clear_state()
    return True, "Services stopped."


class LauncherUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("560x300")
        self.root.resizable(False, False)

        main = ttk.Frame(self.root, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="MentorSeeker", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(main, text="Single-window launcher (no extra terminal windows)", font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 12))

        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(main, textvariable=self.status_var, wraplength=520)
        status.pack(anchor="w", pady=(0, 12))

        row = ttk.Frame(main)
        row.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(row, text="Start Services", command=self.on_start).pack(side=tk.LEFT)
        ttk.Button(row, text="Stop Services", command=self.on_stop).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(row, text="Open App", command=self.on_open).pack(side=tk.LEFT, padx=(8, 0))

        row2 = ttk.Frame(main)
        row2.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(row2, text="Open Logs", command=self.on_open_logs).pack(side=tk.LEFT)
        ttk.Button(row2, text="Exit", command=self.root.destroy).pack(side=tk.RIGHT)

        hint = (
            "First run: 01-Setup-MentorSeeker.bat\n"
            "If startup fails, open logs and check backend.log / frontend.log."
        )
        ttk.Label(main, text=hint, foreground="#555", wraplength=520).pack(anchor="w", pady=(8, 0))

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.root.update_idletasks()

    def on_start(self) -> None:
        self.set_status("Starting services, please wait...")
        ok, msg = start_services()
        self.set_status(msg)
        if ok:
            webbrowser.open(f"http://localhost:{FRONTEND_PORT}")
        else:
            messagebox.showerror(APP_NAME, msg)

    def on_stop(self) -> None:
        self.set_status("Stopping services...")
        ok, msg = stop_services()
        self.set_status(msg)
        if not ok:
            messagebox.showerror(APP_NAME, msg)

    def on_open(self) -> None:
        webbrowser.open(f"http://localhost:{FRONTEND_PORT}")

    def on_open_logs(self) -> None:
        _ensure_runtime_dir()
        os.startfile(str(RUNTIME_DIR))

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    LauncherUI().run()
