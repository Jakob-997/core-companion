"""Short-lived, isolated Bitcoin Core process used by the cold-signer flow."""

import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

from .linux_cold import ColdSetupError, NetworkSession, _active_swaps, _mount_type
from .rpc import CoreError, CoreRPC
from .seed import hash_wallet_dat, master_xprv


_BIP87_ACCOUNT_KEY = re.compile(
    r"^\[([0-9a-fA-F]{8})/(?:87h|87')/(?:0h|0')/(?:0h|0')\](xpub[1-9A-HJ-NP-Za-km-z]+)$"
)


def normalize_bip87_account_key(value):
    """Accept only a mainnet xpub with an explicit BIP87 origin path."""
    match = _BIP87_ACCOUNT_KEY.fullmatch("".join(str(value).split()))
    if not match:
        raise ColdSetupError(
            "Each signer must provide an xpub with origin fingerprint and path "
            "[fingerprint/87h/0h/0h]."
        )
    fingerprint, xpub = match.groups()
    return f"[{fingerprint.lower()}/87h/0h/0h]{xpub}"


class ColdCoreRPC(CoreRPC):
    """RPC operations required only by the isolated cold Core process."""

    METHODS = CoreRPC.METHODS | frozenset({
        "setnetworkactive", "stop", "createwallet", "unloadwallet", "addhdkey", "setlabel",
        "derivehdkey", "createwalletdescriptor", "getdescriptorinfo",
        "importdescriptors", "walletpassphrase", "walletlock",
        "walletprocesspsbt", "listdescriptors",
    })

    def call(self, method, params=None, wallet=None, **kwargs):
        try:
            return super().call(method, params, wallet, **kwargs)
        except CoreError as exc:
            detail = re.sub(r"[xt]prv[1-9A-HJ-NP-Za-km-z]+", "[private key redacted]", str(exc))
            raise CoreError(f"{method}: {detail}") from None


class OfflineCore:
    """Run a private, no-P2P Core instance entirely inside a tmpfs directory."""

    def __init__(self, bitcoind, session_id, base="/dev/shm", *, dev_keep_network=False):
        self.binary = Path(bitcoind).expanduser().resolve()
        self.base = Path(base).resolve()
        self.dev_keep_network = bool(dev_keep_network)
        if not isinstance(session_id, str) or re.fullmatch(r"[0-9a-f]{32}", session_id) is None:
            raise ColdSetupError("The cold signer session identifier is invalid.")
        self.session_id = session_id
        self.directory = None
        self.process = None
        self.rpc = None
        self.port = None
        self.reviewed_transaction = None
        self.address_type = None

    def _lock_wallet(self):
        try:
            self.rpc.call("walletlock", wallet="cold-signer")
        except CoreError:
            raise ColdSetupError("Core could not confirm the wallet is locked. Close this signer before continuing.") from None

    def _prepare_signer(self):
        """Discard only a failed setup's private RAM wallet before retrying."""
        if self.address_type is not None:
            raise ColdSetupError("Close the current wallet before creating another.")
        if self.directory is None:
            raise ColdSetupError("The isolated Core session is not running.")
        if "cold-signer" in self.rpc.call("listwallets"):
            self.rpc.call("unloadwallet", ["cold-signer"])
        path = self.directory / "wallets" / "cold-signer"
        if path.is_symlink():
            raise ColdSetupError("The temporary wallet path is unexpectedly a symbolic link.")
        if path.exists():
            try:
                shutil.rmtree(path)
            except OSError:
                raise ColdSetupError("Could not clear the failed wallet setup. Close this signer and retry.") from None

    @staticmethod
    def _check_sighashes(decoded):
        # NONE, SINGLE and ANYONECANPAY permit changes beyond this review.
        if any(item.get("sighash", "ALL") not in ("ALL", "DEFAULT")
               for item in decoded.get("inputs", [])):
            raise ColdSetupError("Only ALL or Taproot DEFAULT signatures are supported. Request a new PSBT from the online wallet.")

    @staticmethod
    def _free_loopback_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def start(self):
        if sys.platform != "linux":
            raise ColdSetupError("The cold signer currently requires Linux.")
        if not self.binary.is_file() or not os.access(self.binary, os.X_OK):
            raise ColdSetupError("Select an executable Bitcoin Core bitcoind binary.")
        if _mount_type(self.base) != "tmpfs":
            raise ColdSetupError("Cold signer data must be stored on a RAM-backed filesystem.")
        if _active_swaps():
            raise ColdSetupError("System swap is active; cold Core will not be started.")
        if not self.dev_keep_network:
            NetworkSession().assert_disabled()

        self.directory = self.base / f"core-companion-cold-{self.session_id}"
        if self.directory.exists() or self.directory.is_symlink():
            raise ColdSetupError("A temporary cold-signer directory already exists; close stale sessions first.")
        created_directory = False
        try:
            self.directory.mkdir(mode=stat.S_IRWXU)
            created_directory = True
            wallet_dir = self.directory / "wallets"
            wallet_dir.mkdir(mode=stat.S_IRWXU)
        except OSError as exc:
            if created_directory:
                self._remove_directory()
            else:
                self.directory = None
            raise ColdSetupError("Could not create private temporary storage in RAM.") from exc
        self.port = self._free_loopback_port()
        cookie = self.directory / ".cookie"
        log = self.directory / "debug.log"
        command = [
            str(self.binary),
            f"-datadir={self.directory}",
            "-conf=/dev/null",
            f"-walletdir={wallet_dir}",
            f"-rpccookiefile={cookie}",
            f"-rpcport={self.port}",
            "-rpcbind=127.0.0.1",
            "-rpcallowip=127.0.0.1",
            "-server=1",
            "-daemon=0",
            "-chain=main",
            "-listen=0",
            "-connect=0",
            "-dnsseed=0",
            "-discover=0",
            "-natpmp=0",
            "-listenonion=0",
            "-maxconnections=0",
            "-networkactive=0",
            "-walletbroadcast=0",
            f"-debuglogfile={log}",
        ]
        try:
            with (self.directory / "startup.log").open("xb") as startup_log:
                self.process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=startup_log,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                    env={"PATH": "/usr/bin:/bin", "HOME": str(self.directory), "LANG": "C", "LC_ALL": "C"},
                )
        except OSError as exc:
            self._remove_directory()
            raise ColdSetupError("Could not start the isolated Bitcoin Core process.") from exc

        self.rpc = ColdCoreRPC(self.port, cookie)
        deadline = time.monotonic() + 45
        last_error = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                try:
                    with (self.directory / "startup.log").open("rb") as startup_log:
                        startup_log.seek(0, os.SEEK_END)
                        startup_log.seek(max(0, startup_log.tell() - 3000))
                        detail = startup_log.read().decode("utf-8", "replace").strip()
                except OSError:
                    detail = ""
                exit_code = self.process.returncode
                self._remove_directory()
                raise ColdSetupError(
                    f"The isolated Bitcoin Core process exited during startup (exit {exit_code})."
                    + (f"\n\n{detail}" if detail else "")
                )
            try:
                info = self.rpc.call("getnetworkinfo")
                # Core encodes versions as major * 10000 + minor * 100 + patch.
                if int(info.get("version", 0)) < 320100:
                    self.close()
                    raise ColdSetupError("Cold signer setup requires Bitcoin Core 32.1 or newer.")
                state = self.rpc.call("setnetworkactive", [False])
                if state is not False:
                    self.close()
                    raise ColdSetupError("Bitcoin Core did not confirm P2P networking is disabled.")
                info = self.rpc.call("getnetworkinfo")
                if info.get("networkactive") is not False or info.get("connections") != 0:
                    self.close()
                    raise ColdSetupError("Bitcoin Core still reports active P2P networking.")
                return self
            except CoreError as exc:
                last_error = exc
                time.sleep(0.2)
        self.close()
        raise ColdSetupError("The isolated Bitcoin Core process did not become ready.") from last_error

    def create_entropy_wallet_hash(self):
        if self.process is None or self.process.poll() is not None:
            raise ColdSetupError("The isolated Bitcoin Core process is not running.")
        name = "entropy-source"
        wallet_dir = self.directory / "wallets" / name
        try:
            self.rpc.call("createwallet", [name, False, False, "", False, True, False, False])
            self.rpc.call("unloadwallet", {"wallet_name": name})
            if not wallet_dir.is_dir() or wallet_dir.is_symlink():
                raise ColdSetupError("Core's temporary entropy wallet was not in its private RAM directory.")
            return hash_wallet_dat(wallet_dir / "wallet.dat")
        except CoreError as exc:
            raise ColdSetupError("Core could not create or close its temporary entropy wallet.") from exc
        finally:
            # Core must release the SQLite database before the file is removed.
            try:
                loaded = name in self.rpc.call("listwallets")
            except CoreError:
                loaded = True
            if wallet_dir.exists() and loaded:
                try:
                    self.rpc.call("unloadwallet", {"wallet_name": name})
                    loaded = False
                except CoreError:
                    pass
            if wallet_dir.exists() and not loaded:
                try:
                    shutil.rmtree(wallet_dir)
                except OSError as exc:
                    raise ColdSetupError("Could not remove the temporary entropy wallet from RAM.") from exc

    def create_single_sig_wallet(self, phrase, address_type="bech32", wallet_passphrase="", bip39_passphrase=""):
        """Load a BIP39 root key into a blank Core wallet and derive its first address."""
        if address_type not in ("legacy", "p2sh-segwit", "bech32", "bech32m"):
            raise ColdSetupError("Choose a supported Core single-signature address type.")
        name = "cold-signer"
        xprv = ""
        created_wallet = False
        try:
            xprv = master_xprv(phrase, bip39_passphrase)
            self._prepare_signer()
            self.rpc.call("createwallet", [name, False, True, wallet_passphrase or "", False, True, False, False])
            created_wallet = True
            if wallet_passphrase:
                self.rpc.call("walletpassphrase", [wallet_passphrase, 60], wallet=name)
            root = self.rpc.call("addhdkey", [xprv], wallet=name)
            self.rpc.call("createwalletdescriptor", [address_type, {"hdkey": root["xpub"]}], wallet=name)
            descriptors = self.rpc.call("listdescriptors", [False], wallet=name)["descriptors"]
            address = self.rpc.call("getnewaddress", ["", address_type], wallet=name)
            address_info = self.rpc.call("getaddressinfo", [address], wallet=name)
            if not address_info.get("ismine"):
                raise ColdSetupError("Core did not verify the generated address as part of this wallet.")
            self.address_type = address_type
            return {
                "address": address,
                "descriptors": [item["desc"] for item in sorted(
                    (item for item in descriptors if item.get("active") is True),
                    key=lambda item: item.get("internal", False),
                )],
                "address_info": address_info,
                "wallet_name": name,
                "encrypted": bool(wallet_passphrase),
            }
        except CoreError as exc:
            raise ColdSetupError(f"Core wallet setup failed.\n\n{exc}") from None
        finally:
            # Minimize references; the helper process must exit after the user finishes.
            xprv = ""
            if wallet_passphrase and created_wallet:
                self._lock_wallet()

    def create_multisig_wallet(
        self, phrase, threshold, other_signers, wallet_passphrase="", bip39_passphrase="", own_signer_label="This signer"
    ):
        """Create an ephemeral BIP87 P2WSH descriptor wallet in Core."""
        if not isinstance(threshold, int) or not 1 <= threshold <= len(other_signers) + 1:
            raise ColdSetupError("The signing threshold must be between 1 and the signer count.")
        if not 2 <= len(other_signers) + 1 <= 20:
            raise ColdSetupError("Native multisig supports between 2 and 20 signers in this flow.")
        normalized = [normalize_bip87_account_key(item["key"]) for item in other_signers]
        external_xpubs = [key.split("]", 1)[1] for key in normalized]
        if len(set(external_xpubs)) != len(external_xpubs):
            raise ColdSetupError("A signer xpub was entered more than once.")

        name = "cold-signer"
        root_xprv = ""
        account = {}
        created_wallet = False
        try:
            root_xprv = master_xprv(phrase, bip39_passphrase)
            self._prepare_signer()
            self.rpc.call("createwallet", [name, False, True, wallet_passphrase or "", False, True, False, False])
            created_wallet = True
            if wallet_passphrase:
                self.rpc.call("walletpassphrase", [wallet_passphrase, 90], wallet=name)
            root = self.rpc.call("addhdkey", [root_xprv], wallet=name)
            account = self.rpc.call(
                "derivehdkey",
                ["m/87h/0h/0h", {"private": True, "hdkey": root["xpub"]}],
                wallet=name,
            )
            if not all(isinstance(account.get(key), str) for key in ("origin", "xpub", "xprv")):
                raise ColdSetupError("Core did not return the expected BIP87 account key details.")
            own_public = normalize_bip87_account_key(account["origin"] + account["xpub"])
            signer_public = [own_public, *normalized]
            if len({key.split("]", 1)[1] for key in signer_public}) != len(signer_public):
                raise ColdSetupError("The local signer key duplicates one of the other signer keys.")

            private_key = account["origin"] + account["xprv"]
            public_keys = signer_public
            requests = []
            public_descriptors = []
            for branch, internal in ((0, False), (1, True)):
                suffix = f"/{branch}/*"
                private_keys = [private_key + suffix, *[key + suffix for key in normalized]]
                public_branch_keys = [key + suffix for key in public_keys]
                private_descriptor = f"wsh(sortedmulti({threshold},{','.join(private_keys)}))"
                public_descriptor = f"wsh(sortedmulti({threshold},{','.join(public_branch_keys)}))"
                checked_private = self.rpc.call("getdescriptorinfo", [private_descriptor])
                checked_public = self.rpc.call("getdescriptorinfo", [public_descriptor])
                if checked_private.get("hasprivatekeys") is not True:
                    raise ColdSetupError("Core did not recognize the local signer key as private.")
                if checked_public.get("hasprivatekeys") is not False:
                    raise ColdSetupError("The public recovery descriptor unexpectedly contains private keys.")
                requests.append({
                    # Core normalizes "descriptor" to PUBLIC keys. Its checksum
                    # applies to our original private descriptor; keep that key.
                    "desc": private_descriptor + "#" + checked_private["checksum"],
                    "timestamp": "now",
                    "active": True,
                    "internal": internal,
                    "range": [0, 1000],
                    "next_index": 0,
                })
                public_descriptors.append(checked_public["descriptor"])

            imported = self.rpc.call("importdescriptors", [requests], wallet=name)
            if not isinstance(imported, list) or len(imported) != 2 or any(item.get("success") is not True for item in imported):
                raise ColdSetupError("Core rejected one or more multisig descriptors.")
            address = self.rpc.call("getnewaddress", ["", "bech32"], wallet=name)
            address_info = self.rpc.call("getaddressinfo", [address], wallet=name)
            if address_info.get("ismine") is not True:
                raise ColdSetupError("Core did not verify the generated multisig address as part of this wallet.")
            self.address_type = "bech32"
            return {
                "address": address,
                "descriptors": public_descriptors,
                "address_info": address_info,
                "wallet_name": name,
                "own_account_key": own_public,
                "signers": [
                    {"label": own_signer_label, "key": own_public},
                    *[
                        {"label": item["label"], "key": key}
                        for item, key in zip(other_signers, normalized)
                    ],
                ],
                "threshold": threshold,
                "encrypted": bool(wallet_passphrase),
            }
        except CoreError as exc:
            raise ColdSetupError(f"Core multisig setup failed.\n\n{exc}") from None
        finally:
            root_xprv = ""
            if isinstance(account, dict):
                account["xprv"] = ""
            if wallet_passphrase and created_wallet:
                self._lock_wallet()

    def review_psbt(self, psbt):
        """Ask Core to enrich and inspect a PSBT without signing it."""
        self.reviewed_transaction = None
        if not isinstance(psbt, str) or not psbt.strip() or len(psbt) > 2 * 1024 * 1024:
            raise ColdSetupError("Enter a base64 PSBT smaller than 2 MiB.")
        try:
            updated = self.rpc.call(
                "walletprocesspsbt",
                {"psbt": psbt.strip(), "sign": False, "bip32derivs": True, "finalize": False},
                wallet="cold-signer",
            )
            decoded = self.rpc.call("decodepsbt", [updated["psbt"]])
            analysis = self.rpc.call("analyzepsbt", [updated["psbt"]])
        except (CoreError, KeyError, TypeError):
            raise ColdSetupError("Core could not safely decode and inspect this PSBT.") from None

        self._check_sighashes(decoded)
        if analysis.get("error"):
            raise ColdSetupError("Core reports that this PSBT is invalid. Request a new PSBT.")
        transaction = decoded.get("tx", {})
        txid = transaction.get("txid")
        if not isinstance(txid, str) or not txid:
            raise ColdSetupError("Core did not return the unsigned transaction ID for review.")
        input_states = analysis.get("inputs", [])
        if len(input_states) != len(transaction.get("vin", [])) or any(
            item.get("has_utxo") is not True for item in input_states
        ):
            raise ColdSetupError(
                "Core cannot verify the previous-output amount for every input. "
                "Do not sign this PSBT; use one that includes verified UTXO data."
            )
        if decoded.get("fee") is None or decoded["fee"] < 0:
            raise ColdSetupError("Core could not calculate the transaction fee from this PSBT.")
        outputs = []
        for output in transaction.get("vout", []):
            script = output.get("scriptPubKey", {})
            addresses = script.get("address") or script.get("addresses") or []
            if isinstance(addresses, str):
                address = addresses
            elif isinstance(addresses, list) and addresses:
                address = str(addresses[0])
            else:
                address = ""
            mine = False
            change = False
            if address:
                try:
                    info = self.rpc.call("getaddressinfo", [address], wallet="cold-signer")
                    mine = info.get("ismine") is True
                    change = mine and info.get("ischange") is True
                except CoreError:
                    pass
            outputs.append({
                "address": address or "(non-standard or unrecognized script)",
                "script": script.get("hex", ""),
                "amount": output.get("value"),
                "is_mine": mine,
                "is_change": change,
            })
        self.reviewed_transaction = (updated["psbt"], txid)
        return {
            "psbt": updated["psbt"],
            "unsigned_txid": txid,
            "txid": txid,
            "version": transaction.get("version"),
            "locktime": transaction.get("locktime"),
            "inputs": len(transaction.get("vin", [])),
            "outputs": outputs,
            "fee": decoded.get("fee"),
            "analysis": analysis,
        }

    def sign_psbt(self, psbt, wallet_passphrase="", expected_unsigned_txid=""):
        """Sign only the reviewed unsigned transaction; never finalize or broadcast."""
        if not isinstance(psbt, str) or not psbt.strip() or len(psbt) > 2 * 1024 * 1024:
            raise ColdSetupError("The reviewed PSBT is empty or exceeds the 2 MiB limit.")
        if self.reviewed_transaction != (psbt.strip(), expected_unsigned_txid):
            raise ColdSetupError("Review this exact PSBT before signing.")
        try:
            before = self.rpc.call("decodepsbt", [psbt.strip()])
            self._check_sighashes(before)
            if before.get("tx", {}).get("txid") != expected_unsigned_txid:
                raise ColdSetupError("The unsigned transaction changed after review. Review it again before signing.")
            if wallet_passphrase:
                self.rpc.call("walletpassphrase", [wallet_passphrase, 60], wallet="cold-signer")
            result = self.rpc.call(
                "walletprocesspsbt",
                {"psbt": psbt.strip(), "sign": True, "bip32derivs": True, "finalize": False},
                wallet="cold-signer",
            )
            after = self.rpc.call("decodepsbt", [result["psbt"]])
            if after.get("tx", {}).get("txid") != expected_unsigned_txid:
                raise ColdSetupError("Core returned a PSBT with a changed unsigned transaction; do not use it.")
            return {"psbt": result["psbt"], "complete": result.get("complete") is True}
        except CoreError:
            raise ColdSetupError("Core could not sign this PSBT. Check the wallet password and transaction inputs.") from None
        except (KeyError, TypeError):
            raise ColdSetupError("Core returned an incomplete PSBT signing response.") from None
        finally:
            self.reviewed_transaction = None
            if wallet_passphrase:
                self._lock_wallet()

    def verify_address(self, address):
        """Return whether Core recognizes an address as belonging to this wallet."""
        if not isinstance(address, str) or not address or len(address) > 128:
            raise ColdSetupError("Enter a valid Bitcoin address.")
        try:
            info = self.rpc.call("getaddressinfo", [address], wallet="cold-signer")
        except CoreError:
            raise ColdSetupError("Core could not check this address.") from None
        return info.get("ismine") is True

    def new_receive_address(self, label=""):
        """Ask Core for a fresh receive address and confirm wallet ownership."""
        if not isinstance(label, str) or len(label) > 128:
            raise ColdSetupError("Address labels must be 128 characters or fewer.")
        try:
            address = self.rpc.call("getnewaddress", [label, self.address_type], wallet="cold-signer")
            info = self.rpc.call("getaddressinfo", [address], wallet="cold-signer")
        except CoreError:
            raise ColdSetupError("Core could not generate a receive address.") from None
        if info.get("ismine") is not True:
            raise ColdSetupError("Core did not verify the generated address as part of this wallet.")
        return {"address": address, "info": info}

    def set_address_label(self, address, label):
        """Store an address label in Core after checking that the address is ours."""
        if not isinstance(address, str) or not address or len(address) > 128:
            raise ColdSetupError("Choose a valid wallet address.")
        if not isinstance(label, str) or len(label) > 128:
            raise ColdSetupError("Address labels must be 128 characters or fewer.")
        try:
            info = self.rpc.call("getaddressinfo", [address], wallet="cold-signer")
            if info.get("ismine") is not True:
                raise ColdSetupError("Core does not recognize this address as part of the signer wallet.")
            self.rpc.call("setlabel", [address, label], wallet="cold-signer")
        except CoreError:
            raise ColdSetupError("Core could not save this address label.") from None

    def close(self):
        """Stop Core cleanly before deleting its RAM-backed data directory."""
        if self.process is None:
            self._remove_directory()
            return
        if self.process.poll() is None:
            try:
                self.rpc.call("stop")
            except CoreError:
                pass
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        if self.process.poll() is None:
            raise ColdSetupError("Core is still running; do not restore cold-session system settings until it stops.")
        self._remove_directory()
        self.process = None
        self.rpc = None

    def _remove_directory(self):
        if self.directory and self.directory.exists():
            try:
                shutil.rmtree(self.directory)
            except OSError as exc:
                raise ColdSetupError("Could not remove the temporary Core data from RAM.") from exc
        self.directory = None
