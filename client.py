import ctypes
import getpass
import json
import os
from pathlib import Path
import socket
import subprocess

HOST = os.environ.get("RD01_HOST", "192.168.181.128")
PORT = int(os.environ.get("RD01_PORT", "8080"))
MAX_MESSAGE_BYTES = 16384
ROOT = Path.cwd().resolve()  # Keep navigation inside the starting lab folder.


def is_admin():
    """Check current-process elevation, NOT merely admin-group membership."""
    if os.name == "nt":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (OSError, AttributeError):
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def inside_lab(path):
    """Return True only for ROOT or its subdirectories."""
    try:
        path.relative_to(ROOT)
        return True
    except ValueError:
        return False


def run_safe_system_command(name):
    """Run only two fixed, read-only OS tools; never interpolate input."""
    try:
        completed = subprocess.run(
            [name], shell=False, capture_output=True, text=True,
            timeout=5, check=False
        )
        return (completed.stdout or completed.stderr).strip() or "(No output)"
    except (OSError, subprocess.TimeoutExpired) as exc:
        # Show the information without relying on external command availability.
        if name == "whoami":
            return (
                f"{socket.gethostname()}\\{getpass.getuser()}"
                if os.name == "nt" else getpass.getuser()
            )
        if name == "hostname":
            return socket.gethostname()
        return f"[-] Command could not run: {exc}"


def run_command(command, current_dir):
    """Return (display_text, new_directory) without invoking a shell."""
    command = command.strip()
    name, _, argument = command.partition(" ")

    if name in ("whoami", "hostname") and not argument:
        return run_safe_system_command(name), current_dir

    if name == "checkUserLevel" and not argument:
        return (
            "[+] Administrator Privileges."
            if is_admin()
            else "[!!] User Privileges. (No Admin privileges)"
        ), current_dir

    if name == "pwd" and not argument:
        return str(current_dir), current_dir

    if name in ("dir", "ls") and not argument:
        try:
            contents = sorted(current_dir.iterdir(), key=lambda path: path.name.lower())
            if not contents:
                return "(This directory is empty)", current_dir
            lines = [
                ("<DIR>  " if entry.is_dir() else "       ") + entry.name
                for entry in contents[:120]
            ]
            if len(contents) > 120:
                lines.append(f"... and {len(contents) - 120} more items")
            return "\n".join(lines), current_dir
        except OSError as exc:
            return f"[-] Cannot list directory: {exc}", current_dir

    if name == "cd":
        destination = argument.strip().strip('"').strip("'")
        if not destination:
            return "[-] Usage: cd <directory>", current_dir
        target = (current_dir / destination).resolve()
        if not inside_lab(target):
            return "[-] Directory is outside the permitted lab folder", current_dir
        if not target.is_dir():
            return "[-] Directory does not exist", current_dir
        return f"[+] Current working directory is {target}", target

    return (
        "[-] Unsupported command. Use whoami, hostname, pwd, ls, dir, "
        "cd <directory>, checkUserLevel, or terminate."
    ), current_dir


def receive_command(reader):
    raw = reader.readline(MAX_MESSAGE_BYTES + 1)
    if not raw:
        raise ConnectionError("Server disconnected")
    if len(raw) > MAX_MESSAGE_BYTES or not raw.endswith(b"\n"):
        raise ValueError("Invalid or oversized request")
    request = json.loads(raw)
    if not isinstance(request, dict) or not isinstance(request.get("command"), str):
        raise ValueError("Unexpected request format")
    return request["command"]


def send_output(writer, output):
    # Bound replies so a huge directory listing cannot exhaust the connection.
    data = (json.dumps({"output": output}, ensure_ascii=False) + "\n").encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        data = (json.dumps({"output": output[:3000] + "\n[Output shortened]"}) + "\n").encode()
    writer.write(data)
    writer.flush()


def main():
    print(f"[+] Starting lab demonstration client in: {ROOT}")
    with socket.create_connection((HOST, PORT), timeout=10) as connection:
        connection.settimeout(None)
        print("[+] Connected. Commands are limited to the lab demonstration list.")
        current_dir = ROOT
        with connection.makefile("rb") as reader, connection.makefile("wb") as writer:
            while True:
                command = receive_command(reader)
                if command == "terminate":
                    print("[+] Server ended the demonstration")
                    break
                result, current_dir = run_command(command, current_dir)
                send_output(writer, result)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as exc:
        print(f"[-] Connection closed: {exc}")
