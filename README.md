# Core Companion

A Linux-first desktop interface around Bitcoin Core. The online wallet view
connects to an existing local Core node. Cold signer mode starts a separate,
temporary Core process; it does not share the online node's wallet or data
directory.

This is an early development build, not a reviewed wallet release. Do not use it
to protect funds you cannot afford to lose.

## Run on Linux

Install Python 3.11+ and the pinned Python dependencies:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

For the existing-node view, start Core with local RPC enabled. Companion finds
Core's local connection automatically; there is no file path to set up. It reads
Core's private local credential for each request and refuses redirects. Only
already-loaded wallets with private keys disabled appear in the online view.

On Linux x86-64 and ARM64, **Download & verify Bitcoin Core** downloads the
current stable release, verifies the signed checksum file and archive using
Bitcoin Core's upstream verifier, then installs the verified package under
`~/.local/share/core-companion/bitcoin-core/`. The app automatically downloads
eight pinned release-signing keys into a temporary GPG keyring, checks their
full fingerprints, and requires three valid signatures. It never changes the
user's GPG keyring. The fingerprints are listed in `core_download.py` and were
confirmed as signers of Bitcoin Core v32.1's official `SHA256SUMS.asc`. Key
rotation requires an app update. GPG and wget are required; on Debian, install them with
`sudo apt install gnupg wget`. If verification fails, Core is not installed.
The verified `bitcoind` is suggested for cold-signer setup; the user still
starts Core for the online node view.

The cold signer button is under **Tools**. Select the installed `bitcoind`
executable. Cold mode requires Linux, Core 32.1+, a RAM-backed `/dev/shm`,
`pkexec`, `iproute2`, and the system swap tools. If NetworkManager is installed,
`nmcli` and `busctl` are used to turn it off and restore its prior setting.
Camera scanning additionally needs the Linux `zbarcam` utility, commonly
provided by `zbar-tools`.

Cold mode turns off all non-loopback network links and system swap. Close other
programs first; on a low-memory computer, disabling swap can freeze the
desktop. The app stops its temporary Core process, removes session files from
tmpfs, then restores the previous network and swap state when the cold window
closes normally. If the app is force-stopped, some network links or swap may
remain disabled until they are restored manually or the computer is restarted.

For development only, `python run.py --dev-keep-network` leaves host networking
enabled while exercising the cold-signer flow. Bitcoin Core peer networking
remains disabled, and system swap is still turned off. This bypass weakens the
host isolation: other programs can still access the network. Use test wallets
only. Remove this flag before preparing any release build.

## Included in this scaffold

- Existing-node wallet view: balances, history, receiving addresses, labels,
  address generation and Core PSBT inspection.
- Short-lived cold Core session with its own mainnet wallet in tmpfs.
- New English BIP39 phrases based on a SHA-256 temporary `wallet.dat` digest,
  fresh Linux system randomness and optional dice rolls.
- BIP39 phrase recovery for 12, 15, 18, 21 or 24 words, with checksum-valid
  final-word choices when only a partial phrase is entered.
- Optional BIP39 passphrase and separate temporary Core wallet-file encryption.
- Single-signature wallet creation or recovery using Core descriptors.
- BIP87 P2WSH multisig descriptor creation, with signer labels, account xpub
  origins, threshold selection and Core address ownership verification.
- PSBT import from file or one base64 QR, Core-backed output and fee review,
  signing, and signed PSBT export. It never finalizes or broadcasts.
- QR display for the receive address or local BIP87 signer key, with scanning
  for other signers' BIP87 keys.
- Receive-address QR/paste verification using Core's wallet ownership check.
- Core-generated watch-only wallet export for restoring on the online node.

## Not included yet

- Animated UR/BBQr, multi-frame QR scanning or a camera embedded in the app.
- Full wallet-policy/descriptor QR scanning and an online-node import wizard.
- Full PSBT review parity with a hardware wallet, finalization, broadcasting,
  fee policy controls or coin selection.
- Automatic Core updates after installation, installers or reproducible app
  release builds.
- Windows cold signer. The existing-node desktop view may run elsewhere, but
  host isolation and cold signing are Linux-only for now.

## Key handling notes

The BIP39 phrase is processed inside a short-lived helper. Trezor's
`python-mnemonic` creates the 64-byte BIP39 seed and BIP32 master xprv; Core
derives child keys and descriptors. The helper's core dumps are disabled and it
is made non-dumpable on Linux, but Python and Qt cannot promise that secret
bytes are erased from RAM. The `wallet.dat` fingerprint is not itself the BIP39
phrase or master key.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the process boundaries, entropy
construction and PSBT review sequence.

## Dependencies

The Linux Core download and verification action also uses the system `gpg` and
`wget` commands. On Debian, install them with `sudo apt install gnupg wget`.

```text
PySide6-Essentials==6.10.2
mnemonic==0.21
qrcode==8.2
```

References: [Bitcoin Core download and verification](https://bitcoincore.org/en/download/),
[Core RPC documentation](https://bitcoincore.org/en/doc/32.0.0/),
[Trezor python-mnemonic](https://github.com/trezor/python-mnemonic),
[BIP39](https://github.com/bitcoin/bips/blob/master/bip-0039.mediawiki),
[BIP87](https://github.com/bitcoin/bips/blob/master/bip-0087.mediawiki), and
[zbarcam](https://manpages.debian.org/testing/zbar-tools/zbarcam.1.en.html).
