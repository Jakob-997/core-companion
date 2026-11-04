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
These wallet-setup checks did not establish end-to-end signing, camera access or
host network/swap restoration.

The wallet digest and OS bytes are fixed before dice entry and reused on
Generate. The collapsed secret Audit details contains only three labeled
inputs (actual OS RNG bytes, wallet.dat SHA-256, normalized live dice rolls),
one SHA-256 command that combines them using the unchanged v1 recipe, and the
resulting starting entropy. The command prints the selected entropy length
and was checked against the application's entropy for every supported word
count. BIP39 word-conversion commands and redundant commitment displays were
removed. Generation and audit serialization remain independently checked.

Anyone with these reproduction inputs can recover the phrase. They must be
treated as a recovery backup and checked only on a trusted offline computer.
The panel is cleared after wallet creation, when switching setup choices and
on shutdown; Python/Qt memory erasure is not guaranteed.

## Release-candidate pass

- Fixed the multisig exchange dead end: prepare the local signer, share its
  public BIP87 key, then collect cosigner keys and finish the policy. Clear the
  phrase and initial password fields after preparation; encrypted completion
  asks for the wallet-file password again without re-deriving the seed.
- Added a closing/backup prompt and public JSON policy export, including when
  the payload exceeds a single QR. Cold labels and address indexes remain
  temporary; the interface and documentation now state that clearly.
- Resolve privileged tools through fixed system directories. Recheck host
  isolation periodically and before sensitive operations. Preserve restoration
  state after failure and refuse a new session until cleanup succeeds.
- Make Core installation rollback work for cancellation and keyboard interrupts,
  and sanitize the verifier subprocess tool path. Fault-injection checks cover
  interruptions before and after each replacement rename and during extraction.
- Support Core 32.1's default PSBTv2 decoding through a separate review ID over
  Core-decoded transaction fields. No Bitcoin transaction serializer was added.
  V0 continues to use Core's unsigned txid.
- Refresh online balances/history as well as blockchain progress, clear old
  receiving QRs when changing wallets, and keep wallet-operation failures from
  incorrectly changing the connection indicator. Wallet names share validation
  between cold setup and public import.
- Scroll long signing/export screens, improve dark-mode primary-button contrast,
  use system fixed-width fonts and replace placeholder hover help with actual
  explanations, including dynamically added controls.
- Add a normal Linux desktop launcher/installer, a complete dependency wheel
  hash lock, Qt 6.11.3, version metadata and deterministic source packaging.
  The packaged application rejects the source-only networking testing flag.

Actual verified Core 32.1 validation under Ubuntu/WSL now includes encrypted
2-of-3 BIP87 preparation/sharing/completion, duplicate signer rejection,
retrying wrong passwords, public exports, fresh addresses, and actual partial
signature creation for PSBTv0 and PSBTv2. Checks reject changed payloads, replayed
approvals, unsafe signature modes, changes after signing, malformed v2 fields,
fractional-satoshi outputs, and changed isolation state; encrypted wallets are
relocked. Synthetic public-fixture UTXOs were used, with no funds or broadcasting.
Host swap inspection was simulated for these fixtures; actual peer-network
flags were checked. The earlier single-signature address-type checks also pass.

The actual exported multisig policy was imported through `WalletService` into
a Core wallet with private keys disabled. Its first receiving address matched
the cold signer's first address exactly; public descriptors, labels and wallet
snapshots were also checked. Linux Qt 6.11.3 screens were exercised and visually
inspected at 980×680 and 1280×850 in both themes, including staged multisig,
PSBTv0/v2 review/sign UI integration, backups, help and signed-QR scrolling.

The release source tar was byte-identical when built with Windows Python and
Linux Python. Its file-hash manifest passed, the packaged CLI rejected the
development flag, and a fresh installation of the extracted package on Linux
checked dependency hashes, imported the libraries, created a valid desktop
entry and opened/exited the app. Actual desktop-entry launches using inert
fixtures covered spaces, quotes, dollar signs, backticks and backslashes in
paths. Unsupported percent/control-character desktop paths are rejected early.

Temporary scripts remain outside the repository as requested. These are
engineering checks, not an independent audit. Camera capture, actual Debian
privilege prompts and network/swap changes/restoration still need VM acceptance.

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
- Dependency wheel hashes and reproducible source packaging are implemented.
  Signed app releases, full Debian acceptance, a redistribution license and
  independent review remain release gates. The source networking bypass is
  disabled by the release builder; binary/installer reproducibility beyond
  the source archive and locked wheels is not claimed.

## Primary references

- [Core getdescriptorinfo](https://bitcoincore.org/en/doc/32.0.0/rpc/util/getdescriptorinfo/): public normalization and the original input checksum.
- [Core walletprocesspsbt](https://bitcoincore.org/en/doc/32.0.0/rpc/wallet/walletprocesspsbt/): signing, signature modes and finalization controls.

## November 3 native app review update

The previous RAM-only wallet lifetime described in historical notes is superseded.
Completed cold wallets now use encrypted Core backups with atomic replacement,
0600 permissions and a single-writer lock. Public metadata is separate and is
not encrypted. Reopening restores a locked working copy in tmpfs. The entropy
generator wallet remains disposable. Backup or close failure keeps the signer
open for retry.

The entropy domain is now v2: user input is exact UTF-8, including whitespace.
The audit command contains only hex literals and reproduces the full SHA-256;
the selected first 16/20/24/28/32 bytes are the BIP39 phrase entropy.

Disposable real Core 32.1 checks cover encrypted backup/reopen, labels and
address index continuity; receive/change multipath import/export; matching
xpub/zpub addresses; watch-only funding; unsigned PSBTv0 export; the signed
return, finalization and mempool check; and explicit broadcast. The broadcast
exercise uses a disposable regtest node. No host networking or swap settings
are changed by these harnesses. The production application stays on mainnet.

Native UI fixture checks cover 12/24-word vertical confirmation order, the
exact audit command with arbitrary UTF-8 and shell punctuation, default-hidden
BIP39 fields, the then-mandatory file encryption, the Send page, removed
cold-signer online tool and LifeHash color/determinism. LifeHash passes its
upstream RGB reference vector. These review scripts remain outside the
application repo. The encryption requirement was later removed; see the
November 3 update below.

This implementation work does not replace independent security review or a
full Debian camera, desktop authorization and isolation acceptance pass.

Additional checks exercise the actual Qt-to-Core save/switch/reopen path, preserved used labels, address removal without key loss, backup failure preventing close/switch, and reopening after a Core restart. At that point, encrypted multisig reopening, rejection of plaintext backups and concurrent writers also passed. The plaintext-backup rejection is superseded by the November 3 update below. All main native pages fit 980×680 in both themes; a signed-transaction dialog opens without an implicit default broadcast button. Camera hardware and GNOME integration remain manual VM acceptance items.

## Permanent air-gap correction

Historical references to restoring networking are superseded. Networking is now
permanently disabled in normal cold mode, with root-owned boot enforcement and
a repeating guard. All network-enable/restore code was removed from NetworkSession.
A per-user commitment plus system policy detection blocks online startup,
online mode, Core downloads and source-development bypasses. The installer uses
no-index offline resolution on committed computers. Explicit warnings prohibit
reconnecting real signers and recommend removing networking hardware.

Kernel namespace tests pass for IPv4/IPv6 and established traffic blocking,
loopback RPC, ARP default drop, idempotent loading and repair after policy/rule/
dormancy changes. Guard/GUI tests pass for stale and wrong-boot status, changed
files, missing masks, inactive timers, unblocked radios, active interfaces,
failed setup keeping the commitment, online/download/CLI blocking and offline
installer argv. Root script syntax and systemd service/timer verification pass.
No permanent policy, service or radio setting was installed on the review host.
Real Debian boot/reboot, authorization and hardware acceptance remain pending;
software checks are not a physical air-gap guarantee.


## Tor-only online routing (2026-11-03)

The Welcome screen now offers Tor before any node startup or Bitcoin download.
It is the default choice, persists in settings and can be disabled only after
an IP-exposure warning (Cancel is the default). Missing Tor/curl offers a signed
apt installation with an explicit direct-bootstrap disclosure and administrator
authorization. Failed install/bootstrap never selects a direct route.

No Python dependencies were added. A private system-Tor process owns onion
routing; curl owns HTTPS/SOCKS and remote hostname resolution; Core owns Bitcoin
P2P. The unchanged upstream release verifier now operates locally in bin mode.
All metadata, pinned signing keys and archive transfers share the selected
transport. Automatic GPG key retrieval is disabled. The three distinct pinned signer threshold and archive checks remain mandatory.

Validation evidence:

- Real Core 32.1 accepted the exact Tor-only flags in an isolated network
  namespace, confirmed the required proxy and limited networks via local RPC,
  advertised no listening address and had no peers with its proxy absent.
- Extracted distro Tor 0.4.9.11 accepted the exact launch configuration and
  bootstrapped to 100% as an unprivileged private review client. Core's official
  release page, pinned keys and checksum/signature files were fetched through
  it; four distinct pinned release signatures verified for 32.1.
- Real curl against a local SOCKS fixture sent the unresolved destination
  hostname despite NO_PROXY=* and failed when the proxy refused the connection.
- Qt fault fixtures cover no automatic startup, bootstrap gating, missing-tool
  prompts, both apt stages/authentication flags, installation failure, refusal
  of the disable-Tor warning, transport propagation to downloads and local-only
  GPG imports, Tor-loss cancellation and permanent-cold rejection. Initial
  fixtures ran on Linux; the extended UI/installer fixtures also passed in the
  existing Windows Qt 6.11.3 environment with Linux/tool calls mocked. The Linux
  review VM subsequently failed to restart; no VM reset was performed.
- Welcome fits 980x680 and 1280x850; the compact status panel and privacy choice
  were visually checked with a native review font. No installer/service was
  actually installed on the review host and no real wallet keys were used.

Still required: actual Debian administrator/apt acceptance, packet capture
through Tor loss/restart, long-running onion-peer synchronization and the
existing independent security/release review. This is application-level Tor
routing, not a machine-wide Tor gateway or an anonymity guarantee. Committed
cold machines refuse Tor and apt installation; their policy also masks Tor's
system services.

Primary references: [Core 32.1 Tor support](https://github.com/bitcoin/bitcoin/blob/v32.1/doc/tor.md),
[curl proxy and configuration semantics](https://curl.se/docs/manpage.html),
and [Debian Tor manual](https://manpages.debian.org/trixie/tor/tor.1.en.html).


## Multisig origin compatibility (2026-11-03)

Removed the BIP87-only cosigner filter. Inputs must contain a mainnet account
xpub and origin, but no purpose/coin/account path is mandated. Core's
getdescriptorinfo validates a ranged public wrapper and supplies the canonical
key expression. Malformed/private/non-ranged/unsolvable results are rejected.
The wizard still applies its receive/change suffixes and checks the final
private/public multisig descriptors through Core.

The local signer uses the fixed BIP87 path (`m/87h/0h/0h`); the UI does not ask
users to choose its path. Other signers' supplied xpub origin paths remain
flexible, including BIP48, BIP87, custom and root origins, and Core validates
them. Duplicate xpub rejection, private imports and public-only exports remain
in place.

Earlier fixture checks covered BIP48/BIP87/custom/root origins, apostrophe
notation, Core rejection propagation, malformed responses, duplicated xpubs
under changed origins, duplicated local keys, mixed-policy receive/change
construction, and private/public separation. They also exercised a now-removed
editable local path. Those historical checks are not a verification of this
change. No real keys or node were used. The previously failed Linux review VM
remains unavailable, so a real-Core mixed-path creation/signing acceptance run
remains required; this validation does not claim it was performed.

Origin information is supplied metadata, not cryptographic proof of another
signer's seed/path. [BIP380](https://github.com/bitcoin/bips/blob/master/bip-0380.mediawiki)
defines the general origin/key syntax; no BIP87 restriction is implied by it.


## Optional wallet-file encryption (2026-11-03)

Wallet-file encryption is now an option during setup, recommended and enabled
by default. If disabled, Core saves an unencrypted wallet backup; the app marks
its status, warns that the file contains usable private keys, and allows it to
be saved and reopened without a wallet password. Core's `unlocked_until` state
is checked against the recorded status. Backups remain mode 0600 in a mode
0700 application directory with atomic replacement. Use full-disk encryption
and physical protection when choosing an unencrypted wallet file.

Earlier checks that required or rejected plaintext backups describe the
previous behavior and are not evidence for the optional flow. A local
mock-RPC smoke check passed save/reopen metadata handling for both encryption
states. A live Core save/reopen check remains pending; the Debian VM was left
untouched after finding a saved wallet on it. Use a disposable VM with no saved
keys for that acceptance run. The temporary smoke script was removed.


## Close controls (2026-11-03)

Added an explicit Close control to the online window, cold-signer window and
modal dialog headers. Each routes through the existing close/reject handlers,
preserving wallet save prompts and Core/Tor shutdown behavior. An offscreen Qt
smoke check confirmed the controls are visible and close each window; cold Core
startup was stubbed for the UI check.


## Single-window navigation (2026-11-03)

Moved Bitcoin Core connection and network privacy settings into pages in the
online application window. Settings now return to Tools, and connection uses
the global Back control. The cold signer remains a separate process to keep
seed handling and temporary Core outside the online application process. The
online shell stays visible while that helper starts, then hides immediately
before the signer window appears; closing the signer restores the prior page.
Startup failures are reported by the online shell without displaying a helper
error window over it.

This provides one visible application window at a time; it does not make the
online shell and the isolated signer the same native window. Standard operating
system prompts and confirmation dialogs can still appear as dialogs. Connection
and privacy page navigation received an offscreen Qt smoke check. The cold
helper handoff and live Core startup were not exercised on a Linux host; the
Debian VM remains untouched because it contains a saved wallet.


## Deferred node startup and address-use defaults (2026-11-03)

The welcome screen can download and verify Bitcoin Core without launching the
node. Online node startup and RPC connection now require choosing Online Node
and continuing; connection controls route back to mode selection until then.
A verified download remains stopped unless the user already continued into
Online Node, in which case it completes the requested startup. Cold storage
does not download or sync the blockchain. It still uses a short-lived,
peer-disabled Core process for wallet operations.

New receive addresses start marked used in both the online receive flow and the
cold signer address list. This is an app tracking label, not a claim that
Bitcoin Core observed an on-chain payment. Users can still change the marker.


## Recovery phrase entry layout (2026-11-03)

Recovery uses individually numbered word fields arranged in the same column
order as the generated phrase display. The grid follows the selected BIP39
length, preserves already entered words when the length changes, and retains
the checksum-based final-word recovery flow. Only the final field may be left
blank for checksum candidates.


## Welcome connection check and deferred networking (2026-11-03)

Welcome inspects local Core files without initiating network activity. An
explicit user action may issue the read-only `getnetworkinfo` RPC to an
already-running Core at loopback; it never launches Core, Tor, peers or sync.
That result includes the existing node's peer-network state and count, so an
already-online external Core is reported as such rather than described as
offline. If no local cookie is present, the UI says no local connection was
found and leaves Core stopped.

The Tor SOCKS port is now selected when Tor is explicitly started, not during
application construction. Core release download remains a separate explicit
action and follows the selected Tor setting. A successful download stops Tor
unless Online Node was already requested; Online Node starts Core and sync only
after mode selection. The verified Core binary is shared by the Online Node
and peer-disabled cold signer paths. This UI flow does not prove the host has
no physical network hardware or that unrelated processes are offline.


## Cold signer launch repair (2026-11-03)

The `companion/cold_ui.py` file on the prior main revision contained binary
data instead of Python source. The online shell could launch, but the isolated
cold helper could not import its interface. Restored the valid source module
and added parent-window reporting for cold-helper startup failures, including
the Core startup error when available. Python syntax compilation succeeded for
the cold UI, main UI, and entry point. The Debian VM inspection was read-only;
no wallet, node, networking, or swap settings were changed.
