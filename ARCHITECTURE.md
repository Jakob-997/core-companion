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
- `linux_cold.py`: host network and swap state changes and restoration.
- `offline_core.py`: isolated Core lifecycle, BIP87 descriptors, address checks,
  watch-only export, and PSBT review/signing.
- `seed.py`: temporary-wallet hashing, entropy mixing, BIP39, and BIP32 root.
- `cold_ui.py`: cold-signer screens; it delegates key and wallet operations to
  `offline_core.py` and `seed.py`.
- `rpc.py`: loopback cookie-authenticated RPC client and the online method list.
- `wallet.py` and `ui.py`: watch-only node view; `ui.py` starts the cold helper.
- `core_download.py`: invokes Bitcoin Core's upstream release verifier and
  safely installs the verified Linux package.

## Runtime boundaries

```text
Online wallet view ──local cookie RPC──> the user's existing Bitcoin Core

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
The development-only `--dev-keep-network` flag skips host-link changes while
retaining Core's P2P shutdown and swap handling. Other programs can still use
the network in that mode. Do not include this bypass in release builds or use
it with wallets holding funds.
The UI helper starts in its own process group, disables core dumps and Linux
dumpability, then stops Core and removes its session directory before the
controller restores the prior host settings.

The helper passes private key data only over authenticated loopback RPC. No
wallet database is opened by companion code. No arbitrary RPC console is
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
keyring is not modified. The pinned set was confirmed against Bitcoin Core
v32.1's official `SHA256SUMS.asc`; signer rotation requires a reviewed app
update. Only after verification succeeds does the app install the package. The extractor rejects
absolute or parent paths, links, special files and unexpectedly large members,
and stages files before placing the completed directory in the app's data
folder. The upstream verifier requires `gpg` and `wget`; it and its MIT license
are under `companion/vendor/bitcoin-core/`.

## Seed and key flow

1. Start an isolated Bitcoin Core 32.1+ process on mainnet with peer discovery,
   listening and outbound connections disabled. It uses a fresh, private
   directory on a verified tmpfs mount.
2. Create a throwaway descriptor wallet, unload it, and hash its closed
   `wallet.dat` with SHA-256. The displayed fingerprint is that file hash.
3. On Generate, obtain 32 fresh bytes from the Linux system CSPRNG and combine
   them with the wallet digest and optional dice digits using the documented,
   length-prefixed domain-separated SHA-256 in `seed.py`. Truncate only to a
   standard BIP39 entropy size selected by the user.
4. Encode the entropy and validate/recover English BIP39 words with Trezor's
   `python-mnemonic`. `to_seed()` applies the optional BIP39 passphrase;
   `to_hd_master_key()` produces the BIP32 root xprv. Bitcoin Core imports that
   root with `addhdkey` and owns all child-key and descriptor derivation.
5. For multisig, Core derives each local signer account at
   `m/87h/0h/0h`. The app builds receive and change `wsh(sortedmulti(...))`
   descriptors with full key origins, asks Core to checksum and import them,
   then checks that Core recognizes the first receive address as its own.
6. On close, stop Core, remove its tmpfs session directory, and restore the
   previous swap and link states. Python does not guarantee erasure of secret
   strings from process memory. The helper isolation reduces exposure but does
   not make this a reviewed or production-secure signer.

Before closing, the user can ask Core to export a watch-only wallet file to a
chosen destination. Core removes private keys from this export; it includes
public descriptors and address/transaction data. Restore that file in Bitcoin
Core on the online node.

BIP39's checksum does not always identify a unique final word. For a partial
phrase, the recovery screen displays the checksum-valid candidates and asks the
user to match the backup. The checksum detects errors; it is not proof that a
phrase is the intended one.

## PSBT signing boundary

The cold helper accepts a base64 PSBT from a file, paste, or one QR code decoded
by the system `zbarcam` utility. Core enriches and decodes it without signing.
The UI displays every output, the fee, and outputs Core identifies as change.
Signing is a separate user action. Before signing, the helper checks that the
unsigned transaction ID still matches the reviewed one, calls
`walletprocesspsbt`, and checks the transaction ID again. Core does not finalize
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
optional camera scanning. Core is selected by the user and is not bundled.
Review the exact pinned dependencies and the supported Core version whenever
the app is packaged or updated.

The largest remaining engineering risks are lifecycle cleanup after forced
termination, system-specific network management, Core RPC compatibility,
descriptor interoperability, PSBT display and signing review, and packaging.
Do not treat a small codebase or Core-backed operations as a substitute for an
independent security review.
