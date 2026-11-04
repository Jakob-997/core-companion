"""Private file permissions and atomic writes for Core wallet backups."""

import json
import os
import re
import secrets
import shutil
import stat
from pathlib import Path
from .linux_cold import ColdSetupError


def data_directory():
    root = Path(os.environ.get("XDG_DATA_HOME", ""))
    return (root if root.is_absolute() else Path.home() / ".local" / "share") / "core-companion"


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "-" + secrets.token_hex(8))
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, ensure_ascii=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ColdWalletStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_directory() / "cold-wallets"
        self._lock_fd = None

    def acquire(self):
        if self._lock_fd is not None:
            return
        import fcntl
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ColdSetupError("The wallet storage directory must not be a symbolic link.")
        fd = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise ColdSetupError("Another cold signer is using saved wallet storage. Close it first.") from None
        self._lock_fd = fd

    def release(self):
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def _directory(self, wallet_id):
        if not re.fullmatch(r"[0-9a-f]{32}", wallet_id):
            raise ColdSetupError("Invalid saved wallet identifier.")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ColdSetupError("The saved wallet directory must not be a symbolic link.")
        os.chmod(self.root, 0o700)
        directory = self.root / wallet_id
        if directory.is_symlink():
            raise ColdSetupError("The saved wallet path must not be a symbolic link.")
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        return directory

    def list_wallets(self):
        if not self.root.exists():
            return []
        result = []
        for directory in sorted(self.root.iterdir()):
            if re.fullmatch(r"[0-9a-f]{32}", directory.name) and not directory.is_symlink():
                try:
                    metadata = self.read_metadata(directory.name)
                    result.append((directory.name, metadata.get("name", "Cold wallet")))
                except (OSError, ValueError, ColdSetupError):
                    continue
        return result

    def read_metadata(self, wallet_id):
        path = self._directory(wallet_id) / "metadata.json"
        if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
            raise ColdSetupError("The saved wallet metadata is invalid.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("format") != 1:
            raise ColdSetupError("The saved wallet format is unsupported.")
        if (not isinstance(data.get("name"), str) or not isinstance(data.get("wallet_type"), str)
                or not isinstance(data.get("result"), dict) or not isinstance(data["result"].get("address"), str)
                or not isinstance(data.get("address_records", []), list)
                or any(not isinstance(item, dict) or not isinstance(item.get("address"), str)
                       or not isinstance(item.get("label", ""), str) for item in data.get("address_records", []))
                or not isinstance(data.get("hidden_addresses", []), list)
                or any(not isinstance(value, str) for value in data.get("hidden_addresses", []))):
            raise ColdSetupError("The saved wallet metadata is incomplete or invalid.")
        result_encrypted = data["result"].get("encrypted")
        metadata_encrypted = data.get("encrypted")
        if ((result_encrypted is not None and type(result_encrypted) is not bool)
                or (metadata_encrypted is not None and type(metadata_encrypted) is not bool)
                or (result_encrypted is not None and metadata_encrypted is not None
                    and result_encrypted is not metadata_encrypted)):
            raise ColdSetupError("The saved wallet encryption status is invalid.")
        return data

    def save(self, rpc, wallet_id, metadata):
        self.acquire()
        if len(json.dumps(metadata, ensure_ascii=True).encode("utf-8")) > 2 * 1024 * 1024:
            raise ColdSetupError("The public address list exceeds the saved metadata limit.")
        encrypted = "unlocked_until" in rpc.call("getwalletinfo", wallet="cold-signer")
        result = metadata.get("result")
        if not isinstance(result, dict) or result.get("encrypted") is not encrypted:
            raise ColdSetupError("The wallet encryption status changed; keep the signer open and retry.")
        metadata = dict(metadata, encrypted=encrypted)
        wallet_id = wallet_id or secrets.token_hex(16)
        directory = self._directory(wallet_id)
        temporary = directory / ("backup-" + secrets.token_hex(8) + ".dat")
        try:
            rpc.call("backupwallet", [str(temporary)], wallet="cold-signer")
            if temporary.is_symlink() or not temporary.is_file() or not 0 < temporary.stat().st_size <= 256 * 1024 * 1024:
                raise ColdSetupError("Core did not produce a regular wallet backup.")
            os.chmod(temporary, 0o600)
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, directory / "wallet.dat")
            atomic_json(directory / "metadata.json", dict(metadata, format=1))
            if os.name == "posix":
                fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)
        return wallet_id

    def restore(self, wallet_id, destination):
        self.acquire()
        metadata = self.read_metadata(wallet_id)
        source = self._directory(wallet_id) / "wallet.dat"
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(source, flags)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 256 * 1024 * 1024:
                raise ColdSetupError("The saved wallet backup is invalid.")
            destination.parent.mkdir(mode=0o700)
            with destination.open("xb") as output:
                os.chmod(destination, 0o600)
                shutil.copyfileobj(stream, output)
        return metadata
