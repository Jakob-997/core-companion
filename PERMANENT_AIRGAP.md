# Permanent cold installation

**Never reconnect a computer after using it for a real wallet. Closing the
wallet, deleting files, or restarting Linux does not make reconnection safe.
For the strongest safeguard, physically remove Wi-Fi, Ethernet, Bluetooth and
other network hardware. A VM testing flag must never be used with real keys.**

Normal cold setup is a machine-wide commitment, not a temporary session setting.
The acknowledgement screen explains that networking remains disabled across
closing, switching wallets and rebooting. There is no online-mode conversion
or network restoration control in the application.

## Linux enforcement

The supported target is a Debian/systemd desktop. Install nftables, rfkill,
iproute2 and pkexec before committing the computer; transfer these from trusted
offline media if real keys have already been present.

After acknowledgement, the app writes a durable cold-mode marker before
requesting administrator authorization. It installs these root-owned files:

- /etc/core-companion/airgap.nft
- /usr/local/libexec/core-companion-airgap
- /etc/systemd/system/core-companion-airgap.service
- /etc/systemd/system/core-companion-airgap.timer

The service runs before network-pre.target at boot. It applies an atomic
default-drop IPv4/IPv6 input/output/forward policy, allows loopback RPC only,
blocks ARP, blocks radios and takes every non-loopback interface down.
Network managers, supplicants, Bluetooth and competing firewall services are
persistently masked. The timer reapplies protection after hot-plug or changes.
Only this app's nft tables are flushed; no general flush-ruleset is used.

The app checks exact installed policy contents and root ownership, masks,
enabled boot units, the active timer, interface/radio state and a fresh
root-owned success record tied to the current boot and boot uptime.
Unverifiable, stale, modified or inactive protection prevents private-key
operations. Runtime failure stops the signer process tree. Failed setup never
reenables networking or clears the cold commitment.

Core still uses its own no-P2P options. Swap is disabled during private-key use
and may be restored only after Core and its RAM working files are gone.
Networking is never restored.

## App and update boundaries

A committed computer cannot start the online node, connect the online wallet,
download Core, or use the development network bypass. Startup checks the
commitment before scheduling connection attempts. Existing cold wallet files
also suppress the normal online startup path until permanent setup is completed.
The root policy makes the commitment survive app replacement, user changes and
removal of a per-user marker.

The installer automatically uses offline mode on committed computers and on
computers with saved cold wallets. It uses transferred hash-matching wheels in
a wheels/ directory or checks that installed packages already satisfy the lock
without using an index. Transfer application, Core and dependency updates from
a separate connected computer. Never git-pull, apt-download or reconnect the
real signer to obtain an update.

The source-only --dev-keep-network exception is for disposable testing VMs. It
does not install this policy, displays a testing warning, and is rejected after
the machine has been committed. Release packages omit that exception.

## Limits and acceptance

Software configuration cannot establish a physical air gap or protect against
a compromised OS, administrator, firmware or networking before the OS starts.
The app cannot prove that a radio or network adapter has been physically
removed. Hardware removal and a dedicated trusted installation are the
strongest safeguard; the software policy adds enforcement and failure checks.

Validation exercises the real nft rules in isolated network namespaces:
IPv4, IPv6 and established traffic are blocked, loopback works, and repeated
loading repairs changed policies/rules and dormant tables. Mocked installation
and GUI checks cover failed setup, stale/wrong-boot status, modified files,
unblocked radios, active links, inactive timers, download/online/CLI blocking and
offline installer arguments. Shell and systemd unit validation also pass.

Actual administrator authorization, boot/reboot ordering, suspend/resume,
radio hot-plug and distro integration still require acceptance on a disposable
Debian VM without real keys. The review harnesses do not install a host policy.

Policy references: [nftables manual](https://www.netfilter.org/projects/nftables/manpage.html), [systemd network-pre ordering](https://github.com/systemd/systemd/blob/main/docs/NETWORK_ONLINE.md), and [systemd timers](https://www.freedesktop.org/software/systemd/man/256/systemd.timer.html).
