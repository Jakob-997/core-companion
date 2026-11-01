"""Entry point for the desktop app and its short-lived cold helper."""

import sys


def _prepare_cold_helper():
    """Give the signer its own process group and disable core dumps early."""
    if sys.platform != "linux":
        raise SystemExit("The cold signer helper currently requires Linux.")
    import ctypes
    import os
    import resource

    try:
        os.setsid()
    except OSError as exc:
        raise SystemExit("Could not isolate the cold signer process group.") from exc
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        # PR_SET_DUMPABLE = 4. This also prevents same-UID ptrace access on Linux.
        if ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE) failed")
    except (AttributeError, OSError) as exc:
        raise SystemExit("Could not disable dumpable memory for the cold signer.") from exc


if "--cold-helper" in sys.argv:
    _prepare_cold_helper()

from companion.ui import main


if __name__ == "__main__":
    main()
