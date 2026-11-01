"""Wallet orchestration only: Core owns balances, addresses and transactions."""

from decimal import Decimal


def btc(value):
    return f"{Decimal(str(value)):.8f}"


class WalletService:
    def __init__(self, rpc):
        self.rpc = rpc

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
