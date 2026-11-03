"""Public wallet interchange. Core validates descriptors and expands multipaths."""

import hashlib
import re
from .rpc import CoreError

_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def public_key_descriptor(value):
    """Convert an account xpub/ypub/zpub to a receive/change descriptor.

    Only SLIP132 version bytes change here. Key validation, derivation and
    descriptor checksums remain Bitcoin Core operations.
    """
    if not re.fullmatch(r"(?:xpub|ypub|zpub)[1-9A-HJ-NP-Za-km-z]{80,120}", value):
        return value
    number = 0
    for character in value:
        number = number * 58 + _BASE58.index(character)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    raw = b"\0" * (len(value) - len(value.lstrip("1"))) + raw
    if len(raw) != 82 or hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] != raw[-4:]:
        raise CoreError("The extended public key checksum is invalid.")
    versions = {bytes.fromhex("0488b21e"): "wpkh", bytes.fromhex("049d7cb2"): "sh-wpkh",
                bytes.fromhex("04b24746"): "wpkh"}
    kind = versions.get(raw[:4])
    if kind is None or raw[45] not in (2, 3):
        raise CoreError("Import a mainnet extended public key, without private key material.")
    payload = bytes.fromhex("0488b21e") + raw[4:-4]
    encoded = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    number = int.from_bytes(encoded, "big")
    key = ""
    while number:
        number, remainder = divmod(number, 58)
        key = _BASE58[remainder] + key
    body = "wpkh(" + key + "/<0;1>/*)"
    return "sh(" + body + ")" if kind == "sh-wpkh" else body


def expand_public_descriptors(rpc, descriptors):
    if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= 2:
        raise CoreError("Import a public descriptor, xpub, zpub, or a receive/change descriptor pair.")
    expanded = []
    for descriptor in descriptors:
        if not isinstance(descriptor, str) or not descriptor.strip() or len(descriptor) > 20000:
            raise CoreError("Invalid public descriptor.")
        checked = rpc.call("getdescriptorinfo", [public_key_descriptor(descriptor.strip())])
        if checked.get("hasprivatekeys") is not False or checked.get("isrange") is not True or checked.get("issolvable") is not True:
            raise CoreError("Import requires ranged public descriptors without private keys.")
        expanded.extend(checked.get("multipath_expansion", [checked["descriptor"]]))
    if not 1 <= len(expanded) <= 2 or len(set(expanded)) != len(expanded):
        raise CoreError("Use one receive/change multipath descriptor, or a distinct receive/change pair.")
    return expanded


def combined_public_descriptor(rpc, descriptors):
    """Combine only a verified /0/* and /1/* pair, with a Core checksum."""
    if len(descriptors) != 2:
        return "\n".join(descriptors)
    receive, change = [value.split("#", 1)[0] for value in descriptors]
    if "/0/*" not in receive or receive.replace("/0/*", "/1/*") != change:
        return "\n".join(descriptors)
    candidate = receive.replace("/0/*", "/<0;1>/*")
    checked = rpc.call("getdescriptorinfo", [candidate])
    if checked.get("hasprivatekeys") is not False or checked.get("multipath_expansion") != descriptors:
        raise CoreError("Core could not verify the combined receive/change descriptor.")
    return candidate + "#" + checked["checksum"]
