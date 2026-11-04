# Security model

Core Companion assumes a trusted Linux installation, trusted application and
dependency files, and a verified Bitcoin Core binary. It does not protect
against a compromised OS, root, hostile firmware, or a malicious desktop session.
It has no telemetry, analytics service, remote wallet backend or automatic app
updater. Downloads contact Core's official sites, its pinned-key keyserver and
PyPI during installation. The online Core node communicates with Bitcoin peers.

The online UI uses local cookie-authenticated RPC and offers watch-only wallets.
Cold keys are used in a separate helper and an isolated Core directory on tmpfs. Completed wallets are persisted only as Core-encrypted backups. Labels, public descriptors and wallet names are readable metadata. The saved wallet opens locked; encryption passwords are not stored. The entropy-source wallet remains RAM-only and is removed after hashing.
The helper disables dumps; host swap and non-loopback network interfaces are
disabled before normal cold use. Normal cold mode now commits to a persistent machine-wide offline policy; networking is never restored by the app. Periodic checks stop the signer if isolation changes; they cannot prevent every race or privileged change. Source development
mode intentionally leaves host networking on and is unsuitable for valuable keys.

RPC method lists restrict accidental application behavior. They are not a
server-side permission boundary against anyone who already has a Core cookie.
Python/Qt cannot guarantee memory erasure. Session closure, crash cleanup,
offline PSBT amount verification and multisig backup requirements deserve
particular review; see [ARCHITECTURE.md](ARCHITECTURE.md) and [AUDIT.md](AUDIT.md).

Report vulnerabilities privately to the repository owner before opening a
public issue. Include a minimal reproduction using public test vectors or
disposable wallets, the source commit, Core version and Linux distribution.
Never attach recovery words, passphrases, entropy audit values, private
descriptors, RPC cookies or real wallet files. No response-time or security
certification promise is implied by this development repository.

The online send path delegates funding, decoding, finalization, mempool checks and broadcasting to Core. Broadcast requires a separate explicit review action. Public-key version conversion (SLIP132) is transport handling only; the app does not derive public keys outside Core. LifeHash is a visual recognition aid, never a wallet ownership or policy check.

Permanent-mode details and physical-air-gap limits are in [PERMANENT_AIRGAP.md](PERMANENT_AIRGAP.md). Never reconnect a real signer. Physically remove networking hardware for the strongest safeguard. Software cannot guarantee isolation from compromised administrators or firmware.

Tor-only mode uses Core's native proxy/onlynet controls and curl's explicit
SOCKS5 hostname proxy for every Bitcoin-related HTTPS request. Automatic GPG
key retrieval is disabled; the upstream verifier runs locally. It has no direct
fallback. Tor is a network-privacy option, not an anonymity guarantee: local
RPC stays on loopback, and other apps/external nodes are outside its scope.
Installing missing Tor/curl is a disclosed direct bootstrap using authenticated
distro repositories. Dependency installation through pip is a separate installer
step, not routed by the app's Tor preference. A committed cold computer blocks
all Tor/install paths and must never be reconnected.
