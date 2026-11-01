"""Bounded, single-QR transport through the system zbarcam decoder."""

import shutil
from PySide6.QtCore import QProcess, Signal


class QRScanner(QProcess):
    decoded = Signal(str)
    failed = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.buffer = bytearray()
        self.stopping = False
        self.readyReadStandardOutput.connect(self._read)
        self.readyReadStandardError.connect(self.readAllStandardError)
        self.errorOccurred.connect(self._error)
        self.finished.connect(self._finished)

    def scan(self):
        if self.state() != QProcess.ProcessState.NotRunning:
            return
        executable = shutil.which("zbarcam")
        if not executable:
            self.failed.emit("Install zbar-tools to scan with a camera, or paste the QR contents.")
            return
        self.buffer.clear()
        self.stopping = False
        self.start(executable, ["--quiet", "--raw"])

    def stop(self):
        self.stopping = True
        if self.state() != QProcess.ProcessState.NotRunning:
            self.kill()
            self.waitForFinished(3000)
        self.buffer.clear()

    def _read(self):
        if self.stopping:
            self.readAllStandardOutput()
            return
        self.buffer.extend(bytes(self.readAllStandardOutput()))
        if len(self.buffer) > 8192:
            self.stop()
            self.failed.emit("QR payload exceeds the 8 KiB limit.")
        elif b"\n" in self.buffer:
            raw = bytes(self.buffer).split(b"\n", 1)[0]
            self.stop()
            try:
                text = raw.decode("utf-8").strip()
            except UnicodeError:
                self.failed.emit("QR contents are not valid UTF-8 text.")
                return
            self.decoded.emit(text)

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.failed.emit("Could not start zbarcam. Check its installation and camera access.")

    def _finished(self, _code, _status):
        if not self.stopping:
            self.failed.emit("Camera scanner stopped without reading a QR. Check camera access and try again.")
