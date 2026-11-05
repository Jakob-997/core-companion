"""Explicit transports: curl owns HTTPS/SOCKS; Core owns Bitcoin networking."""

import re
import secrets

from .linux_cold import _system_tool


def checked_proxy(proxy):
    if not isinstance(proxy, str) or not re.fullmatch(r"127\.0\.0\.1:[0-9]{1,5}", proxy):
        raise ValueError("Tor requires a local SOCKS proxy.")
    if not 1 <= int(proxy.rsplit(":", 1)[1]) <= 65535:
        raise ValueError("Invalid Tor SOCKS port.")
    return proxy


def curl_command(url, destination, *, proxy=None, limit=2 * 1024 * 1024, timeout=120):
    executable = _system_tool("curl")
    if not executable:
        raise ValueError("Install curl before downloading Bitcoin Core.")
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS downloads are permitted.")
    # -q must be first. Explicit --noproxy defeats inherited NO_PROXY bypasses.
    command = [executable, "-q", "--fail", "--silent", "--show-error", "--location",
               "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "3",
               "--connect-timeout", "45", "--max-time", str(timeout),
               "--max-filesize", str(limit), "--noproxy", "", "--proxy",
               "socks5h://" + checked_proxy(proxy) if proxy else ""]
    if proxy:
        identity = secrets.token_hex(16)
        command += ["--proxy-user", identity + ":" + identity]
    return [*command, "--output", str(destination), "--url", url]


def core_tor_arguments(proxy):
    proxy = checked_proxy(proxy)
    return [f"-proxy={proxy}", f"-onion={proxy}", "-proxyrandomize=1",
            "-onlynet=onion", "-listen=0", "-listenonion=0", "-discover=0",
            "-dns=0", "-dnsseed=0", "-fixedseeds=1", "-natpmp=0"]


def assert_core_tor(node, proxy):
    networks = {item["name"]: item for item in node.get("networks", [])}
    for name in ("ipv4", "ipv6", "onion"):
        entry = networks.get(name, {})
        if entry.get("proxy") != checked_proxy(proxy):
            raise ValueError("Core did not confirm the required Tor proxy.")
        if name != "onion" and entry.get("limited") is not True:
            raise ValueError("Core permits connections outside the onion network.")
    if node.get("localaddresses"):
        raise ValueError("Core is advertising a listening address in Tor-only mode.")
