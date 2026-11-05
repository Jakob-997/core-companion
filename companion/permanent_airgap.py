"""Permanent, root-owned Debian/systemd offline policy. No enable-network path."""

import os
import stat
import sys
import time
from pathlib import Path

from .linux_cold import ColdSetupError, _PrivilegedCommand, _system_tool, NetworkSession
from .storage import atomic_json, data_directory


class PermanentAirgap:
    RESOURCES = Path(__file__).with_name("airgap")
    FILES = {
        "airgap.nft": Path("/etc/core-companion/airgap.nft"),
        "enforce-airgap": Path("/usr/local/libexec/core-companion-airgap"),
        "core-companion-airgap.service": Path("/etc/systemd/system/core-companion-airgap.service"),
        "core-companion-airgap.timer": Path("/etc/systemd/system/core-companion-airgap.timer"),
    }
    STATUS = Path("/run/core-companion-airgap/status")
    UNITS = Path("/etc/systemd/system")
    BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
    UPTIME = Path("/proc/uptime")
    RADIOS = Path("/sys/class/rfkill")
    SERVICES = (
        "NetworkManager.service", "NetworkManager-dispatcher.service", "NetworkManager-wait-online.service",
        "systemd-networkd.service", "systemd-networkd.socket", "systemd-networkd-wait-online.service",
        "networking.service", "wpa_supplicant.service", "iwd.service", "connman.service",
        "bluetooth.service", "dhcpcd.service", "dhcpcd5.service",
        "tor.service", "tor@default.service",
        "dbus-org.freedesktop.NetworkManager.service", "dbus-org.freedesktop.network1.service",
        "dbus-fi.w1.wpa_supplicant1.service",
        "nftables.service", "firewalld.service", "ufw.service",
    )

    @classmethod
    def marker(cls):
        return data_directory() / "permanent-airgap.json"

    @classmethod
    def is_committed(cls):
        return cls.marker().exists() or cls.marker().is_symlink() or any(
            path.exists() or path.is_symlink() for path in cls.FILES.values()
        )

    @staticmethod
    def saved_wallets_exist():
        root = data_directory() / "cold-wallets"
        try:
            if root.is_symlink():
                return True
            with os.scandir(root) as entries:
                for entry in entries:
                    # Treat incomplete saves as sensitive, without reading private files.
                    if entry.is_symlink() or entry.is_dir(follow_symlinks=False):
                        return True
            return False
        except FileNotFoundError:
            return False
        except OSError:
            return True  # Unreadable cold-wallet storage must not permit an online fallback.

    @staticmethod
    def _trusted_bytes(path):
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_mode & 0o022 or info.st_size > 65536):
                raise ColdSetupError("The permanent offline policy is not a trusted root-owned file.")
            return stream.read(65537)

    @staticmethod
    def _systemctl(*args):
        executable = _system_tool("systemctl")
        if not executable:
            raise ColdSetupError("Permanent offline mode requires systemd.")
        return NetworkSession._run_capture([executable, *args])

    @classmethod
    def prerequisites(cls):
        missing = [name for name in ("pkexec", "install", "systemctl", "nft", "rfkill", "ip")
                   if not _system_tool(name)]
        if sys.platform != "linux" or not Path("/run/systemd/system").is_dir():
            raise ColdSetupError("Permanent offline mode requires a Debian/systemd installation.")
        if missing:
            raise ColdSetupError(
                "Install the offline-policy tools before committing this computer: "
                "sudo apt install nftables rfkill iproute2 pkexec. Missing: " + ", ".join(missing)
            )

    @classmethod
    def assert_enforced(cls):
        """Read fresh root-service success and independently inspect links/radios."""
        try:
            for resource, installed in cls.FILES.items():
                if cls._trusted_bytes(installed) != (cls.RESOURCES / resource).read_bytes():
                    raise ColdSetupError("The permanent offline policy is missing or differs from this app version.")
            for unit in cls.SERVICES:
                path = cls.UNITS / unit
                if not path.is_symlink() or path.resolve() != Path("/dev/null"):
                    raise ColdSetupError("A network or firewall manager is not permanently masked.")
            if cls._systemctl("is-enabled", "core-companion-airgap.service").stdout.strip() != "enabled":
                raise ColdSetupError("The boot-time offline service is not enabled.")
            if cls._systemctl("is-enabled", "core-companion-airgap.timer").stdout.strip() != "enabled":
                raise ColdSetupError("The offline guard timer is not enabled.")
            if cls._systemctl("is-active", "core-companion-airgap.timer").stdout.strip() != "active":
                raise ColdSetupError("The permanent offline guard is not running.")
            boot_id, timestamp = cls._trusted_bytes(cls.STATUS).decode("ascii").splitlines()
            current_boot = cls.BOOT_ID.read_text().strip()
            uptime = float(cls.UPTIME.read_text().split()[0])
            if boot_id != current_boot or not 0 <= uptime - float(timestamp) <= 8:
                raise ColdSetupError("The permanent offline guard has no fresh success record for this boot.")
            if any(up for _, up in NetworkSession._interfaces()):
                raise ColdSetupError("A network link became active.")
            for radio in cls.RADIOS.glob("rfkill*"):
                if (radio / "soft").read_text().strip() != "1" and (radio / "hard").read_text().strip() != "1":
                    raise ColdSetupError("A radio is not blocked.")
        except (OSError, ValueError) as exc:
            raise ColdSetupError("Permanent offline protection cannot be verified. Private-key operations are blocked.") from exc

    @classmethod
    def activate(cls):
        """Commit first; failed setup never rolls back into an online installation."""
        cls.prerequisites()
        marker = cls.marker()
        atomic_json(marker, {"format": 1, "permanent_cold": True})
        # Commit the directory entry as well as the file before privileged changes.
        fd = os.open(marker.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            cls.assert_enforced()
            return
        except ColdSetupError:
            pass
        for directory in ("/etc/core-companion", "/usr/local/libexec"):
            _PrivilegedCommand.run("install", "-d", "-o", "root", "-g", "root", "-m", "0755", directory)
        for resource, installed in cls.FILES.items():
            _PrivilegedCommand.run("install", "-o", "root", "-g", "root", "-m",
                                   "0755" if resource == "enforce-airgap" else "0644",
                                   cls.RESOURCES / resource, installed)
        _PrivilegedCommand.run("systemctl", "daemon-reload")
        _PrivilegedCommand.run("systemctl", "mask", *cls.SERVICES)
        for unit in cls.SERVICES:
            if cls._systemctl("is-active", unit).stdout.strip() in ("active", "activating", "reloading"):
                _PrivilegedCommand.run("systemctl", "stop", unit)
        _PrivilegedCommand.run("systemctl", "enable", "--now", "core-companion-airgap.service", "core-companion-airgap.timer")
        os.sync()  # Persist installed boot policy before private-key use is allowed.
        for _ in range(30):
            try:
                cls.assert_enforced()
                return
            except ColdSetupError:
                time.sleep(0.1)
        cls.assert_enforced()
