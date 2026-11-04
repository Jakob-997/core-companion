"""Download and verify the official Bitcoin Core Linux release."""

import argparse
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

if __package__:
    from .linux_cold import SYSTEM_PATH, _system_tool
    from .permanent_airgap import PermanentAirgap
    from .network_privacy import checked_proxy, curl_command
else:
    from linux_cold import SYSTEM_PATH, _system_tool
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from companion.permanent_airgap import PermanentAirgap
    from companion.network_privacy import checked_proxy, curl_command


DOWNLOAD_PAGE = "https://bitcoincore.org/en/download/"
VERIFIER = Path(__file__).parent / "vendor" / "bitcoin-core" / "verify.py"
MINIMUM_TRUSTED_SIGNATURES = 3
# Signers of Bitcoin Core v32.1's official SHA256SUMS.asc:
# https://bitcoincore.org/bin/bitcoin-core-32.1/SHA256SUMS.asc
# Three of these eight pinned keys must sign the release checksum.
TRUSTED_RELEASE_SIGNERS = (
    "152812300785C96444D3334D17565732E08E5E41",
    "0AD83877C1F0CD1EE9BD660AD7CC770B81FD22A8",
    "CFB16E21C950F67FA95E558F2EEB9F5CC09526C1",
    "F4FC70F07310028424EFC20A8E4256593F177720",
    "E61773CD6E01040E2F1BD78CE7E2984B6289C93A",
    "F2CFC4ABD0B99D837EEBB7D09B79B45691DB4173",
    "ED9BDF7AD6A55E232E84524257FF9BDBCC301009",
    "A0083660F235A27000CD3C81CE6EC49945C17EA6",
)
KEYSERVER = "https://keys.openpgp.org/vks/v1/by-fingerprint/"
MAX_FILE_SIZE = 1024 * 1024 * 1024
MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024
active_verifier = None


class CoreDownloadError(Exception):
    pass


def _run_gpg(args, environment, input_text=None):
    global active_verifier
    gpg = _system_tool("gpg")
    if not gpg:
        raise CoreDownloadError("Install GPG, then try again.")
    active_verifier = subprocess.Popen(
        [gpg, "--batch", *args],
        env=environment,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
    )
    try:
        output, error = active_verifier.communicate(input=input_text, timeout=35)
    except subprocess.TimeoutExpired as exc:
        _terminate_active_process()
        raise CoreDownloadError("Timed out while retrieving Core signing keys.") from exc
    except BaseException:
        _terminate_active_process()
        raise
    code = active_verifier.returncode
    active_verifier = None
    return code, output, error


def _download(url, destination, proxy=None, *, limit=2 * 1024 * 1024, timeout=120):
    global active_verifier
    if PermanentAirgap.is_committed():
        raise CoreDownloadError("Downloads are forbidden on a permanently offline computer.")
    try:
        command = curl_command(url, destination, proxy=proxy, limit=limit, timeout=timeout)
        active_verifier = subprocess.Popen(command, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True,
            env={"PATH": SYSTEM_PATH, "LANG": "C", "LC_ALL": "C"})
        _, error = active_verifier.communicate(timeout=timeout + 5)
        code = active_verifier.returncode
        active_verifier = None
        if code or not 0 < destination.stat().st_size <= limit:
            raise CoreDownloadError("HTTPS download failed" + (" over Tor; no direct fallback" if proxy else "")
                                    + ". " + error.decode("utf-8", "replace")[-400:])
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        _terminate_active_process()
        raise CoreDownloadError("Download failed; the selected network route was not changed.") from exc


def _prepare_signing_keyring(home, proxy=None):
    home.mkdir(mode=0o700)
    # Local GPG verification must never retrieve keys through dirmngr.
    (home / "gpg.conf").write_text("no-auto-key-retrieve\nauto-key-locate clear\nno-auto-key-import\n")
    environment = {"PATH": SYSTEM_PATH, "LANG": "C", "LC_ALL": "C", "GNUPGHOME": str(home)}
    trusted = []
    for fingerprint in TRUSTED_RELEASE_SIGNERS:
        key = home.parent / (fingerprint + ".asc")
        try:
            _download(KEYSERVER + fingerprint, key, proxy)
        except CoreDownloadError:
            print(f"Could not retrieve pinned signer {fingerprint[-8:]}; trying the remaining keys.", file=sys.stderr, flush=True)
            continue
        code, _, _ = _run_gpg(["--import", str(key)], environment)
        if code:
            continue
        code, output, _ = _run_gpg(["--with-colons", "--fingerprint", fingerprint], environment)
        if code == 0 and any(
            len(fields) > 9 and fields[0] == "fpr" and fields[9].upper() == fingerprint
            for fields in (line.split(":") for line in output.splitlines())
        ):
            trusted.append(fingerprint)
    if len(trusted) < MINIMUM_TRUSTED_SIGNATURES:
        raise CoreDownloadError("Could not retrieve three pinned Bitcoin Core signing keys.")
    ownertrust = "".join(f"{fingerprint}:6:\n" for fingerprint in trusted)
    code, _, _ = _run_gpg(["--import-ownertrust"], environment, ownertrust)
    if code:
        raise CoreDownloadError("Could not prepare the temporary Core verification keyring.")
    return environment


def _terminate_active_process():
    global active_verifier
    if active_verifier and active_verifier.poll() is None:
        try:
            os.killpg(active_verifier.pid, signal.SIGTERM)
            active_verifier.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(active_verifier.pid, signal.SIGKILL)
            except OSError:
                pass
    active_verifier = None


def _stop_verifier(signum, _frame):
    _terminate_active_process()
    raise SystemExit(128 + signum)


def _latest_version(proxy=None):
    with tempfile.TemporaryDirectory(prefix="core-companion-version-") as directory:
        page_file = Path(directory) / "download.html"
        _download(DOWNLOAD_PAGE, page_file, proxy)
        page = page_file.read_text(encoding="utf-8", errors="replace")
    visible = re.sub(r"<[^>]+>", " ", page)
    match = re.search(r"Latest version:\s*([0-9]+(?:\.[0-9]+){1,2})\b", visible)
    if not match:
        raise CoreDownloadError("Could not identify the current stable Core release.")
    version = match.group(1)
    if tuple(map(int, version.split("."))) < (32, 1):
        raise CoreDownloadError("The download page offers a Core release older than the supported 32.1 minimum.")
    return version


def _verified_signers(directory, environment):
    """Count distinct pinned primary keys, not repeated signature packets."""
    code, status, _ = _run_gpg([
        "--status-fd", "1", "--verify", str(directory / "SHA256SUMS.asc"),
        str(directory / "SHA256SUMS"),
    ], environment)
    if code not in (0, 2):
        raise CoreDownloadError("GPG could not verify the release checksums.")
    signers = set()
    for signature in status.split("[GNUPG:] NEWSIG"):
        if any(f"[GNUPG:] {flag}" in signature for flag in ("EXPKEYSIG", "EXPSIG", "REVKEYSIG", "BADSIG", "ERRSIG")):
            continue
        for line in signature.splitlines():
            fields = line.split()
            if len(fields) >= 11 and fields[:2] == ["[GNUPG:]", "VALIDSIG"]:
                primary = fields[-1] if len(fields) >= 12 else fields[2]
                if primary in TRUSTED_RELEASE_SIGNERS:
                    signers.add(primary)
    if len(signers) < MINIMUM_TRUSTED_SIGNATURES:
        raise CoreDownloadError("The checksums need three distinct, valid pinned release signers.")
    return signers


def _linux_target():
    machine = platform.machine().lower()
    if sys.platform != "linux":
        raise CoreDownloadError("Automatic Bitcoin Core download is available on Linux.")
    if machine in ("x86_64", "amd64"):
        return "x86_64", "x86_64-linux"
    if machine in ("aarch64", "arm64"):
        return "aarch64", "aarch64-linux"
    raise CoreDownloadError(f"Automatic Core download does not support {machine} yet.")


def _extract_verified_archive(archive, version, install_root):
    destination = install_root / version
    staging = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=install_root))
    total_size = 0
    top_level = f"bitcoin-{version}"
    try:
        with tarfile.open(archive, "r:gz") as package:
            for member in package:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                    raise CoreDownloadError("The verified archive has an unsafe file path.")
                if not path.parts or path.parts[0] != top_level:
                    raise CoreDownloadError("The verified archive has an unexpected folder layout.")
                if member.isdir():
                    relative = path.parts[1:]
                    if relative:
                        target = staging.joinpath(*relative)
                        target.mkdir(parents=True, exist_ok=True)
                        target.chmod(0o755)
                    continue
                if not member.isfile():
                    raise CoreDownloadError("The verified archive contains a link or special file.")
                if member.size < 0 or member.size > MAX_FILE_SIZE:
                    raise CoreDownloadError("The verified archive contains an oversized file.")
                total_size += member.size
                if total_size > MAX_TOTAL_SIZE:
                    raise CoreDownloadError("The verified archive is larger than expected.")
                relative = path.parts[1:]
                if not relative:
                    raise CoreDownloadError("The verified archive has an unexpected file layout.")
                target = staging.joinpath(*relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = package.extractfile(member)
                if source is None:
                    raise CoreDownloadError("Could not read a file from the verified archive.")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                target.chmod(member.mode & 0o755)

        binary = staging / "bin" / "bitcoind"
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise CoreDownloadError("The verified package did not contain an executable bitcoind.")
        if destination.is_symlink():
            raise CoreDownloadError("The Core install folder is a symbolic link; refusing to replace it.")
        backup = None
        if destination.exists():
            if not destination.is_dir():
                raise CoreDownloadError("The Core install path exists and is not a folder.")
            backup = Path(tempfile.mkdtemp(prefix=f".{version}-old-", dir=install_root))
            backup.rmdir()
        try:
            if backup is not None:
                os.rename(destination, backup)
            os.rename(staging, destination)
        except BaseException:
            # Signals raise SystemExit/KeyboardInterrupt too. Restore the old
            # install even if interruption arrives just after either rename.
            if backup is not None and backup.exists():
                if destination.exists():
                    shutil.rmtree(destination)
                os.rename(backup, destination)
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
        return destination / "bin" / "bitcoind"
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def download_and_verify(proxy=None):
    if PermanentAirgap.is_committed():
        raise CoreDownloadError("Downloads are forbidden on a permanently offline computer. Use verified offline media.")
    global active_verifier
    if proxy is not None:
        checked_proxy(proxy)
    if not _system_tool("gpg") or not _system_tool("curl"):
        raise CoreDownloadError("Install GPG and curl, then try again.")
    if not VERIFIER.is_file():
        raise CoreDownloadError("Bitcoin Core's official verification script is missing.")

    architecture, _ = _linux_target()
    temp_root = Path(tempfile.mkdtemp(prefix="core-companion-verify-"))
    temp_root.chmod(0o700)
    gpg_home = temp_root / "gnupg"
    old_handlers = {
        signal.SIGTERM: signal.signal(signal.SIGTERM, _stop_verifier),
        signal.SIGINT: signal.signal(signal.SIGINT, _stop_verifier),
    }
    try:
        version = _latest_version(proxy)
        expected_archive = f"bitcoin-{version}-{architecture}-linux-gnu.tar.gz"
        work_dir = temp_root / "release"
        work_dir.mkdir()
        release_url = f"https://bitcoincore.org/bin/bitcoin-core-{version}/"
        for name in ("SHA256SUMS", "SHA256SUMS.asc"):
            _download(release_url + name, work_dir / name, proxy, limit=4 * 1024 * 1024)
        environment = _prepare_signing_keyring(gpg_home, proxy)
        signers = _verified_signers(work_dir, environment)
        _download(release_url + expected_archive, work_dir / expected_archive, proxy,
                  limit=MAX_FILE_SIZE, timeout=7200)
        command = [sys.executable, "-E", "-s", str(VERIFIER), "--min-good-sigs",
                   str(MINIMUM_TRUSTED_SIGNATURES), "--json", "bin", "SHA256SUMS", expected_archive]
        print(
            f"Checking the signed Core {version} release and downloading {architecture} Linux files…",
            file=sys.stderr,
            flush=True,
        )
        active_verifier = subprocess.Popen(
            command,
            cwd=work_dir,
            env=environment,
            stdout=subprocess.PIPE,
            start_new_session=True,
            text=True,
        )
        output, _ = active_verifier.communicate()
        code = active_verifier.returncode
        active_verifier = None
        if code != 0:
            raise CoreDownloadError(
                f"Bitcoin Core verification did not pass (verifier exit {code}). "
                "The pinned signer threshold was not met; review the status output."
            )
        try:
            report = json.loads(output)
        except (TypeError, json.JSONDecodeError) as exc:
            raise CoreDownloadError("Bitcoin Core's verifier returned an unreadable result.") from exc
        trusted = report.get("good_trusted_sigs", [])
        verified = report.get("verified_binaries", {})
        if len(trusted) < MINIMUM_TRUSTED_SIGNATURES:
            raise CoreDownloadError("Fewer than three trusted signatures were verified.")
        if expected_archive not in verified:
            raise CoreDownloadError("The verifier did not confirm the expected Linux archive.")

        archive = (work_dir / expected_archive).resolve()
        if archive.parent != work_dir.resolve() or not archive.is_file():
            raise CoreDownloadError("The verified Bitcoin Core archive is missing.")
        data_home = os.environ.get("XDG_DATA_HOME")
        data_home = Path(data_home) if data_home and Path(data_home).is_absolute() else Path.home() / ".local" / "share"
        install_base = data_home / "core-companion" / "bitcoin-core"
        install_base.mkdir(parents=True, exist_ok=True, mode=0o700)
        binary = _extract_verified_archive(archive, version, install_base)
        print(f"Installed verified Bitcoin Core {version}.", file=sys.stderr, flush=True)
        return {
            "ok": True,
            "version": version,
            "path": str(binary),
            "trusted_signatures": len(signers),
            "archive_sha256": verified[expected_archive],
        }
    finally:
        _terminate_active_process()
        try:
            gpgconf = _system_tool("gpgconf")
            if gpgconf:
                subprocess.run(
                    [gpgconf, "--homedir", str(gpg_home), "--kill", "all"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    env={**os.environ, "PATH": SYSTEM_PATH},
                )
        except (OSError, subprocess.TimeoutExpired):
            pass
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        shutil.rmtree(temp_root, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tor-proxy", help="local Tor SOCKS proxy; never falls back to direct")
    args = parser.parse_args()
    try:
        result = download_and_verify(args.tor_proxy)
    except CoreDownloadError as exc:
        result = {"ok": False, "error": str(exc)}
    except Exception:
        result = {"ok": False, "error": "Download or installation failed. No verified Core was installed."}
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
