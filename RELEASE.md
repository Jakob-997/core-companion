# Release preparation

The current version is **0.1.0rc1**, a Linux source release candidate.
It has no independent security audit or signed release identity yet.

## Build and reproduce

From the exact, clean source commit, with Python 3.11+ and Git:

```sh
python3 tools/build_release.py
```

The builder uses committed file bytes, stable ordering, fixed ownership,
permissions and timestamps. An uncompressed tar keeps archive bytes independent
of compression-library versions. Cross-platform checks compare the archive as
well as its file manifest.
The package includes its source commit, an internal file-hash manifest and an
external archive checksum. Core and Python dependencies are downloaded and
verified separately; they are not opaque bundled executables in this archive.

The builder disables `DEVELOPMENT_BUILD` in the package. Packaged command-line
parsing rejects `--dev-keep-network`; normal cold sessions always require
network and swap isolation. The source checkout retains the testing flag.

Compare the externally supplied checksum before unpacking:

```sh
sha256sum -c core-companion-0.1.0rc1.tar.sha256
tar -xf core-companion-0.1.0rc1.tar
cd core-companion-0.1.0rc1
sha256sum -c SHA256SUMS
python3 install.py
./core-companion
```

Checksums detect differences; they do not authenticate the publisher. Before
public distribution, the owner must sign the archive checksum using an existing
release key whose fingerprint reviewers can verify independently. Do not
generate an unannounced signing identity and treat it as established trust.

## Dependency changes

`requirements.txt` locks direct and transitive dependencies and their official
PyPI wheel SHA-256 values. The installer uses binary wheels, isolated pip
configuration, hash checking and no dependency resolution. `pip check` verifies
the installed dependency metadata afterward. Keep PySide6-Essentials and
shiboken6 on the same release. Review upstream security advisories and compare
the exact upstream metadata before editing hashes or versions. Hash matching
establishes identity with the reviewed package, not package safety.

Qt 6.11.3 replaces 6.10.2 in this candidate. The authoritative references are
[Qt security advisories](https://wiki.qt.io/List_of_known_vulnerabilities_in_Qt_products)
and [official PyPI release metadata](https://pypi.org/pypi/PySide6-Essentials/6.11.3/json).
Installation follows [pip hash-checking guidance](https://pip.pypa.io/en/stable/topics/secure-installs/).

## Gates before a funds-bearing public release

- Independent review of seed handling, public-policy recovery, transaction
  display/signing, OS isolation and release verification.
- Debian desktop acceptance: clean install, actual administrator prompts,
  permanent network disable, swap disable/restore, hotplug isolation failure, closing/crash
  handling, QR camera access, and complete backup/recovery across two devices.
  Use disposable wallets and independently compare every address and signature.
- Select the project's redistribution license and complete dependency notices
  for the chosen distribution format. No license has been assigned to the
  original Companion source by this preparation pass.
- Establish the owner-controlled release-signing key and publish verified signed
  checksums. No public tag or GitHub release is created automatically.

Windows and ARM64 need their own acceptance runs before being advertised as
supported release targets. Existing validation evidence and its limits are in
[AUDIT.md](AUDIT.md).

Permanent offline release acceptance must cover first-time authorization, reboot with the guard before network managers, radio/NIC hot-plug, suspend/resume, failed setup, tamper refusal and offline updates. Perform these on a disposable Debian VM with no real keys. A committed installation must reject the development flag and all online paths. Never reconnect a real signer to perform release acceptance. See PERMANENT_AIRGAP.md.

Tor acceptance must cover missing-tool installation, administrator rejection,
repository verification failure, bootstrap failure, Tor loss during HTTPS and
sync, stop/restart with a changed preference, refused external-node adoption,
and the disable-Tor warning. Confirm no clearnet/DNS traffic from Core or curl
in a packet-captured disposable Debian environment; other apps and the disclosed
Tor installation bootstrap are outside the Tor-only application route.
