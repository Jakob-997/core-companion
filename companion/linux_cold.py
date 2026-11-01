"""Linux host isolation for the short-lived cold signer session."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


class ColdSetupError(RuntimeError):
    pass


def _session_environment():
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"}
    for key in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _decode_mount_path(value):
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def _mount_type(path):
    """Return the filesystem type of the longest matching /proc/mounts entry."""
    target = Path(path).resolve()
    best = None
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ColdSetupError("Cannot verify that temporary storage is RAM-backed.") from exc
    for line in lines:
        fields = line.split()
        if len(fields) < 3:
            continue
        mountpoint = Path(_decode_mount_path(fields[1])).resolve()
        try:
            target.relative_to(mountpoint)
        except ValueError:
            continue
        if best is None or len(str(mountpoint)) > len(str(best[0])):
            best = (mountpoint, fields[2])
    if best is None:
        raise ColdSetupError("Cannot find a mounted filesystem for temporary storage.")
    return best[1]


def _active_swaps():
    try:
        lines = Path("/proc/swaps").read_text(encoding="utf-8").splitlines()[1:]
    except OSError as exc:
        raise ColdSetupError("Cannot check whether system swap is enabled.") from exc
    swaps = []
    for line in lines:
        fields = line.split()
        if len(fields) < 5:
            continue
        try:
            priority = int(fields[4])
        except ValueError:
            continue
        swaps.append((_decode_mount_path(fields[0]), priority))
    return swaps


class _PrivilegedCommand:
    @staticmethod
    def run(tool, *args, timeout=90):
        pkexec = shutil.which("pkexec")
        executable = shutil.which(tool)
        if not pkexec or not executable:
            raise ColdSetupError("This Linux system needs pkexec and the standard system networking tools.")
        try:
            result = subprocess.run(
                [pkexec, str(Path(executable).resolve()), *map(str, args)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
                close_fds=True,
                env=_session_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ColdSetupError("The administrator-authorized system operation did not finish.") from exc
        if result.returncode != 0:
            raise ColdSetupError("Linux could not change the requested system setting.")


class SwapSession:
    """Disable active swap devices and restore their original priorities later."""

    def __init__(self):
        self.original = []
        self.changed = False

    def disable(self):
        if sys.platform != "linux":
            raise ColdSetupError("Cold signer setup currently requires Linux.")
        self.original = _active_swaps()
        if not self.original:
            return
        self.changed = True
        try:
            _PrivilegedCommand.run("swapoff", "--all")
            if _active_swaps():
                raise ColdSetupError("Swap is still active after the system reported success.")
        except Exception as exc:
            try:
                self.restore()
            except ColdSetupError:
                pass
            if isinstance(exc, ColdSetupError) and "still active" in str(exc):
                raise
            raise ColdSetupError(
                "Swap could not be fully disabled. Close other programs and try again; "
                "the computer may freeze if it runs low on memory."
            ) from exc

    def restore(self):
        if not self.changed:
            return
        active = {source for source, _ in _active_swaps()}
        for source, priority in self.original:
            if source in active:
                continue
            args = []
            if priority >= 0:
                args.extend(("--priority", str(priority)))
            args.append(source)
            _PrivilegedCommand.run("swapon", *args)
        missing = {source for source, _ in self.original} - {source for source, _ in _active_swaps()}
        if missing:
            raise ColdSetupError("The cold session ended, but some swap devices could not be restored.")
        self.changed = False


class NetworkSession:
    """Turn off every non-loopback Linux network link for the cold session."""

    SERVICE = "org.freedesktop.NetworkManager"
    OBJECT = "/org/freedesktop/NetworkManager"
    INTERFACE = "org.freedesktop.NetworkManager"

    def __init__(self):
        self.was_enabled = None
        self.network_manager_available = False
        self.interfaces = []
        self.changed = False

    @staticmethod
    def _run_capture(args, timeout=10):
        try:
            return subprocess.run(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
                text=True,
                close_fds=True,
                env=_session_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ColdSetupError("Cannot inspect the Linux network state.") from exc

    @staticmethod
    def _nm_enabled():
        busctl = shutil.which("busctl")
        if not busctl:
            raise ColdSetupError("Cannot verify NetworkManager state; install systemd's busctl tool.")
        result = NetworkSession._run_capture([
            busctl, "get-property", NetworkSession.SERVICE, NetworkSession.OBJECT,
            NetworkSession.INTERFACE, "NetworkingEnabled",
        ])
        value = result.stdout.strip().split()
        if result.returncode != 0 or len(value) != 2 or value[0] != "b" or value[1] not in ("true", "false"):
            raise ColdSetupError("NetworkManager is unavailable or returned an unexpected state.")
        return value[1] == "true"

    @staticmethod
    def _interfaces():
        ip = shutil.which("ip")
        if not ip:
            raise ColdSetupError("Cold signer mode requires iproute2 so it can verify network links are down.")
        result = NetworkSession._run_capture([ip, "-json", "link", "show"])
        if result.returncode != 0:
            raise ColdSetupError("Linux could not report the state of its network links.")
        try:
            rows = json.loads(result.stdout)
        except ValueError as exc:
            raise ColdSetupError("Linux returned an unreadable network-link list.") from exc
        if not isinstance(rows, list):
            raise ColdSetupError("Linux returned an unexpected network-link list.")
        interfaces = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("ifname"), str):
                raise ColdSetupError("Linux returned an incomplete network-link record.")
            if row["ifname"] == "lo":
                continue
            flags = row.get("flags", [])
            if not isinstance(flags, list):
                raise ColdSetupError("Linux returned unexpected network-link flags.")
            interfaces.append((row["ifname"], "UP" in flags))
        return interfaces

    @staticmethod
    def _set_manager(enabled):
        nmcli = shutil.which("nmcli")
        if not nmcli:
            raise ColdSetupError("NetworkManager's nmcli tool is unavailable.")
        result = NetworkSession._run_capture([nmcli, "networking", "on" if enabled else "off"], timeout=30)
        if result.returncode != 0:
            raise ColdSetupError("NetworkManager could not change its networking state.")

    @staticmethod
    def _set_link(name, enabled):
        _PrivilegedCommand.run("ip", "link", "set", "dev", name, "up" if enabled else "down")

    def assert_disabled(self):
        if self.network_manager_available or shutil.which("nmcli"):
            if self._nm_enabled():
                raise ColdSetupError("NetworkManager is still enabled; cold Core will not be started.")
        if any(up for _, up in self._interfaces()):
            raise ColdSetupError("A non-loopback network link is still up; cold Core will not be started.")

    def disable(self):
        if sys.platform != "linux":
            raise ColdSetupError("Cold signer setup currently requires Linux.")
        self.interfaces = self._interfaces()
        self.network_manager_available = bool(shutil.which("nmcli"))
        if self.network_manager_available:
            self.was_enabled = self._nm_enabled()
        self.changed = True
        try:
            if self.was_enabled:
                self._set_manager(False)
                if self._nm_enabled():
                    raise ColdSetupError("NetworkManager did not disable networking.")
            for name, was_up in self.interfaces:
                if was_up:
                    self._set_link(name, False)
            still_up = [(name, up) for name, up in self._interfaces() if up]
            if still_up:
                names = ", ".join(name for name, _ in still_up)
                raise ColdSetupError(f"Networking remains enabled on {names}. Cold signer was not started.")
        except Exception:
            try:
                self.restore()
            except ColdSetupError:
                pass
            raise

    def restore(self):
        if not self.changed:
            return
        if self.network_manager_available and self.was_enabled:
            self._set_manager(True)
            if not self._nm_enabled():
                raise ColdSetupError("The cold session ended, but NetworkManager did not restore networking.")
        for name, was_up in self.interfaces:
            if was_up:
                self._set_link(name, True)
        current = dict(self._interfaces())
        missing = [name for name, was_up in self.interfaces if was_up and not current.get(name, False)]
        if missing:
            raise ColdSetupError("The cold session ended, but some network links could not be restored: " + ", ".join(missing))
        self.changed = False


class ColdSystemSession:
    """Disable host networking by default, always disable swap, then restore state."""

    def __init__(self, disable_networking=True):
        self.disable_networking = bool(disable_networking)
        self.network = NetworkSession()
        self.swap = SwapSession()

    def begin(self):
        if self.disable_networking:
            self.network.disable()
        try:
            self.swap.disable()
        except Exception:
            if self.disable_networking:
                try:
                    self.network.restore()
                except ColdSetupError:
                    pass
            raise

    def restore(self):
        errors = []
        # Keep connectivity disabled until swap has been restored and Core is gone.
        for session in (self.swap, self.network):
            try:
                session.restore()
            except ColdSetupError as exc:
                errors.append(str(exc))
        if errors:
            raise ColdSetupError(" ".join(errors))
