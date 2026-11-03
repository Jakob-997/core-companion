"""Wallet orchestration only: Core owns balances, addresses and transactions."""

from decimal import Decimal
import re
from .rpc import CoreError
from .public_wallet import expand_public_descriptors


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
        descriptors = expand_public_descriptors(self.rpc, descriptors)
        requests = [{"desc": descriptor, "timestamp": 0, "active": True,
                     "internal": index == 1, "range": [0, 1000]}
                    for index, descriptor in enumerate(descriptors)]
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

    def create_psbt(self, name, recipient, amount, fee_rate):
        address = self.rpc.call("validateaddress", [recipient])
        if address.get("isvalid") is not True:
            raise CoreError("Enter a valid Bitcoin recipient address.")
        try:
            amount, fee_rate = Decimal(str(amount)), Decimal(str(fee_rate))
            if (not amount.is_finite() or not fee_rate.is_finite() or
                    not 0 < amount <= 21000000 or not 0 < fee_rate <= 10000 or
                    amount * 100000000 != int(amount * 100000000)):
                raise ValueError()
        except (ValueError, ArithmeticError):
            raise CoreError("Enter a positive BTC amount (up to 8 decimals) and fee rate in sat/vB.") from None
        params = {
            "inputs": [], "outputs": [{recipient: str(amount)}],
            "options": {"includeWatching": True, "add_inputs": True, "fee_rate": str(fee_rate), "lockUnspents": False},
            "bip32derivs": True,
        }
        # Export PSBTv0 for broad signer compatibility; Core 32 defaults to v2.
        if self.rpc.call("getnetworkinfo").get("version", 0) >= 320000:
            params["psbt_version"] = 0
        funded = self.rpc.call("walletcreatefundedpsbt", params, wallet=name)
        return dict(funded, decoded=self.rpc.call("decodepsbt", [funded["psbt"]]))

    def finalize_psbt(self, name, psbt):
        finalized = self.rpc.call("finalizepsbt", [psbt], wallet=name)
        if finalized.get("complete") is not True or not finalized.get("hex"):
            raise CoreError("The PSBT is not fully signed. Return it to the required signers.")
        transaction = self.rpc.call("decoderawtransaction", [finalized["hex"]])
        acceptance = self.rpc.call("testmempoolaccept", [[finalized["hex"]]])
        return {"hex": finalized["hex"], "transaction": transaction, "acceptance": acceptance}

    def broadcast(self, transaction_hex):
        return self.rpc.call("sendrawtransaction", [transaction_hex])
