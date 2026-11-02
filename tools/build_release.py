"""Build a deterministic source release from a clean Git checkout; stdlib only."""

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def main():
    if git("status", "--porcelain").strip():
        raise SystemExit("Commit or set aside local changes before building a release.")
    revision = git("rev-parse", "HEAD").decode().strip()
    epoch = int(git("show", "-s", "--format=%ct", "HEAD"))
    files = {}
    for name in git("ls-files", "-z").decode().split("\0"):
        if not name or name.startswith((".github/", "tools/")) or name == ".gitignore":
            continue
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"Unexpected release file: {name}")
        # Use committed bytes so Windows checkout line endings cannot alter releases.
        files[name] = git("show", f"{revision}:{name}")
    init = files["companion/__init__.py"].decode()
    marker = "DEVELOPMENT_BUILD = True"
    if init.count(marker) != 1:
        raise SystemExit("Cannot identify the development-build switch.")
    files["companion/__init__.py"] = init.replace(marker, "DEVELOPMENT_BUILD = False").encode()
    namespace = {}
    exec(files["companion/__init__.py"], namespace)
    version = namespace["__version__"]
    name = f"core-companion-{version}"
    files["BUILD_INFO"] = f"Version: {version}\nSource commit: {revision}\nDevelopment bypass: disabled\n".encode()
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {path}\n" for path, data in sorted(files.items())
    ).encode()
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    archive = destination / f"{name}.tar"
    with tarfile.open(archive, mode="w", format=tarfile.USTAR_FORMAT) as package:
        for path, data in sorted(files.items()):
            entry = tarfile.TarInfo(f"{name}/{path}")
            entry.size, entry.mtime = len(data), epoch
            entry.mode = 0o755 if path == "core-companion" else 0o644
            package.addfile(entry, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"{archive}\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
