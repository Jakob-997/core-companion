"""Install the locked dependencies and a per-user Linux desktop launcher."""

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-desktop", action="store_true", help="install dependencies only")
    args = parser.parse_args()
    if sys.platform != "linux" or not (3, 11) <= sys.version_info[:2] < (3, 16):
        parser.error("Use Linux with Python 3.11–3.15.")
    if os.geteuid() == 0:
        parser.error("Run this installer as your normal desktop user, without sudo.")
    root = Path(__file__).resolve().parent
    if not args.no_desktop and any(character in str(root) for character in "%\r\n\t"):
        parser.error("Move the app to a folder without percent signs or control characters in its name.")
    environment = root / ".venv"
    if environment.is_symlink():
        parser.error("The .venv path is a symbolic link. Use a fresh application folder.")
    try:
        if not environment.exists():
            venv.EnvBuilder(with_pip=True).create(environment)
        python = str(environment / "bin" / "python")
        if not (environment / "pyvenv.cfg").is_file() or not Path(python).is_file():
            raise OSError("The existing .venv is incomplete. Move it aside, then run the installer again.")
        subprocess.run([
            python, "-E", "-s", "-m", "pip", "--isolated", "install",
            "--require-hashes", "--only-binary=:all:", "--no-deps", "--force-reinstall",
            "-r", str(root / "requirements.txt"),
        ], check=True)
        subprocess.run([python, "-E", "-s", "-m", "pip", "check"], check=True)
        subprocess.run([
            python, "-E", "-s", "-c",
            "from PySide6 import QtWidgets, QtSvg; import mnemonic, qrcode",
        ], check=True)
        launcher = root / "core-companion"
        launcher.chmod(0o755)
        if not args.no_desktop:
            data_home = Path(os.environ.get("XDG_DATA_HOME", ""))
            if not data_home.is_absolute():
                data_home = Path.home() / ".local" / "share"
            applications = data_home / "applications"
            applications.mkdir(parents=True, exist_ok=True)
            # Desktop Entry quoting is separate from shell quoting; Exec uses no shell.
            executable = str(launcher)
            executable = executable.replace("\\", "\\\\\\\\")
            for character in ('"', "`", "$"):
                executable = executable.replace(character, "\\\\" + character)
            (applications / "core-companion.desktop").write_text(
                "[Desktop Entry]\nType=Application\nName=Core Companion\n"
                "Comment=Bitcoin Core wallet companion\n"
                f'Exec="{executable}"\nIcon={root / "companion" / "icon.svg"}\nTerminal=false\nStartupWMClass=core-companion\n'
                "Categories=Office;Finance;\nStartupNotify=true\n", encoding="utf-8",
            )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Installation stopped: {exc}\nOn Debian, install python3-venv and try again.", file=sys.stderr)
        return 1
    print("Installed. Open Core Companion from your applications menu." if not args.no_desktop
          else "Dependencies installed. Run ./core-companion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
