"""Permanent Linux network verification and temporary swap isolation."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


SYSTEM_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


class ColdSetupError(RuntimeError):
    pass


def _system_tool(name):
    """Resolve host tools without searching user-controlled PATH entries."""
    return shutil.which(name, path=SYSTEM_PATH)


def _session_environment():
    env = {"PATH": SYSTEM_PATH, "LANG": "C", "LC_ALL": "C"}
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
        pkexec = _system_tool("pkexec")
        executable = _system_tool(tool)
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
    """Verify the permanent offline policy; never restore or enable networking."""
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
    def _interfaces():
        ip = _system_tool("ip")
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

    def assert_disabled(self):
        from .permanent_airgap import PermanentAirgap
        PermanentAirgap.assert_enforced()

    def disable(self):
        self.assert_disabled()

class ColdSystemSession:
    """Require permanent offline protection; disable/restore swap for key use."""

    def __init__(self, disable_networking=True):
        self.disable_networking = bool(disable_networking)
        self.network = NetworkSession()
        self.swap = SwapSession()

    def begin(self):
        if self.disable_networking:
            self.network.disable()
        else:
            from .permanent_airgap import PermanentAirgap
            if PermanentAirgap.is_committed():
                raise ColdSetupError("Development networking is forbidden on this permanently offline computer.")
        self.swap.disable()

    def assert_disabled(self):
        """Fail if host isolation was changed after the cold session began."""
        if _active_swaps():
            raise ColdSetupError("System swap is active. Close the signer before continuing.")
        if self.disable_networking:
            self.network.assert_disabled()

    def restore(self):
        """Restore swap only after Core stops. Networking is never restored."""
        self.swap.restore()
