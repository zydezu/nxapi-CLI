"""Small ANSI terminal helpers for the setup wizard.

Ported from the `core/ui.py` colour/keyhint helpers in
https://github.com/zydezu/steamplaydataeditor.
"""


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
