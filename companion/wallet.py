"""Wallet orchestration only: Core owns balances, addresses and transactions."""

from decimal import Decimal
from .rpc import CoreError


def btc(value):
    return f"{Decimal(str(value)):.8f}"


class WalletService:
    def __init__(self, rpc):
        self.rpc = rpc

    def import_public_wallet(self, name, descriptors):
        if not name or len(name) > 80 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_" for c in name):
            raise CoreError("Use a wallet name with letters, numbers, spaces, hyphens or underscores.")
        if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= 2:
            raise CoreError("Import one receive descriptor, or receive and change descriptors in that order.")
        requests = []
        for index, descriptor in enumerate(descriptors):
            if not isinstance(descriptor, str) or len(descriptor) > 20000:
                raise CoreError("Invalid public descriptor.")
            checked = self.rpc.call("getdescriptorinfo", [descriptor])
            if checked.get("hasprivatekeys") is not False or checked.get("isrange") is not True:
                raise CoreError("Import requires ranged public descriptors without private keys.")
            requests.append({"desc": checked["descriptor"], "timestamp": 0,
                             "active": True, "internal": index == 1, "range": [0, 1000]})
        self.rpc.call("createwallet", {"wallet_name": name, "disable_private_keys": True, "blank": True})
        result = self.rpc.call("importdescriptors", [requests], wallet=name, timeout=3600)
        if not isinstance(result, list) or len(result) != len(requests) or any(item.get("success") is not True for item in result):
            details = "; ".join(str(item.get("error", {}).get("message", "Import failed"))
                                for item in result if item.get("success") is not True) if isinstance(result, list) else "Invalid Core response"
            raise CoreError(f"Core could not finish the import: {details}. The new wallet remains loaded.")
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
        # Core chooses the wallet's default address type, including multisig.
        address = self.rpc.call("getnewaddress", {"label": label}, wallet=name)
        info = self.rpc.call("getaddressinfo", {"address": address}, wallet=name)
        return address, info

    def inspect_psbt(self, name, psbt):
        return {
            "decoded": self.rpc.call("decodepsbt", {"psbt": psbt}, wallet=name),
            "analysis": self.rpc.call("analyzepsbt", {"psbt": psbt}, wallet=name),
        }
