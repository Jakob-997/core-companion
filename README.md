# Core Companion

A small Linux desktop wallet interface built around Bitcoin Core. Qt Widgets
provides the screens; Core handles descriptors, key derivation, addresses,
ownership checks, wallet data, and PSBT review and signing. Trezor's reference
`python-mnemonic` provides BIP39 and the BIP32 master key.

**0.1.0rc1 is a release candidate for review. Independent security review and
Debian host-isolation acceptance are still required before a funds-bearing release.**

## Install on Debian

Use Python 3.11–3.15 and a normal desktop user. Do not run the app as root.

```sh
sudo apt update
sudo apt install -y python3-venv gnupg wget pkexec iproute2 util-linux zbar-tools libegl1 libxcb-cursor0
python3 install.py
./core-companion
```

The installer checks the pinned dependency wheel hashes and adds **Core
Companion** to the applications menu. Keep the application folder in place.
The private Python environment is managed inside it; no activation is needed.
Run the installer again after updating source or replacing a release folder.
It keeps an existing valid `.venv` and updates its pinned packages in place.
`python3 install.py --no-desktop` installs without changing the applications menu.

Linux x86-64 requires glibc 2.34+ (Debian 12+). ARM64 dependency wheels require
glibc 2.39+; that platform has not completed release acceptance. Cold signing
requires a RAM-backed `/dev/shm` and a graphical administrator authorization
agent. NetworkManager installations also need `nmcli` and `busctl`.

## Choose a wallet mode

- **Cold storage:** a separate, temporary Core process with private keys in RAM.
  Networking and system swap are disabled before it starts. Close other programs
  first; disabling swap on a low-memory machine can freeze the desktop.
- **Online node (watch-only):** connect to a local Core or start the app-managed
  node. Import the public wallet from your signer to view balances and history
  and generate receiving addresses. This mode has no private keys.

The welcome screen downloads and verifies Core when needed. It requires three
distinct valid signatures from eight pinned release-signing keys and verifies
the archive checksum using Core's unchanged upstream verifier. Keys are fetched
into a temporary GPG keyring; your own keyring is untouched. Cold mode requires
Core 32.1+. Downloading Core does not start blockchain networking.

The managed online node uses loopback RPC, automatic cookie authentication and
a 10,000 MiB pruning target. It keeps syncing after the interface closes. An
existing node in the standard Core directory is tried first. Only loaded
wallets with private keys disabled appear in the online view. A pruned node
cannot rescan discarded blocks when importing an older wallet.

## Cold signing and backups

Create or recover an English 12, 15, 18, 21 or 24-word BIP39 phrase. New phrases
default to 12 words, with all words confirmed. The requested entropy recipe
combines a temporary wallet.dat SHA-256, 32 bytes of OS randomness and optional
dice rolls. **Audit details**, collapsed by default, contains these secret
inputs, one reproducible SHA-256 command, and the exact starting entropy.
That command uses only Python's standard library. Anyone with its inputs can
recreate the phrase; inspect them only on a trusted offline computer.

An optional BIP39 passphrase changes the derived wallet. The separate **Encrypt
wallet** password protects only this session's temporary Core file. They are
different secrets. Python and Qt cannot guarantee erasure of secret memory.

For multisig, prepare your signer and share its BIP87 account key before adding
the other signers' keys and choosing a threshold. Core validates and imports
the P2WSH policy. The wizard supports 2–20 signers. Export the completed public
wallet as a QR or JSON backup; import that into the watch-only node.

**Closing the cold signer deletes its wallet, saved addresses and labels.**
Keep the recovery phrase, any BIP39 passphrase and address type. Multisig recovery
also requires the complete public wallet policy and enough signers' private
backups. A wallet encryption password alone cannot restore a wallet. The app
prompts before closing a session that contains recovery material or a wallet.

Scan a receiving address to check ownership, or import a PSBT from a static QR,
file or paste. Review every output and fee before signing. Core supplies the
decoded data and signatures; Companion never finalizes or broadcasts. An
offline signer cannot independently validate input amounts against the chain.
Large public exports and PSBTs can be saved to files when one QR is insufficient.

When closing normally, Core is stopped and RAM files removed before previous
swap/network settings are restored. Isolation is checked periodically and
before private-key operations. This is a desktop precaution, not protection
against a compromised OS. Forced termination or power loss can interrupt cleanup;
a restart or manual restoration may be necessary.

## Development

From a source checkout only:

```sh
./core-companion --dev-keep-network
```

This leaves host networking on, keeps Core peer networking off, still disables
swap and adds **Skip confirmation (testing)**. Use disposable wallets. The
release builder disables this flag in the packaged application.

## Review and release

[ARCHITECTURE.md](ARCHITECTURE.md) maps the boundaries and entropy construction.
[AUDIT.md](AUDIT.md) records checks and limitations. [RELEASE.md](RELEASE.md)
describes reproducible source packaging and the remaining release gates.
[SECURITY.md](SECURITY.md) describes the threat model and reporting guidance.

Not yet included: animated QR protocols, transaction creation/finalization/
broadcast, persistent cold wallet files, Windows cold isolation, signed app
updates or automatic Core updates. This release is a signer and watch-only
companion, not a complete replacement for an online spending wallet.

References: [Bitcoin Core](https://bitcoincore.org/en/download/),
[Trezor python-mnemonic](https://github.com/trezor/python-mnemonic),
[BIP39](https://github.com/bitcoin/bips/blob/master/bip-0039.mediawiki),
[BIP87](https://github.com/bitcoin/bips/blob/master/bip-0087.mediawiki).
