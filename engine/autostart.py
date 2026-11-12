"""
Start-at-login registration for the Veloce engine, per platform:
  Windows: HKCU\\...\\Run registry value
  macOS:   ~/Library/LaunchAgents/com.veloce.engine.plist
  Linux:   ~/.config/autostart/veloce.desktop  (XDG autostart; works on GNOME, KDE, XFCE, ...)
"""

import os
import shlex
import subprocess
import sys
from typing import List

APP_ID = "com.veloce.engine"


def launch_command() -> List[str]:
    """The command that starts the engine in background mode."""
    if getattr(sys, "frozen", False):  # PyInstaller binary
        base = [sys.executable]
    else:
        python = sys.executable
        if sys.platform == "win32":
            pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
            python = pythonw if os.path.exists(pythonw) else python
        main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
        base = [python, main_py]
    return base + ["app", "--background"]


def _linux_path() -> str:
    config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(config, "autostart", "veloce.desktop")


def _mac_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{APP_ID}.plist")


def enable() -> str:
    cmd = launch_command()
    if sys.platform == "win32":
        import winreg
        value = subprocess.list2cmdline(cmd)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Veloce", 0, winreg.REG_SZ, value)
        return "Registered in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"

    if sys.platform == "darwin":
        from xml.sax.saxutils import escape
        args = "\n".join(f"        <string>{escape(a)}</string>" for a in cmd)
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{APP_ID}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key><true/>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
"""
        path = _mac_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(plist)
        subprocess.run(["launchctl", "unload", path], capture_output=True)
        subprocess.run(["launchctl", "load", path], capture_output=True)
        return f"Installed LaunchAgent {path}"

    path = _linux_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Veloce Engine\n"
            "Comment=Download accelerator engine for the Veloce browser extension\n"
            f"Exec={' '.join(shlex.quote(c) for c in cmd)}\n"
            "Terminal=false\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
    return f"Installed {path}"


def disable() -> str:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, "Veloce")
        except FileNotFoundError:
            pass
        return "Removed start-at-login registry entry"

    path = _mac_path() if sys.platform == "darwin" else _linux_path()
    if sys.platform == "darwin" and os.path.exists(path):
        subprocess.run(["launchctl", "unload", path], capture_output=True)
    if os.path.exists(path):
        os.remove(path)
    return f"Removed {path}"


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, "Veloce")
            return True
        except FileNotFoundError:
            return False
    return os.path.exists(_mac_path() if sys.platform == "darwin" else _linux_path())
