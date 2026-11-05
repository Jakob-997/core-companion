"""Short-lived, isolated Bitcoin Core process used by the cold-signer flow."""

import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

from .linux_cold import ColdSetupError, NetworkSession, _active_swaps, _mount_type
from .rpc import CoreError, CoreRPC
from .seed import hash_wallet_dat, master_xprv
from .storage import ColdWalletStore
from .permanent_airgap import PermanentAirgap
from .public_wallet import combined_public_descriptor, normalize_slip132_public_key


DEFAULT_MULTISIG_PATH = "m/87h/0h/0h"


def normalize_account_key(rpc, value):
    """Normalize hardware-wallet keys; Core verifies the key and optional origin."""
    if not isinstance(value, str) or len(value) > 4096:
        raise ColdSetupError("Enter a public extended key with optional origin information.")
    value = "".join(value.split())
    match = re.fullmatch(
        r"(\[[^\[\]]+\])?((?:xpub|ypub|zpub|Ypub|Zpub)[1-9A-HJ-NP-Za-km-z]{80,120})",
        value,
    )
    if match is None:
        raise ColdSetupError(
            "Enter a mainnet extended public key, optionally prefixed with its origin, "
            "for example [fingerprint/48h/0h/0h/2h]Zpub…"
        )
    origin, key = match.groups()
    try:
        value = (origin or "") + normalize_slip132_public_key(key)
    except CoreError as exc:
        raise ColdSetupError(str(exc)) from None
    prefix, suffix = "wpkh(", "/0/*)"
    try:
        checked = rpc.call("getdescriptorinfo", [prefix + value + suffix])
    except CoreError as exc:
        raise ColdSetupError(f"Core rejected the signer key or origin.\n\n{exc}") from None
    if not isinstance(checked, dict) or not isinstance(checked.get("descriptor"), str):
        raise ColdSetupError("Core returned an invalid signer-key description.")
    descriptor = checked.get("descriptor", "").split("#", 1)[0]
    if (checked.get("hasprivatekeys") is not False or checked.get("isrange") is not True
            or checked.get("issolvable") is not True
            or not descriptor.startswith(prefix) or not descriptor.endswith(suffix)):
        raise ColdSetupError("Core could not validate a ranged public signer key.")
    return descriptor[len(prefix):-len(suffix)]


class ColdCoreRPC(CoreRPC):
    """RPC operations required only by the isolated cold Core process."""

    METHODS = CoreRPC.METHODS | frozenset({
        "setnetworkactive", "stop", "createwallet", "unloadwallet", "addhdkey", "setlabel",
        "derivehdkey", "createwalletdescriptor", "getdescriptorinfo",
        "importdescriptors", "walletpassphrase", "walletlock",
        "walletprocesspsbt", "listdescriptors", "backupwallet", "loadwallet",
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
        self.wallet_id = None
        self.store = ColdWalletStore()
        self.prepared_multisig = None

    def _assert_isolation(self):
        """Recheck host isolation at every key-generation or signing boundary."""
        if self.dev_keep_network and PermanentAirgap.is_committed():
            raise ColdSetupError("The development network bypass is forbidden on a permanently offline installation.")
        if _active_swaps():
            raise ColdSetupError("System swap became active. Close the signer before continuing.")
        if not self.dev_keep_network:
            NetworkSession().assert_disabled()
        if self.process is not None:
            if self.process.poll() is not None:
                raise ColdSetupError("The isolated Bitcoin Core process is no longer running.")
            try:
                info = self.rpc.call("getnetworkinfo")
            except CoreError:
                raise ColdSetupError("Could not verify the isolated Core process. Close the signer before continuing.") from None
            if info.get("networkactive") is not False or info.get("connections") != 0:
                raise ColdSetupError("Core peer networking became active. Close the signer before continuing.")

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
        self.prepared_multisig = None

    @staticmethod
    def _check_sighashes(decoded):
        # NONE, SINGLE and ANYONECANPAY permit changes beyond this review.
        if not isinstance(decoded, dict):
            raise ColdSetupError("Core did not return decoded PSBT details.")
        inputs = decoded.get("inputs")
        if not isinstance(inputs, list) or any(not isinstance(item, dict) for item in inputs):
            raise ColdSetupError("Core did not return the PSBT input details.")
        if any(item.get("sighash", "ALL") not in ("ALL", "DEFAULT") for item in inputs):
            raise ColdSetupError("Only ALL or Taproot DEFAULT signatures are supported. Request a new PSBT from the online wallet.")

    @staticmethod
    def _transaction_for_review(decoded):
        """Use Core's txid for v0, or commit to Core's decoded v2 transaction fields.

        Core does not expose a reconstructed unsigned transaction for PSBTv2.
        The v2 review ID is an application commitment, never a Bitcoin txid.
        Transaction serialization and signing remain entirely inside Core.
        """
        version = decoded.get("psbt_version", 0)
        if type(version) is not int:
            raise ColdSetupError("Core returned an invalid PSBT version.")
        if version == 0:
            transaction = decoded.get("tx", {})
            if not isinstance(transaction, dict):
                raise ColdSetupError("Core did not return the unsigned transaction for review.")
            txid = transaction.get("txid")
            if not isinstance(txid, str) or re.fullmatch(r"[0-9a-fA-F]{64}", txid) is None:
                raise ColdSetupError("Core did not return the unsigned transaction ID for review.")
            return transaction, txid, "Transaction ID"
        if version != 2:
            raise ColdSetupError("This PSBT version is not supported. Request PSBT version 0 or 2.")

        def uint(value):
            if type(value) is not int or not 0 <= value <= 0xffffffff:
                raise ColdSetupError("Core returned incomplete PSBTv2 transaction fields.")
            return value

        tx_version = decoded.get("tx_version")
        if type(tx_version) is not int or not -(2 ** 31) <= tx_version < 2 ** 31:
            raise ColdSetupError("Core did not return the PSBTv2 transaction version.")
        fallback = uint(decoded["fallback_locktime"]) if "fallback_locktime" in decoded else None
        flags = []
        for field in ("inputs_modifiable", "outputs_modifiable", "has_sighash_single"):
            value = decoded.get(field)
            if field in decoded and type(value) is not bool:
                raise ColdSetupError("Core returned invalid PSBTv2 modification flags.")
            flags.append(value)
        if flags[2]:
            raise ColdSetupError("PSBTv2 SIGHASH_SINGLE transactions are not supported.")
        inputs, outputs = decoded.get("inputs"), decoded.get("outputs")
        if (not isinstance(inputs, list) or not inputs or not isinstance(outputs, list) or not outputs
                or uint(decoded.get("input_count")) != len(inputs)
                or uint(decoded.get("output_count")) != len(outputs)):
            raise ColdSetupError("Core did not return every PSBTv2 input and output.")
        input_fields, output_fields, review_outputs, constraints = [], [], [], []
        for index, item in enumerate(inputs, 1):
            if (not isinstance(item, dict) or not isinstance(item.get("previous_txid"), str)
                    or re.fullmatch(r"[0-9a-fA-F]{64}", item["previous_txid"]) is None):
                raise ColdSetupError("Core did not return a PSBTv2 previous transaction ID.")
            optional = [uint(item[field]) if field in item else None
                        for field in ("sequence", "time_locktime", "height_locktime")]
            input_fields.append([item["previous_txid"], uint(item.get("previous_vout")), *optional])
            for field, value in zip(("time", "height"), optional[1:]):
                if value is not None:
                    constraints.append(f"input {index} {field} {value}")
        for item in outputs:
            if not isinstance(item, dict):
                raise ColdSetupError("Core returned an invalid PSBTv2 output.")
            amount, script = item.get("amount"), item.get("script")
            if (type(amount) not in (int, Decimal) or (isinstance(amount, Decimal) and not amount.is_finite())
                    or not 0 <= amount <= 21000000
                    or amount * 100000000 != int(amount * 100000000)
                    or not isinstance(script, dict) or not isinstance(script.get("hex"), str)
                    or re.fullmatch(r"(?:[0-9a-fA-F]{2})*", script["hex"]) is None):
                raise ColdSetupError("Core did not return a complete PSBTv2 output amount and script.")
            output_fields.append([int(amount * 100000000), script["hex"]])
            review_outputs.append({"value": amount, "scriptPubKey": script})
        material = json.dumps([tx_version, fallback, flags, input_fields, output_fields], separators=(",", ":")).encode("ascii")
        review_id = hashlib.sha256(b"Core Companion PSBTv2 review v1\x00" + material).hexdigest()
        locktime = f"fallback {fallback if fallback is not None else 0}"
        if constraints:
            locktime += "; " + "; ".join(constraints)
        return {"version": tx_version, "locktime": locktime, "vin": inputs, "vout": review_outputs}, review_id, "Review ID"

    @staticmethod
    def _free_loopback_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def start(self):
        if sys.platform != "linux":
            raise ColdSetupError("The cold signer currently requires Linux.")
        if self.dev_keep_network and PermanentAirgap.is_committed():
            raise ColdSetupError("Development networking cannot be used on a permanently offline installation.")
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
        self._assert_isolation()
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
        self._assert_isolation()
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

    def prepare_multisig_key(self, phrase, wallet_passphrase="", bip39_passphrase=""):
        """Create the local signer first so its public account key can be shared."""
        self._assert_isolation()
        name = "cold-signer"
        root_xprv = ""
        created_wallet = False
        try:
            root_xprv = master_xprv(phrase, bip39_passphrase)
            self._prepare_signer()
            self.rpc.call("createwallet", [name, False, True, wallet_passphrase or "", False, True, False, False])
            created_wallet = True
            if wallet_passphrase:
                self.rpc.call("walletpassphrase", [wallet_passphrase, 90], wallet=name)
            root = self.rpc.call("addhdkey", [root_xprv], wallet=name)
            account = self.rpc.call("derivehdkey", [DEFAULT_MULTISIG_PATH, {"hdkey": root["xpub"]}], wallet=name)
            own_public = normalize_account_key(self.rpc, account["origin"] + account["xpub"])
            self.prepared_multisig = {
                "root_xpub": root["xpub"], "own_account_key": own_public,
                "encrypted": bool(wallet_passphrase),
            }
            return {"own_account_key": own_public, "encrypted": bool(wallet_passphrase)}
        except (CoreError, KeyError, TypeError) as exc:
            raise ColdSetupError(f"Core could not prepare the multisig signer.\n\n{exc}") from None
        finally:
            root_xprv = ""
            if wallet_passphrase and created_wallet:
                self._lock_wallet()

    def complete_multisig_wallet(self, threshold, other_signers, wallet_passphrase="", own_signer_label="This signer"):
        """Import the shared policy into the prepared signer without reseeding it."""
        self._assert_isolation()
        if self.address_type is not None or self.prepared_multisig is None:
            raise ColdSetupError("Prepare the local multisig signer before adding the wallet policy.")
        if not isinstance(other_signers, list) or not 1 <= len(other_signers) <= 19:
            raise ColdSetupError("Native multisig supports between 2 and 20 signers in this flow.")
        if not isinstance(threshold, int) or not 1 <= threshold <= len(other_signers) + 1:
            raise ColdSetupError("The signing threshold must be between 1 and the signer count.")
        if any(not isinstance(item, dict) or not isinstance(item.get("key"), str) or
               not isinstance(item.get("label"), str) or len(item["label"]) > 128 for item in other_signers):
            raise ColdSetupError("Each signer needs a public account key and a label of at most 128 characters.")
        normalized = [normalize_account_key(self.rpc, item["key"]) for item in other_signers]
        external_xpubs = [key.split("]", 1)[1] for key in normalized]
        if len(set(external_xpubs)) != len(external_xpubs):
            raise ColdSetupError("A signer xpub was entered more than once.")

        name = "cold-signer"
        account = {}
        encrypted = self.prepared_multisig["encrypted"]
        if encrypted and not wallet_passphrase:
            raise ColdSetupError("Enter the prepared signer's encryption password.")
        try:
            if encrypted:
                self.rpc.call("walletpassphrase", [wallet_passphrase, 90], wallet=name)
            account = self.rpc.call(
                "derivehdkey",
                [DEFAULT_MULTISIG_PATH, {"private": True, "hdkey": self.prepared_multisig["root_xpub"]}],
                wallet=name,
            )
            if not all(isinstance(account.get(key), str) for key in ("origin", "xpub", "xprv")):
                raise ColdSetupError("Core did not return the expected signer account key details.")
            own_public = normalize_account_key(self.rpc, account["origin"] + account["xpub"])
            if own_public != self.prepared_multisig["own_account_key"]:
                raise ColdSetupError("The local signer key changed after preparation. Close this signer and retry.")
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
                "encrypted": encrypted,
            }
        except CoreError as exc:
            raise ColdSetupError(f"Core multisig setup failed.\n\n{exc}") from None
        finally:
            if isinstance(account, dict):
                account["xprv"] = ""
            if encrypted:
                self._lock_wallet()

    def create_multisig_wallet(
        self, phrase, threshold, other_signers, wallet_passphrase="", bip39_passphrase="", own_signer_label="This signer"
    ):
        """Create a multisig wallet when all public signer keys are already known."""
        self.prepare_multisig_key(phrase, wallet_passphrase, bip39_passphrase)
        return self.complete_multisig_wallet(threshold, other_signers, wallet_passphrase, own_signer_label)

    def review_psbt(self, psbt):
        """Ask Core to enrich and inspect a PSBT without signing it."""
        self.reviewed_transaction = None
        self._assert_isolation()
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
        transaction, review_id, review_id_label = self._transaction_for_review(decoded)
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
        self.reviewed_transaction = (updated["psbt"], review_id)
        return {
            "psbt": updated["psbt"],
            "review_id": review_id,
            "review_id_label": review_id_label,
            "version": transaction.get("version"),
            "locktime": transaction.get("locktime"),
            "inputs": len(transaction.get("vin", [])),
            "outputs": outputs,
            "fee": decoded.get("fee"),
            "analysis": analysis,
        }

    def sign_psbt(self, psbt, wallet_passphrase="", expected_review_id=""):
        """Sign only the exact reviewed transaction; never finalize or broadcast."""
        if not isinstance(psbt, str) or not psbt.strip() or len(psbt) > 2 * 1024 * 1024:
            raise ColdSetupError("The reviewed PSBT is empty or exceeds the 2 MiB limit.")
        if self.reviewed_transaction != (psbt.strip(), expected_review_id):
            raise ColdSetupError("Review this exact PSBT before signing.")
        try:
            self._assert_isolation()
            before = self.rpc.call("decodepsbt", [psbt.strip()])
            self._check_sighashes(before)
            if self._transaction_for_review(before)[1] != expected_review_id:
                raise ColdSetupError("The unsigned transaction changed after review. Review it again before signing.")
            if wallet_passphrase:
                self.rpc.call("walletpassphrase", [wallet_passphrase, 60], wallet="cold-signer")
            result = self.rpc.call(
                "walletprocesspsbt",
                {"psbt": psbt.strip(), "sign": True, "bip32derivs": True, "finalize": False},
                wallet="cold-signer",
            )
            after = self.rpc.call("decodepsbt", [result["psbt"]])
            if self._transaction_for_review(after)[1] != expected_review_id:
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
        self._assert_isolation()
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
        self.store.release()

    def save_wallet(self, metadata):
        self._assert_isolation()
        try:
            self.wallet_id = self.store.save(self.rpc, self.wallet_id, metadata)
        except (OSError, ValueError, CoreError) as exc:
            raise ColdSetupError("Could not save the wallet. Keep this window open and check the storage location.") from exc
        return self.wallet_id

    def unload_signer(self):
        if "cold-signer" in self.rpc.call("listwallets"):
            self.rpc.call("unloadwallet", ["cold-signer"])
        self.address_type = None
        self.wallet_id = None
        self.reviewed_transaction = None
        self._prepare_signer()

    def open_saved_wallet(self, wallet_id):
        self._assert_isolation()
        self._prepare_signer()
        path = self.directory / "wallets" / "cold-signer" / "wallet.dat"
        try:
            metadata = self.store.restore(wallet_id, path)
            self.rpc.call("loadwallet", ["cold-signer", False])
            info = self.rpc.call("getwalletinfo", wallet="cold-signer")
            encrypted = "unlocked_until" in info
            recorded_encryption = metadata.get(
                "encrypted", metadata.get("result", {}).get("encrypted", True)
            )
            if recorded_encryption is not encrypted:
                raise ColdSetupError("The saved wallet encryption status does not match its Core backup.")
            self.address_type = metadata["address_type"]
            if self.address_type not in ("bech32", "bech32m", "p2sh-segwit", "legacy"):
                raise ValueError()
            descriptors = [item["desc"] for item in sorted(
                (item for item in self.rpc.call("listdescriptors", [False], wallet="cold-signer")["descriptors"]
                 if item.get("active") is True), key=lambda item: item.get("internal", False))]
            self.wallet_id = wallet_id
            result = metadata["result"]
            result["descriptors"] = descriptors
            result["address_info"] = self.rpc.call("getaddressinfo", [result["address"]], wallet="cold-signer")
            if result["address_info"].get("ismine") is not True:
                raise ColdSetupError("The saved identity address does not belong to this Core wallet.")
            result["encrypted"] = encrypted
            hidden = set(metadata.get("hidden_addresses", []))
            records = {item["address"]: item for item in metadata.get("address_records", []) if item["address"] not in hidden}
            for item in self.rpc.call("listreceivedbyaddress", {"minconf": 0, "include_empty": True}, wallet="cold-signer"):
                if item["address"] not in hidden:
                    records.setdefault(item["address"], {"address": item["address"], "label": item.get("label", ""), "used": False})
            metadata["address_records"] = list(records.values())
            return metadata
        except (OSError, ValueError, KeyError, CoreError) as exc:
            raise ColdSetupError("Core could not open the saved wallet.") from exc

    def public_descriptor(self, descriptors):
        return combined_public_descriptor(self.rpc, descriptors)
