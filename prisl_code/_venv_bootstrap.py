"""
Isolated venv bootstrap for Prisl Code (stdlib only).

Console scripts import this module first so dependencies can be installed into
~/.prisl_code/env before prislcode.py
"""

from __future__ import annotations

import os
import sys
import subprocess
import shutil
import shlex
import time
import tempfile
import venv
from typing import Any, Dict, List, Optional

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


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


def _remove_prisl_user_home(prisl_dir: str, log) -> None:
    if not os.path.exists(prisl_dir):
        return
    log(f"Removing environment: {prisl_dir}...")
    try:
        shutil.rmtree(prisl_dir, ignore_errors=False)
    except OSError:
        shutil.rmtree(prisl_dir, ignore_errors=True)
    if os.path.exists(prisl_dir):
        _schedule_remove_dir_deferred(prisl_dir)
        log(
            "The data folder is still in use. It will be deleted automatically a few seconds after you exit."
        )
    else:
        log("Removed environment.")


_VENV_PIP_PACKAGES = (
    "openai",
    "rich",
    "prompt-toolkit",
    "psutil",
)


def _subprocess_run_venv(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    if _is_windows():
        kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(cmd, **kwargs)


def _pip_run(
    venv_python: str, pip_args: List[str], *, timeout: int = 600, capture_output: bool = True
) -> subprocess.CompletedProcess:
    return _subprocess_run_venv(
        [venv_python, "-m", "pip"] + pip_args,
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _pip_install_with_retries(
    venv_python: str,
    pip_install_args: List[str],
    *,
    attempts: int = 4,
    label: str = "",
) -> subprocess.CompletedProcess:
    delay = 2.0
    last: Optional[subprocess.CompletedProcess] = None
    for attempt in range(attempts):
        try:
            last = _pip_run(venv_python, ["install"] + pip_install_args, timeout=600)
        except subprocess.TimeoutExpired as e:
            last = subprocess.CompletedProcess(e.cmd, 1, stdout="", stderr=str(e))
        if last.returncode == 0:
            return last
        if attempt + 1 < attempts:
            tag = f" ({label})" if label else ""
            print(
                f"[PRISL-CODE] pip attempt {attempt + 1}/{attempts} failed{tag}; "
                f"retrying in {delay:.0f}s..."
            )
            time.sleep(delay)
            delay = min(delay * 1.5, 45.0)
    assert last is not None
    return last


def _ensure_pip_in_venv(venv_python: str) -> bool:
    probe = _pip_run(venv_python, ["--version"], timeout=90)
    if probe.returncode == 0:
        return True
    print("[PRISL-CODE] pip missing in venv; running ensurepip...")
    _subprocess_run_venv(
        [venv_python, "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    probe2 = _pip_run(venv_python, ["--version"], timeout=90)
    return probe2.returncode == 0


def _verify_venv_imports(venv_python: str) -> bool:
    script = (
        "import importlib.util as u; "
        "mods = ('openai', 'rich', 'prompt_toolkit', 'psutil'); "
        "assert all(u.find_spec(m) for m in mods)"
    )
    r = _subprocess_run_venv(
        [venv_python, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    return r.returncode == 0


def _venv_python_path(venv_dir: str) -> str:
    if _is_windows():
        return os.path.join(venv_dir, "Scripts", "python.exe")
    py = os.path.join(venv_dir, "bin", "python")
    if os.path.exists(py):
        return py
    v3 = os.path.join(venv_dir, "bin", "python3")
    if os.path.exists(v3):
        return v3
    return py


def _same_python(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _ensure_venv_dependencies(venv_python: str) -> None:
    if not _ensure_pip_in_venv(venv_python):
        print("[PRISL-CODE] ERROR: Could not bootstrap pip inside the virtual environment.")
        sys.exit(1)

    print("[PRISL-CODE] Upgrading pip, setuptools, wheel...")
    up = _pip_install_with_retries(
        venv_python,
        ["--upgrade", "--no-input", "pip", "setuptools", "wheel"],
        attempts=4,
        label="pip tooling",
    )
    if up.returncode != 0:
        print("[PRISL-CODE] WARNING: pip tooling upgrade failed; continuing.")
        if up.stderr:
            print(up.stderr[-1500:])

    print("[PRISL-CODE] Installing required packages into the virtual environment...")
    inst = _pip_install_with_retries(
        venv_python,
        ["--upgrade", "--no-input"] + list(_VENV_PIP_PACKAGES),
        attempts=4,
        label="dependencies",
    )
    if inst.returncode != 0:
        print("[PRISL-CODE] Bulk install failed; installing packages one-by-one...")
        for pkg in _VENV_PIP_PACKAGES:
            one = _pip_install_with_retries(
                venv_python,
                ["--upgrade", "--no-input", pkg],
                attempts=4,
                label=pkg,
            )
            if one.returncode != 0:
                print(f"\n[PRISL-CODE] ERROR: Failed to install {pkg}.")
                if one.stderr:
                    print(f"[PRISL-CODE] pip stderr:\n{one.stderr[-2000:]}")
                if not shutil.which("git"):
                    print("[PRISL-CODE] HINT: 'git' was NOT found on your system.")
                    print("[PRISL-CODE]       Some pip packages need git. See https://git-scm.com")
                sys.exit(1)

    if not _verify_venv_imports(venv_python):
        print("[PRISL-CODE] ERROR: Packages installed but import verification failed.")
        if inst.stderr:
            print(inst.stderr[-1500:])
        sys.exit(1)

    print("[PRISL-CODE] Dependencies OK.")


def _local_venv_deps_ok() -> bool:
    import importlib.util

    for mod in ("openai", "rich", "prompt_toolkit", "psutil"):
        if importlib.util.find_spec(mod) is None:
            return False
    return True


def bootstrap_venv() -> None:
    """Ensures the script runs inside an isolated virtual environment with all dependencies."""
    home_dir = os.path.expanduser("~")
    venv_dir = os.path.join(home_dir, ".prisl_code", "env")
    venv_python = _venv_python_path(venv_dir)

    if _same_python(sys.executable, venv_python):
        if not _local_venv_deps_ok():
            print("[PRISL-CODE] Virtual environment is missing packages; repairing...")
            _ensure_venv_dependencies(sys.executable)
            if not _local_venv_deps_ok():
                print("[PRISL-CODE] ERROR: Could not repair the virtual environment.")
                sys.exit(1)
        return

    print("\n[PRISL-CODE] Checking isolated environment...")

    if not os.path.exists(venv_python):
        print("\n[PRISL-CODE] First run detected. Creating an isolated environment...")
        if os.path.exists(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)
        os.makedirs(os.path.dirname(venv_dir), exist_ok=True)
        try:
            venv.create(venv_dir, with_pip=True)
        except BaseException as e:
            print(
                f"\n[PRISL-CODE] Failed to create venv ({type(e).__name__}: {e}). "
                "Cleaning up..."
            )
            shutil.rmtree(venv_dir, ignore_errors=True)
            sys.exit(1)

        venv_python = _venv_python_path(venv_dir)
        if not os.path.exists(venv_python):
            print("[PRISL-CODE] ERROR: venv was created but Python executable is missing.")
            shutil.rmtree(venv_dir, ignore_errors=True)
            sys.exit(1)

        try:
            _ensure_venv_dependencies(venv_python)
        except KeyboardInterrupt:
            print("\n[PRISL-CODE] Install interrupted. Cleaning up...")
            shutil.rmtree(venv_dir, ignore_errors=True)
            sys.exit(1)
        except SystemExit:
            shutil.rmtree(venv_dir, ignore_errors=True)
            raise
        except BaseException as e:
            print(f"\n[PRISL-CODE] Install failed ({type(e).__name__}: {e}). Cleaning up...")
            shutil.rmtree(venv_dir, ignore_errors=True)
            sys.exit(1)
    elif not _verify_venv_imports(venv_python):
        print(
            "[PRISL-CODE] Virtual environment is incomplete; "
            "installing/updating packages into ~/.prisl_code/env ..."
        )
        try:
            _ensure_venv_dependencies(venv_python)
        except KeyboardInterrupt:
            print("\n[PRISL-CODE] Install interrupted by user.")
            sys.exit(1)

    print("[PRISL-CODE] Relaunching inside virtual environment...\n")
    script_path = os.path.abspath(__file__)
    relaunch_kw: Dict[str, Any] = {}
    try:
        rc = subprocess.call([venv_python, script_path] + sys.argv[1:], **relaunch_kw)
        sys.exit(rc)
    except KeyboardInterrupt:
        print("\n[PRISL-CODE] Relaunch interrupted by user.")
        sys.exit(1)


def _stdlib_uninstall_prisl_code() -> None:
    """Uninstall without third-party deps (for --uninstall before the app loads)."""
    print("\nUNINSTALL PRISL CODE")
    print(
        "This will permanently delete the virtual environment, LLM binaries, and cache."
    )
    ans = input("Are you absolutely sure you want to proceed? [y/N]: ").strip().lower()
    if ans not in ("y", "yes"):
        print("Uninstall cancelled.")
        sys.exit(0)

    home_dir = os.path.expanduser("~")
    prisl_dir = os.path.join(home_dir, ".prisl_code")
    _remove_prisl_user_home(prisl_dir, print)

    llama_bin = os.path.join(os.getcwd(), "llama_bin")
    if os.path.exists(llama_bin):
        print(f"Removing binaries: {llama_bin}...")
        try:
            shutil.rmtree(llama_bin, ignore_errors=True)
            print("Removed local binaries.")
        except Exception as e:
            print(f"Failed to remove binaries: {e}")

    print("Cleaning up Prisl Code cache and build files...")
    package_dir = os.path.dirname(os.path.abspath(__file__))
    count = 0
    for root, dirs, files in os.walk(package_dir):
        for d in list(dirs):
            if d == "__pycache__" or d.endswith(".egg-info") or d == ".pytest_cache" or d == ".build" or d == "dist":
                target = os.path.join(root, d)
                try:
                    shutil.rmtree(target, ignore_errors=True)
                    count += 1
                except OSError:
                    pass
    print(f"Removed {count} internal cache/build directories.")

    print("Attempting to uninstall package via pip...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "prisl-code", "-y"],
            capture_output=True,
        )
        print("Uninstalled package from current environment (if it was installed).")
    except Exception as e:
        print(f"Could not uninstall via pip: {e}")

    print("\nPrisl Code has been uninstalled successfully.")
    sys.exit(0)


def pre_main() -> None:
    """Run before importing prislcode (direct ``python prislcode.py``)."""
    if "--uninstall" in sys.argv:
        _stdlib_uninstall_prisl_code()
    bootstrap_venv()


def cli_main() -> None:
    """Setuptools console_script entry: bootstrap venv, then run the app."""
    if "--uninstall" in sys.argv:
        _stdlib_uninstall_prisl_code()
    bootstrap_venv()
    from prisl_code.prislcode import main

    main()


if __name__ == "__main__":
    cli_main()
