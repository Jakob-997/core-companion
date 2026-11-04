"""A private, unprivileged Tor process; no system service or global proxy changes."""

import os
import re
import socket

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .linux_cold import SYSTEM_PATH, _system_tool
from .permanent_airgap import PermanentAirgap
from .storage import data_directory


class TorSession(QObject):
    ready = Signal()
    progress = Signal(int)
    unavailable = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proxy = None
        self.process = None
        self.bootstrapped = False
        self.output = ""
        self.bootstrap_progress = -1
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(180000)
        self.deadline.timeout.connect(self._timed_out)

    def start(self):
        if PermanentAirgap.is_committed():
            raise ValueError("Tor is forbidden on a permanently offline computer.")
        if self.process is not None:
            return
        executable = _system_tool("tor")
        if not executable or not _system_tool("curl"):
            raise ValueError("Install Tor and curl first: sudo apt install tor curl")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.proxy = "127.0.0.1:" + str(listener.getsockname()[1])
        directory = data_directory() / "tor"
        if directory.is_symlink():
            raise ValueError("Tor storage must not be a symbolic link.")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        configuration = directory / "companion-torrc"
        # Tor requires a regular configuration file; do not inherit /etc/tor/torrc.
        fd = os.open(configuration, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        process = QProcess(self)
        self.process = process
        self.output = ""
        self.bootstrap_progress = -1
        environment = QProcessEnvironment()
        environment.insert("PATH", SYSTEM_PATH)
        environment.insert("LANG", "C")
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self._read(process))
        process.finished.connect(lambda *_: self._failed(process))
        process.errorOccurred.connect(lambda *_: self._failed(process))
        process.start(executable, [
            "--defaults-torrc", str(configuration), "-f", str(configuration),
            "--DataDirectory", str(directory), "--SocksPort", self.proxy,
            "--ClientOnly", "1", "--RunAsDaemon", "0", "--SafeSocks", "1",
            "--ControlPort", "0", "--DNSPort", "0", "--TransPort", "0",
            "--HTTPTunnelPort", "0", "--ORPort", "0", "--DirPort", "0",
            "--Log", "notice stdout",
        ])
        self.deadline.start()

    def _read(self, process):
        if process is not self.process:
            return
        self.output = (self.output + bytes(process.readAllStandardOutput()).decode("utf-8", "replace"))[-16000:]
        matches = re.findall(r"Bootstrapped ([0-9]+)%", self.output)
        if not matches:
            return
        progress = int(matches[-1])
        if progress != self.bootstrap_progress:
            self.bootstrap_progress = progress
            self.progress.emit(progress)
        if progress == 100 and not self.bootstrapped:
            self.bootstrapped = True
            self.deadline.stop()
            self.ready.emit()

    def _failed(self, process):
        if process is not self.process:
            return
        self.stop()
        self.unavailable.emit("Tor is unavailable. Downloads and node connections have no direct fallback.")

    def _timed_out(self):
        self.stop()
        self.unavailable.emit("Tor could not connect. Check your connection and retry; direct access remains blocked.")

    def stop(self):
        self.deadline.stop()
        process, self.process = self.process, None
        self.bootstrapped = False
        if process is not None:
            process.terminate()
            if not process.waitForFinished(3000):
                process.kill()
                process.waitForFinished(3000)
            process.deleteLater()
