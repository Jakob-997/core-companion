"""Small BIP39 boundary for the cold-signer prototype.

This module deliberately delegates mnemonic and BIP32 master-key operations to
Trezor's reference `python-mnemonic` package. Python does not guarantee erasure
of secret values; call it only inside the short-lived seed helper process.
"""

import hashlib
import os
import secrets
import stat
import unicodedata
from pathlib import Path

from mnemonic import Mnemonic


WORD_COUNTS = {12: 16, 15: 20, 18: 24, 21: 28, 24: 32}
MAX_WALLET_BYTES = 256 * 1024 * 1024
_DOMAIN = b"Core Companion BIP39 entropy v1\x00"


class SeedError(ValueError):
    """Invalid or unavailable seed-generation input."""


def hash_wallet_dat(path):
    """Return SHA-256 of a regular, bounded wallet.dat file."""
    wallet_path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(wallet_path, flags)
    except OSError as exc:
        raise SeedError("Cannot safely open Core's temporary wallet file.") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_WALLET_BYTES:
            raise SeedError("Core's temporary wallet file has an unexpected size or type.")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as wallet_file:
            while chunk := wallet_file.read(1024 * 1024):
                digest.update(chunk)
        return digest.digest()
    finally:
        os.close(fd)


def entropy_from_sources(wallet_digest, word_count=24, dice_rolls="", os_entropy=None):
    """Mix wallet-file hash, Linux OS randomness, and optional 1–6 dice rolls.

    The OS contribution is always 32 bytes from Python's system CSPRNG. The
    digest is truncated only to a standard BIP39 entropy size, selected by word
    count. Dice are mixed as an optional independent contribution; they are not
    treated as a replacement for the OS CSPRNG.
    """
    if word_count not in WORD_COUNTS:
        raise SeedError("BIP39 word count must be 12, 15, 18, 21, or 24.")
    os_entropy = secrets.token_bytes(32) if os_entropy is None else os_entropy
    digest = hashlib.sha256(entropy_material(wallet_digest, os_entropy, dice_rolls)).digest()
    return digest[:WORD_COUNTS[word_count]]


def entropy_material(wallet_digest, os_entropy, dice_rolls=""):
    """The exact bytes hashed for generation and displayed for reproduction."""
    if any(not isinstance(value, bytes) or len(value) != 32 for value in (wallet_digest, os_entropy)):
        raise SeedError("Wallet hash and OS randomness must each be 32 bytes.")
    dice = "".join(str(dice_rolls).split())
    if any(face not in "123456" for face in dice):
        raise SeedError("Dice input may contain only rolls from 1 to 6.")
    if len(dice) > 4096:
        raise SeedError("Dice input is too long.")
    dice_bytes = dice.encode("ascii")
    return (
        _DOMAIN
        + len(wallet_digest).to_bytes(2, "big") + wallet_digest
        + len(os_entropy).to_bytes(2, "big") + os_entropy
        + len(dice_bytes).to_bytes(4, "big") + dice_bytes
    )


def phrase_from_entropy(entropy):
    """Encode standard-length entropy with Trezor's English BIP39 wordlist."""
    if not isinstance(entropy, bytes) or len(entropy) not in WORD_COUNTS.values():
        raise SeedError("Entropy must be 16, 20, 24, 28, or 32 bytes.")
    return Mnemonic("english").to_mnemonic(entropy)


def normalize_phrase(phrase):
    normalized = unicodedata.normalize("NFKD", str(phrase)).casefold()
    return " ".join(normalized.strip().split())


def validate_phrase(phrase):
    """Return normalized English words, or raise when length/checksum is invalid."""
    normalized = normalize_phrase(phrase)
    if not Mnemonic("english").check(normalized):
        raise SeedError("Enter a valid English BIP39 phrase with a correct checksum.")
    return normalized


def final_word_candidates(partial_phrase):
    """List checksum-valid final words; BIP39 often leaves multiple candidates."""
    words = normalize_phrase(partial_phrase).split()
    if len(words) not in (11, 14, 17, 20, 23):
        raise SeedError("Enter all but the final word of a 12, 15, 18, 21, or 24-word phrase.")
    mnemonic = Mnemonic("english")
    candidates = []
    for word in mnemonic.wordlist:
        if mnemonic.check(" ".join((*words, word))):
            candidates.append(word)
    return candidates


def master_xprv(phrase, bip39_passphrase=""):
    """Return the BIP32 root xprv using Trezor's BIP39/BIP32 helpers."""
    normalized = validate_phrase(phrase)
    seed = Mnemonic.to_seed(normalized, passphrase=str(bip39_passphrase))
    return Mnemonic.to_hd_master_key(seed, testnet=False)
