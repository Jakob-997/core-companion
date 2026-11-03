# Boundaries and implementation notes

## Core-first rule

Bitcoin Core is the wallet engine and source of truth. Use its RPCs for wallet
creation, key import and derivation, descriptor parsing/checksums/import,
addresses and ownership checks, balances and history, PSBT decoding/analysis/
signing, and watch-only export. Do not reimplement those operations in the
companion. Descriptor text assembly is only input serialization; Core validates
and imports the descriptors.

Companion-owned behavior is limited to the desktop flow and display, local RPC
transport, Linux cold-session isolation and cleanup, and the requested entropy
recipe. BIP39 phrase generation/recovery and conversion to the BIP32 root use
Trezor's `python-mnemonic`, because Core accepts an extended BIP32 key rather
than a BIP39 phrase. If Core already exposes an operation needed by the app,
call that RPC instead of adding parallel wallet logic.

## Source map

- `run.py`: cold-helper process isolation and early core-dump restrictions.
- `install.py`, `core-companion`: hash-locked dependency installation and the
  Linux desktop launcher. `tools/build_release.py` builds the source archive.
- `linux_cold.py`: permanent network policy verification and temporary swap disable/restore.
- `offline_core.py`: isolated Core lifecycle, BIP87 descriptors, address checks,
  watch-only export, and PSBT review/signing.
- `seed.py`: temporary-wallet hashing, entropy mixing, BIP39, and BIP32 root.
- `cold_ui.py`: cold-signer screens; it delegates key and wallet operations to
  `offline_core.py` and `seed.py`.
- `rpc.py`: loopback cookie-authenticated RPC client and the online method list.
- `wallet.py` and `ui.py`: watch-only node view; `ui.py` starts the cold helper.
- `core_download.py`: invokes Bitcoin Core's upstream release verifier and
  safely installs the verified Linux package.
- `qr.py` and `scanner.py`: shared QR rendering and bounded camera transport.
- `AUDIT.md`: review findings, checked boundaries, and remaining limitations.

## Runtime boundaries

```text
Online wallet view ──local cookie RPC──> existing Core or managed Core

Cold-session controller ──turn off interfaces and swap──> Linux host
       │
       └──short-lived helper──> isolated bitcoind ──cookie RPC──> tmpfs wallet
                                   loopback only
```

The online view reads wallet state from the user's existing node. Cold mode is
a separate process tree: it starts a second, isolated Bitcoin Core process with
its own data directory, wallet directory, cookie and log under `/dev/shm`. Its
P2P networking is disabled by Core options and `setnetworkactive false`; the
controller also disables non-loopback host links and swap before starting it.
The source-development `--dev-keep-network` flag skips host-link changes while
retaining Core's P2P shutdown and swap handling. Other programs can still use
the network in that mode. The release builder disables this command-line flag;
do not use development mode with wallets holding funds.
The UI helper starts in its own process group, disables core dumps and Linux
dumpability, then stops Core and removes its session directory before the
controller restores prior swap settings only; networking remains permanently disabled.

Host network/swap state is checked every two seconds by the controller. A failed
check stops the signer process group and invokes cleanup before restoring
settings. Core peer networking and host state are also checked before key
creation, derivation, PSBT review/signing and new address generation. Tools
requiring administrator authorization are resolved only in fixed system
directories. These checks detect changes; they are not a network namespace or
protection against privileged processes and cannot eliminate every race.

The helper passes private key data only over authenticated loopback RPC. The
companion hashes the closed temporary wallet file as bytes; it does not parse
or modify its database. No arbitrary RPC console is
exposed. The RPC method allowlist is an application guardrail, not a server-side
permission boundary: a compromised client with a Core cookie can bypass it.
Keep Core RPC bound to loopback and do not expose it to a network.

## Bitcoin Core download verification

The Linux download action obtains the current stable version from the official
download page and invokes the unchanged Bitcoin Core v32.1
`contrib/verify-binaries/verify.py`. It downloads eight pinned public signing
keys into a temporary GPG home, checks every full fingerprint against the
allowlist in `core_download.py`, and marks only those keys trusted in that
temporary home. The verifier checks the signed `SHA256SUMS` files from both
official hosts, requires at least three accepted signatures, downloads the
selected Linux archive, and checks its SHA-256 hash. The user's personal GPG
keyring is not modified. Companion additionally verifies the checksum signature
status directly with GPG, requiring three distinct non-expired, non-revoked
pinned primary signers. Repeated signature packets do not increase this count.
The pinned set was confirmed against Bitcoin Core
v32.1's official `SHA256SUMS.asc`; signer rotation requires a reviewed app
update. Only after verification succeeds does the app install the package. The extractor rejects
absolute or parent paths, links, special files and unexpectedly large members,
and stages files before placing the completed directory in the app's data
folder. The upstream verifier requires `gpg` and `wget`; it and its MIT license
are under `companion/vendor/bitcoin-core/`.

When Online Node is selected, Linux starts the verified Core binary in a
separate app-managed data directory under `~/.local/share/core-companion/`.
The node enables RPC only on loopback, uses its cookie from that data directory,
and starts with `-prune=10000`. It runs independently after the UI closes and
reconnects on the next app launch. Downloading Core does not start the node;
cold-signer setup therefore does not silently bring up online networking. If a
Core cookie exists in the standard user data directory, Companion tries that
node first. If that connection is stale or fails, selecting Online Node starts
its managed node. A stale connection record does not start online peer
networking before the user chooses Online Node. Managed startup waits are
bounded, and a stale managed cookie no longer causes an endless reconnect loop.

## Seed and key flow

1. Start an isolated Bitcoin Core 32.1+ process on mainnet with peer discovery,
   listening and outbound connections disabled. It uses a fresh, private
   directory on a verified tmpfs mount.
2. Create a throwaway descriptor wallet, unload it, and hash its closed
   `wallet.dat` with SHA-256.
3. Before user entropy entry, obtain 32 fresh bytes from the Linux system CSPRNG. Display
   actual OS bytes and wallet-file hash in the collapsed secret Audit details.
   Retain those same original inputs in signer memory. On
   Generate, combine those fixed inputs with the exact UTF-8 user input using the documented,
   length-prefixed domain-separated SHA-256 in `seed.py`; no new randomness is
   drawn after user entropy entry. Truncate only to the selected standard BIP39 size.
4. Encode the entropy and validate/recover English BIP39 words with Trezor's
   `python-mnemonic`. `to_seed()` applies the optional BIP39 passphrase;
   `to_hd_master_key()` produces the BIP32 root xprv. Bitcoin Core imports that
   root with `addhdkey` and owns all child-key and descriptor derivation.
5. For multisig, Core derives the local signer account at
   `m/87h/0h/0h` first. The UI shares its public account key before asking for
   other signers, and clears the phrase/passphrase fields. Once the other keys
   are collected, the app builds receive and change `wsh(sortedmulti(...))`
   descriptors with full key origins, asks Core to checksum and import them,
   then checks that Core recognizes the first receive address as its own.
6. On close, stop Core, remove its tmpfs session directory, and restore the
   previous swap state only. Networking is never re-enabled. Python does not guarantee erasure of secret
   strings from process memory. The helper isolation reduces exposure but does
   not make this a reviewed or production-secure signer.

Completed wallets require Core file encryption. Core backupwallet writes a
consistent backup, permissions are set to 0600, and an atomic rename replaces
the previous wallet.dat. Public metadata is saved separately with atomic writes
and directory fsync. A held flock prevents simultaneous writers. The app backs
up after setup, address generation, label/status changes and before switching
or closing. On reopen it copies the encrypted backup into the private tmpfs
wallet directory and asks Core to load it locked. The throwaway entropy wallet
never enters this persistent storage.

Public exports combine the exact receive/change pair into /<0;1>/* only after
Core confirms expansion reproduces both original canonical descriptors. Core
also supplies the checksum. QR/text export carries that plain descriptor.
The importer accepts this form, pairs, xpubs, zpubs and ypubs. Only public-key
version conversion is local; Base58Check is verified and Core validates and
expands descriptors before wallet creation. Pruned-away history cannot be
recovered by a rescan.

BIP39's checksum does not always identify a unique final word. For a partial
phrase, the recovery screen displays the checksum-valid candidates and asks the
user to match the backup. The checksum detects errors; it is not proof that a
phrase is the intended one.

## PSBT signing boundary

The cold helper accepts a base64 PSBT from a file, paste, or one QR code decoded
by the system `zbarcam` utility. Core enriches and decodes it without signing.
The UI displays every output, the fee, and outputs Core identifies as change.
Signing is a separate user action. The Core wrapper remembers the exact PSBT
approved by review and rejects non-ALL/non-DEFAULT input signature modes. For
PSBTv0 it compares Core's unsigned transaction ID before and after signing.
Core 32.1 decodes PSBTv2 without reconstructing a `tx` object. For that format,
the wrapper checks every decoded input/output, and makes a domain-separated
SHA-256 review ID from transaction version, fallback locktime, modification
flags, previous outpoints, sequences, required input locktimes, and exact output
amounts/scripts. The UI calls this a **Review ID**, never a transaction ID. The
same fields must match after `walletprocesspsbt`. Transaction serialization and
signatures are entirely delegated to Core. Core does not finalize
or broadcast it. The cold process has no blockchain, so input values and the
fee displayed from PSBT data are not independently verified against chain
state; confirm them using the online node or another trusted source. A QR that
is too large for one standard code must be saved as a PSBT file; animated
UR/BBQr transport is not implemented.

The screen uses the same Core process and wallet as the signer, so the UI is not
an independent trusted display. Verify transaction details using a second,
trusted source before signing.

## Dependencies and review

The desktop app uses PySide6 Qt Widgets. The cold helper adds Trezor's
`python-mnemonic` for BIP39 and BIP32 master-key creation and `qrcode` for QR
encoding. It uses installed Linux tools for privilege prompts, swap, links and
optional camera scanning. Core is downloaded and verified separately and is not bundled.
Direct and transitive Python dependencies are pinned with official wheel
hashes, installed without dependency resolution, and checked afterward. Review
upstream advisories and the supported Core version whenever the app is packaged
or updated. [RELEASE.md](RELEASE.md) describes reproducible source packaging and
the separate owner-signing/independent-review gates.

The largest remaining engineering risks are lifecycle cleanup after forced
termination, system-specific network management, Core RPC compatibility,
descriptor interoperability, PSBT display and signing review, and packaging.
Do not treat a small codebase or Core-backed operations as a substitute for an
independent security review.

The new storage.py owns atomic encrypted Core backups and a single-writer file lock. public_wallet.py owns public-key version conversion and Core-validated multipath interchange. The online send path delegates funding, decoding, finalization, mempool checks and explicitly approved broadcast to Core. PSBTv0 is requested for broad external-signer compatibility.

## Permanent offline commitment (supersedes session-only network restoration)

Normal mode installs the root-owned boot firewall/radio/link policy and timer in
PERMANENT_AIRGAP.md. linux_cold.NetworkSession now verifies that policy and has
no network restoration or enable method. ColdSystemSession.restore restores
swap only. permanent_airgap.py checks per-boot fresh root success, exact policy
files, masks, timer and current links/radios before private operations. The app
locks online paths and startup connections once committed. The development flag
cannot bypass an existing machine-wide commitment. Installer and Core downloader
also enforce offline operation. Hardware removal remains the strongest safeguard.
