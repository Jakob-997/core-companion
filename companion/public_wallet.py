"""Public wallet interchange. Core validates descriptors and expands multipaths."""

import hashlib
import re
from .rpc import CoreError

_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


# SLIP-132 prefixes; Core descriptors use canonical BIP32 xpub serialization.
_PUBLIC_VERSIONS = {
    "xpub": bytes.fromhex("0488b21e"), "ypub": bytes.fromhex("049d7cb2"),
    "zpub": bytes.fromhex("04b24746"), "Ypub": bytes.fromhex("0295b43f"),
    "Zpub": bytes.fromhex("02aa7ed3"),
}
_XPUB_VERSION = _PUBLIC_VERSIONS["xpub"]


def normalize_slip132_public_key(value):
    """Normalize a mainnet SLIP-132 account public key to descriptor xpub form."""
    match = re.match(r"(xpub|ypub|zpub|Ypub|Zpub)", value)
    if match is None or not re.fullmatch(
        r"(?:xpub|ypub|zpub|Ypub|Zpub)[1-9A-HJ-NP-Za-km-z]{80,120}", value
    ):
        raise CoreError("Enter a supported mainnet extended public key.")
    prefix = match.group(1)
    number = 0
    try:
        for character in value:
            number = number * 58 + _BASE58.index(character)
    except ValueError:
        raise CoreError("The extended public key contains an invalid Base58 character.") from None
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    raw = b"\0" * (len(value) - len(value.lstrip("1"))) + raw
    if (len(raw) != 82 or raw[:4] != _PUBLIC_VERSIONS[prefix]
            or hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] != raw[-4:]
            or raw[45] not in (2, 3)):
        raise CoreError("The extended public key version, checksum, or public key is invalid.")
    payload = _XPUB_VERSION + raw[4:-4]
    encoded = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    leading_zeroes = len(encoded) - len(encoded.lstrip(b"\0"))
    number = int.from_bytes(encoded, "big")
    characters = []
    while number:
        number, remainder = divmod(number, 58)
        characters.append(_BASE58[remainder])
    return "1" * leading_zeroes + "".join(reversed(characters))


def public_key_descriptor(value):
    """Convert a bare single-signature xpub/ypub/zpub to a Core descriptor.

    Core validates descriptors and computes checksums. SLIP-132 version bytes
    are normalized because descriptor keys use BIP32 xpub serialization.
    """
    match = re.fullmatch(
        r"(xpub|ypub|zpub)[1-9A-HJ-NP-Za-km-z]{80,120}", value
    )
    if match is None:
        return value
    key = normalize_slip132_public_key(value)
    body = f"wpkh({key}/<0;1>/*)"
    return f"sh({body})" if match.group(1) == "ypub" else body

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
