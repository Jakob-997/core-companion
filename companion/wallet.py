"""Wallet orchestration only: Core owns balances, addresses and transactions."""

from decimal import Decimal
import re
from .rpc import CoreError


def btc(value):
    return f"{Decimal(str(value)):.8f}"


def validate_wallet_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[\w -]{1,80}", name) or not name.strip():
        raise CoreError("Use a wallet name with letters, numbers, spaces, hyphens or underscores (up to 80 characters).")
    return name


class WalletService:
    def __init__(self, rpc):
        self.rpc = rpc

    def import_public_wallet(self, name, descriptors):
        validate_wallet_name(name)
        if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= 2:
            raise CoreError("Import one receive descriptor, or receive and change descriptors in that order.")
        requests = []
        for index, descriptor in enumerate(descriptors):
            if not isinstance(descriptor, str) or len(descriptor) > 20000:
                raise CoreError("Invalid public descriptor.")
            checked = self.rpc.call("getdescriptorinfo", [descriptor])
            if checked.get("hasprivatekeys") is not False or checked.get("isrange") is not True or checked.get("issolvable") is not True:
                raise CoreError("Import requires ranged public descriptors without private keys.")
            if any(item["desc"] == checked["descriptor"] for item in requests):
                raise CoreError("Receive and change descriptors must be different.")
            requests.append({"desc": checked["descriptor"], "timestamp": 0,
                             "active": True, "internal": index == 1, "range": [0, 1000]})
        self.rpc.call("createwallet", {"wallet_name": name, "disable_private_keys": True, "blank": True})
        result = self.rpc.call("importdescriptors", [requests], wallet=name, timeout=3600)
        if not isinstance(result, list) or len(result) != len(requests) or any(not isinstance(item, dict) for item in result):
            raise CoreError("Core returned an invalid import response. The new wallet remains loaded.")
        failures = [item.get("error", {}).get("message", "Import failed")
                    for item in result if item.get("success") is not True]
        if failures:
            raise CoreError(f"Core could not finish the import: {'; '.join(map(str, failures))}. The new wallet remains loaded.")
        return self.connect()

    def connect(self):
        wallets = self.rpc.call("listwallets")
        watch_only = []
        for name in wallets:
            info = self.rpc.call("getwalletinfo", wallet=name)
            if info.get("private_keys_enabled") is False:
                watch_only.append(name)
        return {
            "node": self.rpc.call("getnetworkinfo"),
            "chain": self.rpc.call("getblockchaininfo"),
            "wallets": watch_only,
        }

    def snapshot(self, name, skip=0):
        return {
            "info": self.rpc.call("getwalletinfo", wallet=name),
            "balances": self.rpc.call("getbalances", wallet=name),
            "transactions": self.rpc.call("listtransactions", {"count": 100, "skip": skip, "include_watchonly": True}, wallet=name),
            "addresses": self.rpc.call("listreceivedbyaddress", {"minconf": 0, "include_empty": True, "include_watchonly": True}, wallet=name),
            "chain": self.rpc.call("getblockchaininfo"),
        }

    def receive(self, name, label):
        params = {"label": label}
        active = [item["desc"] for item in self.rpc.call("listdescriptors", [False], wallet=name)["descriptors"]
                  if item.get("active") is True and not item.get("internal", False)]
        # Imported wallets can contain only Taproot or legacy descriptors while
        # Core's global default remains bech32. Use the imported type explicitly.
        if len(active) == 1:
            for prefix, address_type in (("tr(", "bech32m"), ("wpkh(", "bech32"),
                                         ("wsh(", "bech32"), ("sh(", "p2sh-segwit"), ("pkh(", "legacy")):
                if active[0].startswith(prefix):
                    params["address_type"] = address_type
                    break
        address = self.rpc.call("getnewaddress", params, wallet=name)
        info = self.rpc.call("getaddressinfo", {"address": address}, wallet=name)
        return address, info

    def inspect_psbt(self, name, psbt):
        return {
            "decoded": self.rpc.call("decodepsbt", {"psbt": psbt}, wallet=name),
            "analysis": self.rpc.call("analyzepsbt", {"psbt": psbt}, wallet=name),
        }
