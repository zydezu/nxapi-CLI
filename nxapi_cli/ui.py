"""Small ANSI terminal helpers for the setup wizard.

Ported from the `core/ui.py` colour/keyhint helpers in
https://github.com/zydezu/steamplaydataeditor.
"""

import sys


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"


def clear() -> None:
    print("\033[H\033[J", end="", flush=True)


def stdin_is_interactive() -> bool:
    """True when we can actually prompt the terminal"""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        # ValueError: stdin detached/closed underneath us.
        return False


def require_interactive(what: str) -> None:
    """Abort with an actionable message if we can't prompt."""
    err(f"Cannot prompt for {what}: no interactive terminal (stdin is not a TTY).")
    print(
        f"{C.GRAY}This usually means running under a service manager. Edit the "
        f"config file directly, or run the setup wizard from a terminal.{C.RESET}"
    )
    raise SystemExit(1)


def key_opt(key: str, label: str, note: str = "") -> str:
    """Format a coloured key hint: [E]dit  or  [E]dit (3)"""
    note_str = f" {C.GRAY}({note}){C.RESET}" if note else ""
    return f"[{C.YELLOW}{key}{C.RESET}]{label}{note_str}"


def ok(msg: str) -> None:
    print(f"{C.GREEN}✓  {msg}{C.RESET}")


def err(msg: str) -> None:
    print(f"{C.RED}✗  {msg}{C.RESET}")


def warn(msg: str) -> None:
    print(f"{C.YELLOW}⚠  {msg}{C.RESET}")
