# Review notes — 1 November 2026

This is an implementation review, not an independent security audit or a
production-readiness certification. The app assumes a trusted OS and local
Bitcoin Core. Its controls do not protect against a compromised kernel or
another privileged process.

## Fixed boundaries

| Area | Change |
| --- | --- |
| Multisig signing keys | Import the original private descriptor with Core's checksum. Core's normalized `descriptor` field is public and must not replace the private import. Exports remain public. |
| Signing approval | Bind approval to the exact reviewed PSBT and unsigned transaction ID. Consume approval on a signing attempt; re-review after failure. |
| Signature modes | Accept ALL and Taproot DEFAULT. Reject NONE, SINGLE and ANYONECANPAY modes that allow changes beyond the reviewed transaction. |
| Wallet locking | Attempt to re-lock encrypted wallets on both successful and failed creation/signing paths, and report failure to confirm locking. |
| Offline startup | Disable P2P activity from process startup, disable wallet broadcasting, retain host-network/swap checks, and use a private process umask. |
| Downloads | Keep the upstream verifier unchanged, then independently count distinct valid pinned primary signing keys. Reject duplicate-signature inflation and releases older than the supported minimum. |
| Binary selection | Select the highest installed numeric release, excluding incomplete staging and backup directories. |
| Node reconnection | Recover from stale managed cookies, bound startup waits, and avoid starting an online node from an automatic stale-cookie check before Online Node is selected. |
| Local RPC | Retain loopback-only transport, disabled proxies and redirects, and bounded responses. Bound cookie reads and reject non-finite JSON numbers and malformed error objects. |
| Imported wallets | Reject private, unsolvable, non-ranged or duplicate descriptors before creating a watch-only wallet. Core performs descriptor validation, import and rescanning. |
| Addresses | Preserve the chosen cold-wallet address type; handle single-type online imports explicitly. Save verified-address labels in Core before updating local display records. |
| Input/display | Bound PSBT-file reads before loading their contents, share one bounded camera decoder, and render dynamic labels as plain text. |

## Simplification

QR encoding/rendering and camera scanning each have one implementation shared
by both wallet modes. Repeated signer-detail validation, a hidden wallet-type
selector, an unused protection-group handler, and the obsolete wallet-file
export path were removed. No new runtime dependency was introduced. Native
system fonts, compact recovery words, and optional protection/audit details
keep the desktop flow readable without adding another UI framework.

## Validation performed

- Compiled all Python source and checked the diff for whitespace errors.
- Checked the standard public BIP39 reference vector through Trezor's library.
- Exercised descriptor serialization with a simulated Core response that strips
  private keys; verified private imports and public exports stay distinct.
- Exercised rejection of private/duplicate wallet imports, altered PSBTs,
  reused signing approval, unsafe signature modes, non-finite RPC JSON, and
  repeated release signatures from the same primary key.
- Constructed the online and cold Qt screens with the pinned dependencies,
  checked confirmation of all 24 words, the 12-word default, passphrase controls,
  dice counting, and QR sizing; rendered and inspected the phrase/protection
  screens offscreen on Windows with public placeholder data.

The temporary review scripts and environment are outside the repository. Core
RPC behavior in these checks was simulated: real Linux Core creation, signing,
camera access, GPG release downloading, and network/swap restoration were not
exercised end to end in this environment.

## Follow-up validation: wallet setup

Verified and ran the actual Linux Core 32.1 archive under Ubuntu/WSL, requiring
the pinned signer threshold and archive checksum. Using only the public BIP39
zero-entropy reference phrase in isolated RAM directories with Core peer
networking disabled, checked native SegWit, Taproot, legacy and nested SegWit
creation, encryption, BIP39 passphrase derivation, fresh receive addresses and
retry after a partial wallet setup. Native SegWit matched the known BIP84
reference address. Every review Core process was stopped and its RAM directory
removed afterward; host networking and swap settings were not changed.

This exposed unused root-key descriptor entries without `active`/`internal`
fields. Both cold creation and online receiving now filter active entries
before using those fields. Failed setup wallets are unloaded and removed from
their private RAM directory before a retry; completed wallets are protected
from this reset. Setup errors identify the failing RPC with extended private
keys redacted.

UI checks also cover fixed pre-dice input commitments, recovery without a
second phrase-entry screen, one BIP39-passphrase entry on recovery, cleared
password fields and hidden online wallet actions until a wallet is loaded.
These follow-up checks do not establish end-to-end signing, camera access or
host network/swap restoration.

The displayed pre-dice commitment uses a separate domain from seed generation,
so it does not reveal the seed entropy when no dice are entered. The actual
wallet digest and OS bytes are fixed before dice entry and reused on Generate.

The entropy screen now additionally exposes a deliberately **secret** calculation
panel: actual OS-random bytes, the wallet-file hash, normalized live dice digits,
the actual combined SHA-256 and selected BIP39 entropy bytes. A short Python
command hashes the exact serialized input bytes, and a second command converts
the resulting entropy into words through Trezor's pinned library. Both commands
were checked against application output for all five supported word counts.
The v1 recipe is unchanged, and generation and audit serialization now share
one implementation in `entropy_material`. Anyone with these reproduction inputs can recover
the phrase, so they must be treated as a recovery backup and checked only on a
trusted offline computer. The panel is cleared after wallet creation, when
switching setup choices and on shutdown; Python/Qt memory erasure is not guaranteed.

## Remaining limits

- Python cannot guarantee erasure of seed strings. The separate signer process
  limits their lifetime but does not provide a trusted display, memory locking,
  or a sandbox against a compromised desktop. Core dumps are disabled. Other
  processes under the same user may be able to inspect Core depending on the
  OS ptrace policy; privileged attackers can inspect running processes.
- Forced process termination or power loss can interrupt cleanup/restoration.
  Host interfaces and swap may need manual restoration or a restart.
- The offline signer has no independent blockchain view. Displayed input
  amounts/fees depend on PSBT data checked by Core, not local chain validation.
- Pruned nodes cannot scan blocks they discarded. A scan timeout may leave an
  import still running in Core; do not assume a failed UI response rolled it back.
- QR transfer supports one static QR. Large multisig descriptors and PSBTs may
  require text or file transfer; animated QR protocols are not implemented.
- Dependency versions are pinned, but reproducible installers, dependency hash
  locking, signed app releases and a separate release-time security review
  remain packaging work. The development networking bypass is still present
  and must be removed or excluded from release builds.

## Primary references

- [Core getdescriptorinfo](https://bitcoincore.org/en/doc/32.0.0/rpc/util/getdescriptorinfo/): public normalization and the original input checksum.
- [Core walletprocesspsbt](https://bitcoincore.org/en/doc/32.0.0/rpc/wallet/walletprocesspsbt/): signing, signature modes and finalization controls.
