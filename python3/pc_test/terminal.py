"""TTY helpers."""

from __future__ import annotations

import sys


def read_key(*, abort_on_ctrl_c: bool = False) -> bool:
    """Read one key in raw mode.

    Returns False if the user pressed Ctrl-C and abort_on_ctrl_c is True.
    Otherwise returns True.
    """
    if not sys.stdin.isatty():
        return True
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except KeyboardInterrupt:
        print(flush=True)
        if abort_on_ctrl_c:
            return False
        raise
    except Exception:
        return True
    print(flush=True)
    if abort_on_ctrl_c and ch == "\x03":
        return False
    return True
