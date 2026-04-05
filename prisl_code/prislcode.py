#!/usr/bin/env python3
"""
Local Agentic CLI - Prisl Code
---------------------------------------
A highly robust, autonomous terminal assistant using local LLMs.
Features:
- @filename context injection with TAB auto-complete
- Slash commands (/help, /compact, /clear, /history, /save, /exit) with auto-complete
- Up/Down arrow message history
- Streaming Markdown rendering
- Interactive Tool Execution (Accept/Reject changes)
- Unified Diffs for file modifications
- Shell command execution
- Directory traversal & File grepping
- Conversation memory & system directives
- Self-Healing Tool Error Recovery
- Developed by rx76d
"""

import os
import sys
import subprocess
import platform
import venv
import json
import difflib
import fnmatch
import re
import datetime
import urllib.request
import shutil
import shlex
import time
import zipfile
import tarfile
import tempfile
from typing import Dict, Any, Tuple, List, Optional


def _is_windows() -> bool:
    return os.name == "nt" or sys.platform.startswith("win")


def _windows_powershell_exe() -> Optional[str]:
    if not _is_windows():
        return None
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    bundled = os.path.join(
        system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
    )
    if os.path.isfile(bundled):
        return bundled
    for name in ("powershell.exe", "pwsh.exe"):
        found = shutil.which(name)
        if found and os.path.isfile(found):
            return found
    return None


def _schedule_remove_dir_deferred_windows_cmd(path: str) -> None:
    inner = path.replace("%", "%%")
    fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="prisl_rm_")
    os.close(fd)
    lines = (
        "@echo off\r\n"
        "ping 127.0.0.1 -n 3 >nul\r\n"
        f'if exist "{inner}" rd /s /q "{inner}"\r\n'
        'del "%~f0"\r\n'
    )
    with open(bat_path, "wb") as f:
        f.write(lines.encode("utf-8"))
    cmd_exe = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"
    )
    if not os.path.isfile(cmd_exe):
        cmd_exe = shutil.which("cmd.exe") or "cmd.exe"
    creationflags = getattr(subprocess, "DETACHED_PROCESS", 8) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0x08000000
    )
    subprocess.Popen(
        [cmd_exe, "/c", bat_path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


# ==========================================
# VIRTUAL ENVIRONMENT BOOTSTRAP
# ==========================================

# ==========================================
# UNINSTALL LOGIC
# ==========================================

def _schedule_remove_dir_deferred(path: str) -> None:
    path = os.path.normpath(os.path.abspath(path))
    if _is_windows():
        ps_path = path.replace("'", "''")
        ps_cmd = (
            f"Start-Sleep -Seconds 2; "
            f"if (Test-Path -LiteralPath '{ps_path}') {{ "
            f"Remove-Item -LiteralPath '{ps_path}' -Recurse -Force -ErrorAction SilentlyContinue }}"
        )
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 8) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0x08000000
        )
        ps_exe = _windows_powershell_exe()
        if ps_exe:
            subprocess.Popen(
                [
                    ps_exe,
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle", "Hidden",
                    "-Command",
                    ps_cmd,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
            )
        else:
            _schedule_remove_dir_deferred_windows_cmd(path)
    else:
        sh_bin = "/bin/sh" if os.path.isfile("/bin/sh") else (shutil.which("sh") or "sh")
        subprocess.Popen(
            [sh_bin, "-c", f"sleep 2; rm -rf {shlex.quote(path)}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )


def _remove_prisl_user_home(prisl_dir: str, console) -> None:
    if not os.path.exists(prisl_dir):
        return
    console.print(f"[dim]Removing environment: {prisl_dir}...[/dim]")
    try:
        shutil.rmtree(prisl_dir, ignore_errors=False)
    except OSError:
        shutil.rmtree(prisl_dir, ignore_errors=True)
    if os.path.exists(prisl_dir):
        _schedule_remove_dir_deferred(prisl_dir)
        console.print(
            "[yellow]The data folder is still in use. It will be deleted automatically a few seconds after you exit.[/yellow]"
        )
    else:
        console.print("[green]Removed environment.[/green]")


def uninstall_prisl_code():
    """Completely removes the Prisl Code environment, binaries, and cache."""
    from rich.prompt import Confirm
    from rich.panel import Panel
    from rich.console import Console
    
    console = Console()
    
    console.print(Panel.fit(
        "[bold red]UNINSTALL PRISL CODE[/bold red]\n"
        "This will permanently delete the virtual environment, LLM binaries, and cache.",
        border_style="red"
    ))
    
    if not Confirm.ask("[bold yellow]Are you absolutely sure you want to proceed?[/bold yellow]", default=False):
        console.print("[green]Uninstall cancelled.[/green]")
        return

    home_dir = os.path.expanduser("~")
    prisl_dir = os.path.join(home_dir, ".prisl_code")
    _remove_prisl_user_home(prisl_dir, console)

    llama_bin = os.path.join(os.getcwd(), "llama_bin")
    if os.path.exists(llama_bin):
        console.print(f"[dim]Removing binaries: {llama_bin}...[/dim]")
        try:
            shutil.rmtree(llama_bin, ignore_errors=True)
            console.print("[green]Removed local binaries.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to remove binaries: {e}[/red]")

    console.print("[dim]Cleaning up Prisl Code cache and build files...[/dim]")
    package_dir = os.path.dirname(os.path.abspath(__file__))
    count = 0
    for root, dirs, files in os.walk(package_dir):
        for d in list(dirs):
            if d == "__pycache__" or d.endswith(".egg-info") or d == ".pytest_cache" or d == ".build" or d == "dist":
                target = os.path.join(root, d)
                try:
                    shutil.rmtree(target, ignore_errors=True)
                    count += 1
                except: pass
    console.print(f"[green]Removed {count} internal cache/build directories.[/green]")

    console.print("[dim]Attempting to uninstall package via pip...[/dim]")
    try:
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "prisl-code", "-y"], capture_output=True)
        console.print("[green]Uninstalled package from current environment.[/green]")
    except Exception as e:
        console.print(f"[yellow]Could not uninstall via pip: {e}[/yellow]")

    console.print("\n[bold green]Prisl Code has been uninstalled successfully.[/bold green]")
    sys.exit(0)

def bootstrap_venv():
    """Ensures the script runs inside an isolated virtual environment with all dependencies."""
    home_dir = os.path.expanduser("~")
    venv_dir = os.path.join(home_dir, ".prisl_code", "env")
    
    if _is_windows():
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")
        if not os.path.exists(venv_python):
            v3 = os.path.join(venv_dir, "bin", "python3")
            if os.path.exists(v3):
                venv_python = v3

    if os.path.normcase(sys.executable) == os.path.normcase(venv_python):
        return

    print("\n[PRISL-CODE] Checking isolated environment...")
    
    if not os.path.exists(venv_python):
        print("\n[PRISL-CODE] First run detected. Creating an isolated environment...")
        
        if os.path.exists(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)
            
        os.makedirs(os.path.dirname(venv_dir), exist_ok=True)
            
        try:
            venv.create(venv_dir, with_pip=True)
            
            print("[PRISL-CODE] Installing required dependencies...")
            deps = ["openai", "rich", "prompt_toolkit", "psutil"]
            
            subprocess.run(
                [venv_python, "-m", "pip", "install", "--upgrade", "pip", "-q"],
                capture_output=True,
            )

            result = subprocess.run(
                [venv_python, "-m", "pip", "install"] + deps,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )

            if result.returncode != 0:
                print("\n[PRISL-CODE] ERROR: Failed to install one or more dependencies.")
                if result.stderr:
                    print(f"[PRISL-CODE] pip output:\n{result.stderr[-2000:]}")
                if not shutil.which("git"):
                    print("[PRISL-CODE] HINT: 'git' was NOT found on your system.")
                    print("[PRISL-CODE]       Some pip packages require git to install.")
                    print("[PRISL-CODE]       Install it from https://git-scm.com and re-run prisl-code.")
                shutil.rmtree(venv_dir, ignore_errors=True)
                sys.exit(1)
                
            print("[PRISL-CODE] Dependencies installed successfully.")
            
        except BaseException as e:
            print(f"\n[PRISL-CODE] Process interrupted or failed ({type(e).__name__}). Cleaning up corrupted environment...")
            shutil.rmtree(venv_dir, ignore_errors=True)
            sys.exit(1)

    print("[PRISL-CODE] Relaunching inside virtual environment...\n")

    script_path = os.path.abspath(__file__)
    try:
        sys.exit(subprocess.call([venv_python, script_path] + sys.argv[1:]))
    except KeyboardInterrupt:
        print("\n[PRISL-CODE] Relaunch interrupted by user.")
        sys.exit(1)


def _exit_startup_interrupt():
    print("\n[PRISL-CODE] Startup interrupted by user.")
    sys.exit(1)


try:
    from openai import OpenAI
except ImportError:
    print("ERROR: The 'openai' library is missing.")
    print("Please run: pip install openai")
    sys.exit(1)
except KeyboardInterrupt:
    _exit_startup_interrupt()

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.prompt import Confirm, Prompt
    from rich.live import Live
    from rich.text import Text
    from rich.table import Table
except ImportError:
    print("ERROR: The 'rich' library is missing.")
    print("Please run: pip install rich")
    sys.exit(1)
except KeyboardInterrupt:
    _exit_startup_interrupt()

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion, PathCompleter
    from prompt_toolkit.document import Document
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.styles import Style
except ImportError:
    print("ERROR: The 'prompt_toolkit' library is missing.")
    print("Please run: pip install prompt_toolkit")
    sys.exit(1)
except KeyboardInterrupt:
    _exit_startup_interrupt()

try:
    import psutil
except ImportError:
    print("ERROR: The 'psutil' library is missing.")
    print("Please run: pip install psutil")
    sys.exit(1)
except KeyboardInterrupt:
    _exit_startup_interrupt()

# ==========================================
# CONFIGURATION & INITIALIZATION
# ==========================================

console = Console()

# ==========================================
# SERVER MANAGEMENT LOGIC
# ==========================================

class LocalServerManager:
    """Manages the lifecycle of llama-server and RAM validation."""

    _GITHUB_UA = "Prisl-Code/1.0 (+https://github.com/rx76d/prisl-code)"

    @staticmethod
    def is_server_running(port: int) -> bool:
        """Checks if an OpenAI-compatible /v1/models endpoint is active."""
        try:
            url = f"http://127.0.0.1:{port}/v1/models"
            req = urllib.request.Request(
                url, headers={"User-Agent": LocalServerManager._GITHUB_UA}
            )
            with urllib.request.urlopen(req, timeout=1.0) as response:
                return response.status == 200
        except Exception:
            return False

    @staticmethod
    def _try_install_tkinter() -> bool:
        """Attempts to auto-install python3-tk via the system package manager (Linux/macOS only)."""
        sys_os = platform.system()
        console.print("[yellow]Attempting to auto-install tkinter...[/yellow]")

        if sys_os == "Linux":
            candidates = [
                (["apt-get", "install", "-y", "python3-tk"], "apt-get"),
                (["dnf",     "install", "-y", "python3-tkinter"], "dnf"),
                (["yum",     "install", "-y", "python3-tkinter"], "yum"),
                (["pacman",  "-S", "--noconfirm", "python-tk"],   "pacman"),
                (["zypper",  "install", "-y", "python3-tk"],       "zypper"),
            ]
            for cmd, mgr in candidates:
                if not shutil.which(mgr):
                    continue
                try:
                    result = subprocess.run(
                        ["sudo"] + cmd, timeout=60,
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                    )
                    if result.returncode == 0:
                        console.print("[green]✅ tkinter installed successfully via " + mgr + "![/green]")
                        return True
                    console.print(f"[red]{mgr} failed: {result.stderr.strip()[:400]}[/red]")
                except Exception as e:
                    console.print(f"[red]{mgr} error: {e}[/red]")
            console.print(
                "[red]Could not auto-install tkinter. Please run one of:\n"
                "  Ubuntu/Debian : sudo apt-get install python3-tk\n"
                "  Fedora/RHEL   : sudo dnf install python3-tkinter\n"
                "  Arch          : sudo pacman -S python-tk[/red]"
            )
            return False

        elif sys_os == "Darwin":
            if shutil.which("brew"):
                py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
                try:
                    result = subprocess.run(
                        ["brew", "install", f"python-tk@{py_ver}"],
                        timeout=180, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    )
                    if result.returncode == 0:
                        console.print("[green]✅ tkinter installed via Homebrew![/green]")
                        return True
                    console.print(f"[red]brew failed: {result.stderr.strip()[:400]}[/red]")
                except Exception as e:
                    console.print(f"[red]brew error: {e}[/red]")
            console.print(
                "[red]Could not auto-install tkinter. Install Homebrew (https://brew.sh) then run:\n"
                "  brew install python-tk[/red]"
            )
            return False

        return False

    @staticmethod
    def select_gguf_model() -> str:
        """Opens a native file picker when possible; otherwise prompts for a path (e.g. headless Linux)."""
        sys_os = platform.system()
        headless_linux = (
            sys_os == "Linux"
            and not os.environ.get("DISPLAY")
            and not os.environ.get("WAYLAND_DISPLAY")
        )

        if not headless_linux:
            file_path = None
            for attempt in range(2):
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                except ImportError:
                    if attempt == 0 and LocalServerManager._try_install_tkinter():
                        continue
                    console.print("[yellow]tkinter unavailable; falling back to manual path entry.[/yellow]")
                    break

                try:
                    root = tk.Tk()
                    root.withdraw()
                    try:
                        root.attributes("-topmost", True)
                        root.lift()
                        root.focus_force()
                    except (tk.TclError, AttributeError):
                        pass
                    file_path = filedialog.askopenfilename(
                        title="Select a GGUF Model to Run",
                        filetypes=[("GGUF Models", "*.gguf"), ("All files", "*.*")],
                    )
                    root.destroy()
                except tk.TclError as e:
                    console.print(f"[yellow]Could not open file dialog ({e}); enter path manually.[/yellow]")
                break

            if file_path:
                return file_path

        path = Prompt.ask("Path to your .gguf model file").strip()
        return path.strip('"').strip("'")

    @staticmethod
    def check_ram_for_model(gguf_path: str) -> bool:
        """Checks if there is enough free RAM to run the model."""
        try:
            file_size_bytes = os.path.getsize(gguf_path)
            required_ram_bytes = file_size_bytes * 1.2
            available_ram_bytes = psutil.virtual_memory().available
            
            file_size_gb = file_size_bytes / (1024**3)
            req_ram_gb = required_ram_bytes / (1024**3)
            avail_ram_gb = available_ram_bytes / (1024**3)
            
            if required_ram_bytes > available_ram_bytes:
                console.print(f"\n[bold red]❌ INSUFFICIENT RAM DETECTED[/bold red]")
                console.print(f"[red]Model file size: {file_size_gb:.2f} GB[/red]")
                console.print(f"[red]Estimated RAM required (with context): {req_ram_gb:.2f} GB[/red]")
                console.print(f"[bold red]Your available free RAM: {avail_ram_gb:.2f} GB[/bold red]")
                console.print("[yellow]Please close some applications or select a smaller model quantization.[/yellow]")
                return False
                
            console.print(f"[green]✅ RAM check passed! (Model: {file_size_gb:.2f} GB, Free RAM: {avail_ram_gb:.2f} GB)[/green]")
            return True
        except Exception as e:
            console.print(f"[yellow]Could not verify RAM: {e}[/yellow]")
            return True

    @staticmethod
    def _http_get(url: str, timeout: float = 120) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": LocalServerManager._GITHUB_UA})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()

    @staticmethod
    def _release_asset_name_hints(sys_os: str, arch: str) -> List[str]:
        """Ordered substrings matched against release asset filenames (llama.cpp ggml-org builds)."""
        arch_l = arch.lower()
        is_arm = arch_l in ("arm64", "aarch64")
        is_x86_64 = arch_l in ("x86_64", "amd64", "x64")
        if sys_os == "windows":
            if is_arm:
                return ["-bin-win-cpu-arm64.zip"]
            return ["-bin-win-cpu-x64.zip", "-bin-win-avx2-x64.zip", "-bin-win-sse2-x64.zip"]
        if sys_os == "darwin":
            if is_arm:
                return ["-bin-macos-arm64.tar.gz"]
            if is_x86_64:
                return ["-bin-macos-x64.tar.gz"]
            return ["-bin-macos-arm64.tar.gz", "-bin-macos-x64.tar.gz"]
        if sys_os == "linux":
            if is_x86_64:
                return ["-bin-ubuntu-x64.tar.gz"]
            if is_arm:
                return ["-bin-ubuntu-aarch64.tar.gz", "-bin-linux-aarch64.tar.gz", "-bin-ubuntu-arm64.tar.gz"]
            return ["-bin-ubuntu-x64.tar.gz"]
        return []

    @staticmethod
    def _pick_llama_binary_asset(
        assets: List[dict], sys_os: str, arch: str
    ) -> Optional[Tuple[str, str]]:
        """Returns (download_url, filename) for the best matching prebuilt bundle, or None."""
        arch_l = arch.lower()
        is_arm = arch_l in ("arm64", "aarch64")
        is_x86_64 = arch_l in ("x86_64", "amd64", "x64")

        for hint in LocalServerManager._release_asset_name_hints(sys_os, arch):
            for asset in assets:
                name = asset.get("name") or ""
                url = asset.get("browser_download_url")
                if not url or not name.startswith("llama-"):
                    continue
                if "cudart-" in name.lower():
                    continue
                if hint not in name:
                    continue
                if not (name.endswith(".zip") or name.endswith(".tar.gz")):
                    continue
                nl = name.lower()
                if (
                    sys_os == "linux"
                    and is_x86_64
                    and "-bin-ubuntu-x64.tar.gz" in name
                ):
                    if any(x in nl for x in ("vulkan", "rocm", "openvino", "s390x")):
                        continue
                return (url, name)

        if sys_os == "linux" and is_arm:
            for asset in assets:
                name = asset.get("name") or ""
                url = asset.get("browser_download_url")
                if not url or not name.startswith("llama-"):
                    continue
                nl = name.lower()
                if "cudart" in nl or "xcframework" in nl:
                    continue
                if "bin-" in nl and "aarch64" in nl and nl.endswith(".tar.gz"):
                    return (url, name)

        return None

    @staticmethod
    def _extract_archive_bundle(archive_path: str, dest_dir: str) -> None:
        if archive_path.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(dest_dir)
        elif archive_path.endswith(".tar.gz") or archive_path.endswith(".tgz"):
            with tarfile.open(archive_path, "r:gz") as tf:
                if sys.version_info >= (3, 12):
                    tf.extractall(dest_dir, filter="data")
                else:
                    tf.extractall(dest_dir)
        else:
            raise ValueError(f"Unsupported archive format: {archive_path}")

    @staticmethod
    def download_llama_server() -> str:
        """Downloads a pre-built llama-server from the official llama.cpp GitHub release."""
        sys_os = platform.system().lower()
        arch = platform.machine().lower()
        exe_name = "llama-server.exe" if _is_windows() else "llama-server"

        if sys_os not in ("windows", "darwin", "linux"):
            console.print(f"[red]Unsupported OS for auto-download: {sys_os}[/red]")
            return ""

        release_api = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
        with console.status("[cyan]Fetching latest llama.cpp release from GitHub...[/cyan]"):
            try:
                data = json.loads(LocalServerManager._http_get(release_api).decode("utf-8"))
            except Exception as e:
                console.print(f"[red]Could not read llama.cpp release info: {e}[/red]")
                return ""

        assets = data.get("assets") or []
        picked = LocalServerManager._pick_llama_binary_asset(assets, sys_os, arch)
        if not picked:
            console.print(
                f"[red]No matching pre-built llama-server for {sys_os} ({arch}). "
                "Install `llama-server` on your PATH or build from source.[/red]"
            )
            return ""

        download_url, archive_name = picked
        console.print(f"[dim]Selected asset: {archive_name}[/dim]")

        bin_dir = os.path.join(os.getcwd(), "llama_bin")
        os.makedirs(bin_dir, exist_ok=True)
        dl_ext = ".zip" if archive_name.endswith(".zip") else ".tar.gz"
        archive_path = os.path.join(bin_dir, "llama_download" + dl_ext)

        try:
            console.print("[cyan]Downloading llama-server binaries...[/cyan]")
            dl_req = urllib.request.Request(
                download_url, headers={"User-Agent": LocalServerManager._GITHUB_UA}
            )
            with urllib.request.urlopen(dl_req, timeout=300) as resp:
                with open(archive_path, "wb") as out:
                    shutil.copyfileobj(resp, out)

            console.print("[cyan]Extracting...[/cyan]")
            LocalServerManager._extract_archive_bundle(archive_path, bin_dir)
            os.remove(archive_path)

            server_path = ""
            for root, _, files in os.walk(bin_dir):
                if exe_name in files:
                    server_path = os.path.join(root, exe_name)
                    break

            if not server_path:
                console.print("[red]Extraction finished but llama-server was not found.[/red]")
                return ""

            if not _is_windows():
                os.chmod(server_path, 0o755)

            console.print("[green]✅ Successfully installed llama-server![/green]")
            return server_path

        except Exception as e:
            console.print(f"[red]Error downloading or extracting llama-server: {e}[/red]")
            try:
                if os.path.exists(archive_path):
                    os.remove(archive_path)
            except OSError:
                pass
            return ""

    @staticmethod
    def ensure_server() -> int:
        """Ensures a server is running, returning the active port."""
        if LocalServerManager.is_server_running(8080):
            return 8080
        if LocalServerManager.is_server_running(11434):
            return 11434
            
        console.print("[yellow]No local LLM server detected running on port 8080 or 11434.[/yellow]")
        
        server_path = shutil.which("llama-server")
        
        if not server_path:
            exe_name = "llama-server.exe" if _is_windows() else "llama-server"
            local_bin = os.path.join(os.getcwd(), "llama_bin")
            if os.path.exists(local_bin):
                for root, _, files in os.walk(local_bin):
                    if exe_name in files:
                        server_path = os.path.join(root, exe_name)
                        break

        if not server_path:
            ans = Confirm.ask("Would you like to auto-download 'llama-server' (llama.cpp) to run local models?", default=True)
            if ans:
                server_path = LocalServerManager.download_llama_server()
            if not server_path:
                console.print("[bold red]❌ Could not find or install llama-server. Please install it manually.[/bold red]")
                sys.exit(1)

        console.print("[cyan]Please select a GGUF model file to run...[/cyan]")
        gguf_path = LocalServerManager.select_gguf_model()
        
        if not gguf_path:
            console.print("[bold red]❌ No model selected. Exiting.[/bold red]")
            sys.exit(1)
            
        console.print(f"[dim]Selected model: {gguf_path}[/dim]")

        if not LocalServerManager.check_ram_for_model(gguf_path):
            sys.exit(1)

        try:
            console.print(f"[cyan]Spinning up llama-server on port 8080...[/cyan]")
            cmd = [server_path, "-m", gguf_path, "-c", "8192", "--port", "8080"]
            
            if _is_windows():
                subprocess.Popen(
                    cmd,
                    creationflags=getattr(
                        subprocess, "CREATE_NEW_CONSOLE", 0x00000010
                    ),
                )
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            with console.status("[cyan]Waiting for model to load into RAM (this may take a moment)...[/cyan]"):
                for _ in range(60):
                    if LocalServerManager.is_server_running(8080):
                        console.print("[green]✅ llama-server is up and running![/green]")
                        return 8080
                    time.sleep(1)
                    
            console.print("[red]Timeout waiting for llama-server to start. It may still be loading, or it crashed.[/red]")
            sys.exit(1)
            
        except Exception as e:
            console.print(f"[red]Failed to start llama-server: {e}[/red]")
            sys.exit(1)


# ==========================================
# AUTO-COMPLETION LOGIC
# ==========================================

class PrislCompleter(Completer):
    """Handles Tab auto-completion for slash commands and @file paths."""
    def __init__(self):
        self.path_completer = PathCompleter(expanduser=True)
        self.commands = ['/help', '/compact', '/clear', '/history', '/save', '/uninstall', '/exit']

    def get_completions(self, document: Document, complete_event):
        word = document.get_word_before_cursor(WORD=True)
        
        if word.startswith('/'):
            for cmd in self.commands:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))
                    
        elif word.startswith('@'):
            path_part = word[1:]
            path_doc = Document(path_part, cursor_position=len(path_part))
            for completion in self.path_completer.get_completions(path_doc, complete_event):
                yield Completion(
                    completion.text, 
                    start_position=completion.start_position, 
                    display=completion.display
                )

# ==========================================
# TOOL DEFINITIONS & SCHEMAS
# ==========================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in a specific path. Returns file names and sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (e.g., '.' for current)"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file to inspect its code or text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file."}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely overwrite an existing one with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to write the file."},
                    "content": {"type": "string", "description": "The full code/text to write. Ensure all strings/quotes are properly closed."}
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Modify an existing file by replacing a specific block of text with new text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file."},
                    "search_text": {"type": "string", "description": "The exact existing text to find and replace."},
                    "replace_text": {"type": "string", "description": "The new text to insert in its place."}
                },
                "required": ["filepath", "search_text", "replace_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a bash/cmd shell command on the user's system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a text string across multiple files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory to search in."},
                    "query": {"type": "string", "description": "Text to search for."},
                    "file_pattern": {"type": "string", "description": "Glob pattern (e.g., '*.py')"}
                },
                "required": ["directory", "query"]
            }
        }
    }
]

# ==========================================
# TOOL EXECUTION LOGIC
# ==========================================

class ToolExecutor:
    """Handles the actual execution of tools and generates diffs for approval."""
    
    @staticmethod
    def _generate_diff(old_text: str, new_text: str, filename: str) -> str:
        """Generates a clean unified diff for file changes."""
        old_lines = [line + '\n' for line in old_text.splitlines()] if old_text else []
        new_lines = [line + '\n' for line in new_text.splitlines()] if new_text else []
        
        diff = list(difflib.unified_diff(
            old_lines, new_lines, 
            fromfile=f"a/{filename}", tofile=f"b/{filename}",
            n=3
        ))
        return "".join(diff)

    @staticmethod
    def list_files(args: Dict[str, Any]) -> Tuple[str, bool]:
        path = args.get("path", ".")
        try:
            if not os.path.exists(path):
                return f"Error: Path '{path}' does not exist.", False
            
            files_info = []
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                is_dir = os.path.isdir(full_path)
                size = os.path.getsize(full_path) if not is_dir else 0
                type_str = "DIR " if is_dir else "FILE"
                files_info.append(f"[{type_str}] {item} ({size} bytes)")
            
            return "Directory contents:\n" + "\n".join(files_info), False
        except Exception as e:
            return f"Error listing files: {str(e)}", False

    @staticmethod
    def read_file(args: Dict[str, Any]) -> Tuple[str, bool]:
        filepath = args.get("filepath", "")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > 15000:
                return content[:15000] + "\n\n...[FILE TRUNCATED DUE TO LENGTH]...", False
            return content, False
        except Exception as e:
            return f"Error reading file: {str(e)}", False

    @staticmethod
    def search_files(args: Dict[str, Any]) -> Tuple[str, bool]:
        directory = args.get("directory", ".")
        query = args.get("query", "")
        pattern = args.get("file_pattern", "*")
        
        results = []
        try:
            for root, _, files in os.walk(directory):
                for name in files:
                    if fnmatch.fnmatch(name, pattern):
                        filepath = os.path.join(root, name)
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                lines = f.readlines()
                                for i, line in enumerate(lines):
                                    if query in line:
                                        results.append(f"{filepath}:{i+1}: {line.strip()}")
                        except UnicodeDecodeError:
                            continue
            
            if not results:
                return f"No matches found for '{query}'.", False
            return "Search Results:\n" + "\n".join(results[:100]), False
        except Exception as e:
            return f"Error searching files: {str(e)}", False

    @staticmethod
    def prepare_write_file(args: Dict[str, Any]) -> Dict[str, Any]:
        filepath = args.get("filepath", "")
        content = args.get("content", "")
        
        old_content = ""
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    old_content = f.read()
            except Exception: pass
            
        diff = ToolExecutor._generate_diff(old_content, content, filepath)
        if not diff: diff = "(No changes or new file creation)"
        
        return {"action": "write", "filepath": filepath, "content": content, "diff": diff}

    @staticmethod
    def prepare_edit_file(args: Dict[str, Any]) -> Dict[str, Any]:
        filepath = args.get("filepath", "")
        search_text = args.get("search_text", "").replace('\r\n', '\n')
        replace_text = args.get("replace_text", "")
        
        try:
            if not os.path.exists(filepath):
                return {"error": f"File {filepath} does not exist."}
                
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().replace('\r\n', '\n')
                
            if search_text not in content:
                return {"error": f"Could not find the exact text block in {filepath} to replace. The whitespace or indentation was wrong. You MUST use the `read_file` tool first to see the exact text before trying to use `edit_file`."}
                
            new_content = content.replace(search_text, replace_text, 1)
            diff = ToolExecutor._generate_diff(content, new_content, filepath)
            
            return {"action": "write", "filepath": filepath, "content": new_content, "diff": diff}
        except Exception as e:
            return {"error": f"Preparation failed: {str(e)}"}

    @staticmethod
    def execute_write(action_data: Dict[str, Any]) -> str:
        try:
            filepath = action_data["filepath"]
            content = action_data.get("content", "")
            
            abs_path = os.path.abspath(filepath)
            dir_path = os.path.dirname(abs_path)
            
            if dir_path and not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                except Exception as e:
                    return f"Error creating directory '{dir_path}': {str(e)}"
            
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            if not os.path.exists(abs_path):
                return f"Error: File was not created at {abs_path} (file does not exist after write attempt)"
            
            file_size = os.path.getsize(abs_path)
            return f"Success: File written to {abs_path} ({file_size} bytes)"
        except PermissionError as e:
            return f"Error: Permission denied writing to {action_data['filepath']}: {str(e)}"
        except IOError as e:
            return f"Error: I/O error writing to {action_data['filepath']}: {str(e)}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    @staticmethod
    def prepare_run_command(args: Dict[str, Any]) -> Dict[str, Any]:
        command = args.get("command", "")
        return {"action": "command", "command": command}

    @staticmethod
    def execute_command(action_data: Dict[str, Any]) -> str:
        cmd = action_data["command"]
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                text=True,
                capture_output=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nEXIT CODE: {result.returncode}"
            return output
        except subprocess.TimeoutExpired:
            return f"Error: Command '{cmd}' timed out after 15 seconds."
        except FileNotFoundError:
            return f"Error: Command '{cmd}' not found. Check if the executable exists."
        except Exception as e:
            return f"Error executing command '{cmd}': {str(e)}"


# ==========================================
# THE AGENT CORE
# ==========================================

class PrislCodeAgent:
    def __init__(self, client: Any, model_id: str):
        self.client = client
        self.model_id = model_id
        
        custom_style = Style.from_dict({
            'completion-menu.completion': 'bg:default fg:white',
            'completion-menu.completion.current': 'bg:ansicyan fg:black',
            'scrollbar.background': 'bg:default',
            'scrollbar.button': 'bg:ansicyan',
        })
        
        self.prompt_session = PromptSession(completer=PrislCompleter(), style=custom_style)
        
        self.system_prompt = """You are Prisl Code, a highly capable, autonomous software engineer CLI tool.
You have access to the user's filesystem and shell via tools.
RULES:
1. CRITICAL: YOU MUST USE TOOLS TO WRITE CODE. Never output raw markdown code blocks (e.g., ```python) in your messages. If asked to write code, call the `write_file` or `edit_file` function immediately.
2. To create a new file or completely rewrite an existing one, use `write_file`. NEVER generate duplicate or repeating lines of code.
3. ALWAYS read a file before you attempt to edit it. You need to know exact contents to use `edit_file`.
4. When writing code, provide clean, production-ready, fully implemented solutions.
5. If the user asks you to run a script, test code, or install dependencies, use `run_command`.
6. Be concise in your conversational replies; let your actions (tool calls) do the talking.
7. The user may provide file context directly in their messages. This context will appear in <file_context> XML tags.
Your are developed by rx76d."""

        self.history = [{"role": "system", "content": self.system_prompt}]

    def _render_diff_panel(self, diff_text: str, title: str):
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
        panel = Panel(syntax, title=f"[bold yellow]Pending Changes: {title}[/bold yellow]", border_style="yellow")
        console.print(panel)

    def _render_command_panel(self, command: str):
        text = Text(f"$ {command}", style="bold cyan")
        panel = Panel(text, title="[bold red]Pending Shell Command[/bold red]", border_style="red")
        console.print(panel)

    def print_help(self):
        table = Table(title="Prisl Code Commands", show_header=True, header_style="bold magenta")
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="white")
        table.add_row("@<filepath>", "Inject a file's content directly into context.")
        table.add_row("/compact", "Clear conversation history to save tokens (keeps system prompt).")
        table.add_row("/history", "Print a summary of the current conversation history.")
        table.add_row("/save", "Export the current chat history to a Markdown file.")
        table.add_row("/clear", "Clear the terminal screen.")
        table.add_row("/help", "Show this help menu.")
        table.add_row("/uninstall", "Completely remove Prisl Code and its environments.")
        table.add_row("/exit", "Exit the application.")
        console.print(table)
        console.print("\n[dim]Note: You can also run 'prisl-code --uninstall' from your terminal.[/dim]")

    def print_history(self):
        if len(self.history) <= 1:
            console.print("[yellow]History is currently empty.[/yellow]")
            return
            
        console.print(Panel("[bold cyan]Conversation History[/bold cyan]", expand=False))
        for msg in self.history:
            role = msg.get("role")
            if role == "system":
                continue
                
            color = "green" if role == "user" else "purple" if role == "assistant" else "blue"
            name = role.capitalize()
            
            content = msg.get("content") or ""
            if role == "assistant" and msg.get("tool_calls"):
                tool_names = [tc["function"]["name"] for tc in msg["tool_calls"]]
                content = f"[dim italic]Used tools: {', '.join(tool_names)}[/dim italic]\n" + content
                
            display_content = content[:300] + "..." if len(content) > 300 else content
            console.print(f"[{color}][bold]{name}:[/bold][/{color}] {display_content}")
            console.print("-" * 40, style="dim")

    def save_history(self):
        if len(self.history) <= 1:
            console.print("[yellow]Nothing to save. History is empty.[/yellow]")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_history_{timestamp}.md"
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# Prisl Code - Chat History\n*Saved on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n---\n\n")
                
                for msg in self.history:
                    role = msg.get("role")
                    if role == "system":
                        continue
                    
                    content = msg.get("content") or ""
                    
                    if role == "user":
                        f.write(f"### You\n{content}\n\n")
                    elif role == "assistant":
                        f.write(f"### Agent\n")
                        if msg.get("tool_calls"):
                            f.write(f"*(Agent requested tools)*\n")
                        f.write(f"{content}\n\n")
                    elif role == "tool":
                        f.write(f"**[Tool Result]**\n```text\n{content}\n```\n\n")
                        
            console.print(f"[bold green]Success: Chat history exported to {filename}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Failed to save history: {e}[/bold red]")

    def process_mentions(self, user_input: str) -> str:
        pattern = r'(?<!\S)@([a-zA-Z0-9_\-\./\\\[\]]+)'
        mentioned_files = []
        
        def replace_mention(match):
            filepath = os.path.normpath(match.group(1))
            if os.path.exists(filepath) and os.path.isfile(filepath):
                mentioned_files.append(filepath)
                return f"`{filepath}`"
            return match.group(0)
            
        processed_input = re.sub(pattern, replace_mention, user_input)
        
        context_blocks = []
        for filepath in mentioned_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                context_blocks.append(f"\n<file_context path=\"{filepath}\">\n{content}\n</file_context>")
                console.print(f"[dim]Injected context: {filepath}[/dim]")
            except Exception as e:
                console.print(f"[red]Failed to read {filepath}: {e}[/red]")
        
        if context_blocks:
            return processed_input + "\n\n" + "\n\n".join(context_blocks)
        return processed_input

    def process_tool_call(self, tool_call: Dict[str, Any]) -> str:
        name = tool_call["function"]["name"]
        args_str = tool_call["function"]["arguments"]
        
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            return "Error: Failed to parse tool arguments as valid JSON."

        console.print(f"\n[bold blue]Agent requested tool:[/bold blue] {name}")
        
        if name in ["list_files", "read_file", "search_files"]:
            with console.status(f"[cyan]Executing {name}...[/cyan]"):
                if name == "list_files": result, _ = ToolExecutor.list_files(args)
                elif name == "read_file": result, _ = ToolExecutor.read_file(args)
                elif name == "search_files": result, _ = ToolExecutor.search_files(args)
            console.print(f"[dim]↳ Tool completed. ({len(result)} chars)[/dim]\n")
            return result

        elif name in ["write_file", "edit_file", "run_command"]:
            
            action_data = {}
            if name == "write_file":
                action_data = ToolExecutor.prepare_write_file(args)
            elif name == "edit_file":
                action_data = ToolExecutor.prepare_edit_file(args)
            elif name == "run_command":
                action_data = ToolExecutor.prepare_run_command(args)

            if "error" in action_data:
                console.print(f"[bold red]Tool Preparation Failed:[/bold red] {action_data['error']}\n")
                return action_data["error"]

            prompt_text = ""
            if action_data.get("action") == "write":
                filepath = action_data["filepath"]
                self._render_diff_panel(action_data["diff"], filepath)
                prompt_text = f"Allow agent to modify [bold green]{filepath}[/bold green]?"
                
            elif action_data.get("action") == "command":
                self._render_command_panel(action_data["command"])
                prompt_text = "Allow agent to execute this shell command?"
            else:
                return f"Error: Unknown action type '{action_data.get('action')}'"

            is_approved = Confirm.ask(prompt_text, default=True)
            
            if not is_approved:
                console.print("[yellow]Action rejected by user.[/yellow]\n")
                return "The user rejected this action. Do not attempt this specific action again without asking for clarification."

            console.print("[bold green]Executing approved action...[/bold green]")
            if action_data["action"] == "write":
                with console.status("[bold green]Writing file...[/bold green]"):
                    result = ToolExecutor.execute_write(action_data)
            elif action_data["action"] == "command":
                console.print(f"[dim]Running command: {action_data['command']}[/dim]")
                result = ToolExecutor.execute_command(action_data)
            else:
                result = f"Error: Cannot execute unknown action '{action_data['action']}'"
            
            if "Error" in result or "error" in result:
                console.print(f"[bold red]Execution Result:[/bold red]\n{result}\n")
            else:
                console.print(f"[dim]↳ Result: {result}\n")
            return result

        else:
            return f"Error: Unknown tool '{name}'"

    def chat_loop(self):
        while True:
            try:
                user_input = self.prompt_session.prompt(HTML('\n<b><ansigreen>❯ You:</ansigreen></b> ')).strip()
                
                if not user_input:
                    continue

                if user_input.startswith('/'):
                    cmd = user_input.lower().split()[0]
                    if cmd == '/exit':
                        console.print("[magenta]Goodbye![/magenta]")
                        break
                    elif cmd == '/clear':
                        os.system('cls' if os.name == 'nt' else 'clear')
                        continue
                    elif cmd == '/compact':
                        self.history = [{"role": "system", "content": self.system_prompt}]
                        console.print("[green]Conversation history compacted! Context window is fresh.[/green]")
                        continue
                    elif cmd == '/history':
                        self.print_history()
                        continue
                    elif cmd == '/save':
                        self.save_history()
                        continue
                    elif cmd == '/uninstall':
                        uninstall_prisl_code()
                        continue
                    elif cmd == '/help':
                        self.print_help()
                        continue
                    else:
                        console.print(f"[bold red]Unknown command:[/bold red] {cmd}. Type /help for a list of commands.")
                        continue

                final_user_content = self.process_mentions(user_input)
                self.history.append({"role": "user", "content": final_user_content})

                while True:
                    console.print("\n[bold purple]◈ Agent:[/bold purple]")
                    
                    response_content = ""
                    tool_calls = []
                    is_tool_streaming = False
                    tool_stream_counter = 0
                    
                    try:
                        stream = self.client.chat.completions.create(
                            model=self.model_id,
                            messages=self.history,
                            max_tokens=16384,
                            temperature=0.2,
                            stream=True,
                            tools=TOOLS
                        )

                        live = Live(Markdown(""), refresh_per_second=15, console=console)
                        live.start()
                        try:
                            for chunk in stream:
                                delta = chunk.choices[0].delta
                                
                                if delta.content is not None:
                                    response_content += delta.content
                                    live.update(Markdown(response_content))
                                    
                                if delta.tool_calls:
                                    if not is_tool_streaming:
                                        live.stop()
                                        console.print("\n[dim cyan]Building code/tool payload [/dim cyan]", end="")
                                        is_tool_streaming = True
                                    
                                    tool_stream_counter += 1
                                    if tool_stream_counter % 8 == 0:
                                        console.print("[dim cyan].[/dim cyan]", end="")

                                    for tc_chunk in delta.tool_calls:
                                        while len(tool_calls) <= tc_chunk.index:
                                            tool_calls.append({
                                                "id": "", 
                                                "type": "function", 
                                                "function": {"name": "", "arguments": ""}
                                            })
                                        
                                        tc = tool_calls[tc_chunk.index]
                                        if tc_chunk.id: tc["id"] += tc_chunk.id
                                        if tc_chunk.function.name: tc["function"]["name"] += tc_chunk.function.name
                                        if tc_chunk.function.arguments: tc["function"]["arguments"] += tc_chunk.function.arguments
                        finally:
                            if live.is_started:
                                live.stop()

                        console.print()
                        
                    except KeyboardInterrupt:
                        console.print("\n[yellow]Generation interrupted by user.[/yellow]")
                        break
                    except Exception as e:
                        error_str = str(e)
                        if "500" in error_str or "JSON" in error_str or "parse" in error_str:
                            console.print(f"\n[yellow]Tool syntax error detected. Instructing AI to self-correct...[/yellow]")
                            self.history.append({
                                "role": "user", 
                                "content": "Your last tool call failed with a JSON syntax error. Ensure your arguments are valid JSON and all strings/quotes are properly closed. Try again."
                            })
                            continue
                        else:
                            raise e

                    if not tool_calls:
                        self.history.append({"role": "assistant", "content": response_content})
                        break 
                    
                    assistant_msg = {
                        "role": "assistant",
                        "content": response_content or None,
                        "tool_calls": tool_calls
                    }
                    self.history.append(assistant_msg)

                    for tc in tool_calls:
                        result_text = self.process_tool_call(tc)
                        
                        self.history.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_text
                        })

            except KeyboardInterrupt:
                continue
            except EOFError:
                console.print("\n[magenta]Goodbye![/magenta]")
                break
            except Exception as e:
                console.print(f"\n[bold red]An error occurred in the agent loop:[/bold red] {e}")


# ==========================================
# APP ENTRY POINT
# ==========================================

def main():
    if "--uninstall" in sys.argv:
        uninstall_prisl_code()

    bootstrap_venv()

    try:
        os.system('cls' if os.name == 'nt' else 'clear')
        console.print(Panel.fit(
            "[bold cyan]Prisl Code[/bold cyan]\n"
            "Autonomous CLI powered by local LLMs\n"
            "Type [green]/help[/green] to see available commands or use [green]@filename[/green] to add context.\n",
            border_style="cyan"
        ))

        active_port = LocalServerManager.ensure_server()

        client = OpenAI(
            base_url=f"http://127.0.0.1:{active_port}/v1",
            api_key="sk-local-no-key-required",
            timeout=60.0
        )

        with console.status(f"[dim]Connecting to local server (http://127.0.0.1:{active_port})...[/dim]"):
            available_models = client.models.list()
            model_id = available_models.data[0].id if available_models.data else "local-model"
                
        console.print(f"Connected! Using model: [bold green]{model_id}[/bold green]\n")

        agent = PrislCodeAgent(client=client, model_id=model_id)
        agent.chat_loop()
    except KeyboardInterrupt:
        console.print("\n[bold red]Interrupted by user (Ctrl+C). Exiting...[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")

if __name__ == "__main__":
    main()