"""Local-only Bitcoin Core JSON-RPC. No wallet files or private keys are read."""

import base64
import json
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class CoreError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CoreRPC:
    # This is an application guardrail, not a server-side permission boundary.
    METHODS = frozenset({
        "getnetworkinfo", "getblockchaininfo", "listwallets", "getwalletinfo",
        "getbalances", "listtransactions", "listreceivedbyaddress",
        "getnewaddress", "getaddressinfo", "decodepsbt", "analyzepsbt",
        "getdescriptorinfo", "createwallet", "importdescriptors",
        "listdescriptors",
    })

    def __init__(self, port, cookie_path):
        try:
            self.port = int(port)
        except (ValueError, TypeError):
            raise CoreError("Enter a valid RPC port.") from None
        if not 1 <= self.port <= 65535:
            raise CoreError("RPC port must be between 1 and 65535.")
        self.cookie_path = Path(cookie_path).expanduser()
        # Never inherit system HTTP proxies or forward credentials on redirects.
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def call(self, method, params=None, wallet=None, *, timeout=12):
        if method not in self.METHODS:
            raise CoreError("This RPC operation is not enabled.")
        try:
            with self.cookie_path.open(encoding="ascii") as cookie_file:
                cookie = cookie_file.read(4097).strip()
        except (OSError, UnicodeError):
            raise CoreError("Could not find Core's local connection. Start Core on this computer and try again.") from None
        if len(cookie) > 4096 or ":" not in cookie or any(ord(c) < 33 or ord(c) > 126 for c in cookie):
            raise CoreError("Core's local connection could not be read. Restart Core and try again.")
        path = "/" if wallet is None else "/wallet/" + quote(wallet, safe="")
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps({"jsonrpc": "2.0", "id": "companion", "method": method, "params": {} if params is None else params}, allow_nan=False).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(cookie.encode()).decode()},
        )
        try:
            response = self.opener.open(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code == 401:
                exc.close()
                raise CoreError("Core did not accept the local connection. Restart Core and try again.") from None
            if exc.code not in (400, 404, 500):
                exc.close()
                raise CoreError(f"Core returned HTTP {exc.code}.") from None
            response = exc
        except (URLError, OSError, TimeoutError):
            raise CoreError("Cannot reach Bitcoin Core. Check that it is running and local RPC is enabled.") from None
        try:
            with response:
                body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise CoreError("Core response exceeded the 8 MiB limit.")
            result = json.loads(body, parse_float=Decimal, parse_constant=_reject_constant)
        except (ValueError, OSError, TimeoutError):
            raise CoreError("Core returned an unreadable response.") from None
        if not isinstance(result, dict) or result.get("id") != "companion":
            raise CoreError("Unexpected RPC response.")
        if result.get("error"):
            error = result["error"]
            if not isinstance(error, dict):
                raise CoreError("Core returned an invalid error response.")
            raise CoreError(f"Core error {error.get('code')}: {error.get('message', 'Request failed')}")
        if "result" not in result:
            raise CoreError("Core response is missing a result.")
        return result["result"]


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")
