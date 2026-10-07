"""Config file handling and first-run setup wizard"""

import json
import os
import re
import shutil
import sys
import textwrap
from pathlib import Path
from time import sleep
from typing import ClassVar

import requests
from pypresence import DiscordNotFound, PyPresenceException
from pypresence.presence import Presence

from nxapi_cli.nxapi import (
    DEFAULT_PLAY_TIME,
    PLAY_TIME_MODES,
    PUBLIC_BASE_URL,
    NxapiClient,
    NxapiError,
    NxapiNotFound,
    is_nsaid,
    normalise_nsaid,
)
from nxapi_cli.ui import C, clear, err, ok, warn

default_config = {
    # Where to read presence from.
    "nsaid": "",
    "base_url": PUBLIC_BASE_URL,
    "url": "",  # optional full-URL override, wins over base_url + nsaid
    # Discord.
    "client_id": 1512043386327007253,
    "wait_seconds": 30,
    "hibernate_seconds": 600,  # clear presence after this long without a report
    "stale_seconds": 7200,
    "nsaid_prompt": True,
    # Elapsed timer.
    "show_timer": True,
    "accurate_timer": True,
    # Activity text.
    "show_only_in_game": True,
    "show_inactive_presence": False,
    "show_console": True,
    # Tooltip.
    "show_tooltip": True,
    "tooltip_as_status_line": True,
    "tooltip_session_start": False,
    "tooltip_title_id": False,
    # Play time.
    "play_time": "hour",
    # Friend code.
    "share_friend_code": False,
    "friend_code": "",
    "show_buttons": False,
    "one_button": True,
    "profile_url": "",
    "friend_url": "",
    # Cover art.
    "avatar_when_idle": True,
    "mii_icon": True,
    "prefer_dev_app": False,
}

CONFIG_FILENAME = "nxapicliconfig.json"
APP_NAME = "nxapi-cli"

# Referenced in the setup prompt: where presence comes from, how to get a
# server, and where accounts get linked.
NXAPI_AUTH_URL = "https://nxapi-auth.fancy.org.uk"
NXAPI_SETUP_URL = "https://gitlab.fancy.org.uk/samuel/nxapi"

# Dead options, stripped from configs on load.
RETIRED_OPTIONS = ("use_appname", "short_console_name", "tooltip_play_time")

# Renamed options, migrated on load so users keep their settings.
RENAMED_OPTIONS = {
    "hide_console_name": "show_console",  # inverted: show_console = not hide_console_name
    "add_friend_url": "profile_url",
    "add_friend_button": "show_buttons",
}

SEPARATOR = "=" * 25 + "\n"


_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _row_count(text, width):
    """How many terminal rows `text` takes up once wrapped to `width`.

    Menus redraw in place by walking the cursor back up, so this has to be the
    *visual* height. Getting it wrong garbles the screen, which is what happens
    on any terminal narrow enough to wrap a label.
    """
    plain = _ANSI_RE.sub("", text)
    if width <= 1:
        return max(1, len(plain))
    return max(1, len(textwrap.wrap(plain, width, break_long_words=True)) or 1)


def _term_width():
    return shutil.get_terminal_size((80, 24)).columns


def _read_key():
    """Block for one keypress. Returns 'up' / 'down' / 'space' / 'enter' / None."""
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getwch()
        if ch == "\xe0":
            return {"H": "up", "P": "down"}.get(msvcrt.getwch())
        if ch == " ":
            return "space"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            raise KeyboardInterrupt
        return None

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            if sys.stdin.read(1) == "[":
                return {"A": "up", "B": "down"}.get(sys.stdin.read(1))
            return None
        if ch == " ":
            return "space"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            raise KeyboardInterrupt
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _arrow_select(prompt, options, selected=0):
    """Arrow-key single-choice menu. Returns the index of the chosen option."""
    selected = max(0, min(selected, len(options) - 1))

    height = 0

    def render():
        nonlocal height
        lines = [
            f"{C.YELLOW}{C.BOLD}> {opt}{C.RESET}"
            if i == selected
            else f"  {C.GRAY}{opt}{C.RESET}"
            for i, opt in enumerate(options)
        ]
        width = _term_width()
        height = sum(_row_count(line, width) for line in lines)
        sys.stdout.write("\r\n".join(lines) + "\r\n")
        sys.stdout.flush()

    def move_up():
        if height:
            sys.stdout.write(f"\033[{height}A")
            sys.stdout.flush()

    print(prompt)
    render()
    while True:
        key = _read_key()
        if key == "up":
            selected = (selected - 1) % len(options)
        elif key == "down":
            selected = (selected + 1) % len(options)
        elif key == "enter":
            sys.stdout.write("\r\n")
            sys.stdout.flush()
            return selected
        else:
            continue
        move_up()
        render()


def _toggle_select(prompt, groups, values):
    """Grouped checklist menu. Category headers render but aren't selectable."""
    options = [(key, label) for _, items in groups for key, label in items]
    selected = 0
    height = 0

    def render():
        nonlocal height
        lines = []
        idx = 0
        for group_index, (title, items) in enumerate(groups):
            if group_index:
                lines.append("")
            lines.append(f"{C.BOLD}{C.CYAN}{title}{C.RESET}")
            for key, label in items:
                box = (
                    f"{C.GREEN}[x]{C.RESET}" if values[key] else f"{C.GRAY}[ ]{C.RESET}"
                )
                if idx == selected:
                    lines.append(f"{C.YELLOW}{C.BOLD}>{C.RESET} {box} {label}")
                else:
                    lines.append(f"  {box} {C.GRAY}{label}{C.RESET}")
                idx += 1
        width = _term_width()
        height = sum(_row_count(line, width) for line in lines)
        sys.stdout.write("\r\n".join(lines) + "\r\n")
        sys.stdout.flush()

    def move_up():
        if height:
            sys.stdout.write(f"\033[{height}A")
            sys.stdout.flush()

    print(prompt)
    render()
    while True:
        key = _read_key()
        if key == "up":
            selected = (selected - 1) % len(options)
        elif key == "down":
            selected = (selected + 1) % len(options)
        elif key == "space":
            values[options[selected][0]] = not values[options[selected][0]]
        elif key == "enter":
            sys.stdout.write("\r\n")
            sys.stdout.flush()
            return values
        else:
            continue
        move_up()
        render()


class PrepWork:
    def __init__(self):
        self.RPC = None
        self.config = {}
        self.config_path = self._resolve_config_path()
        self.session = requests.Session()

    @staticmethod
    def _config_dir():
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", "~")).expanduser() / APP_NAME
        return Path(f"~/.config/{APP_NAME}").expanduser()

    @staticmethod
    def _app_dir():
        # PyInstaller onefile builds run from a temp extraction dir, so use the
        # actual .exe's folder instead of cwd/__file__ when frozen.
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path.cwd()

    @staticmethod
    def _resolve_config_path():
        # Portable mode
        app_dir = PrepWork._app_dir()
        if (app_dir / "portable.txt").is_file():
            return app_dir / CONFIG_FILENAME

        preferred = PrepWork._config_dir() / CONFIG_FILENAME
        legacy_home = Path(f"~/{CONFIG_FILENAME}").expanduser()
        local = Path(CONFIG_FILENAME)
        if preferred.is_file():
            return preferred
        if legacy_home.is_file():
            preferred.parent.mkdir(parents=True, exist_ok=True)
            legacy_home.rename(preferred)
            return preferred
        if local.is_file():
            return local
        return preferred

    def read_config(self):
        if self.config_path.is_file():
            try:
                with self.config_path.open(mode="r") as f:
                    self.config = json.load(f)
            except json.JSONDecodeError:
                warn(
                    f"Config file {self.config_path} is corrupted, resetting to defaults."
                )
                self.config_path.unlink()
                self.config = default_config.copy()
                self.prompt_user()
                self.configure_options()
                return
            # Carry renamed options across rather than resetting them.
            renamed = [k for k in RENAMED_OPTIONS if k in self.config]
            for old in renamed:
                new = RENAMED_OPTIONS[old]
                value = self.config.pop(old)
                self.config[new] = not value if old == "hide_console_name" else value
                print(f"Config: {old} renamed to {new}")

            missing = {k: v for k, v in default_config.items() if k not in self.config}
            retired = [k for k in RETIRED_OPTIONS if k in self.config]
            for key in retired:
                del self.config[key]
            if missing or retired or renamed:
                self.config.update(missing)
                self.save_config()
                if missing:
                    print(
                        f"Config updated with {len(missing)} new default(s): "
                        f"{', '.join(missing)}"
                    )
                if retired:
                    print(f"Removed retired option(s): {', '.join(retired)}")
            self.config["wait_seconds"] = max(15, self.config["wait_seconds"])
            saved_nsaid = normalise_nsaid(self.config.get("nsaid"))
            if not saved_nsaid and not str(self.config.get("url") or "").strip():
                warn("No Nintendo account (NSA ID) is saved yet.")
                self.prompt_user()
            elif self.config["nsaid_prompt"] and not self.test_for_presence(
                silent=True
            ):
                err(
                    "No presence could be read for the saved NSA ID "
                    f'"{saved_nsaid or self.config.get("url")}".'
                )
                self.prompt_user()
        else:
            self.config = default_config.copy()
            print(
                f"{C.GRAY}No config file found - a new one will be saved to "
                f"{self.config_path}{C.RESET}"
            )
            self.prompt_user()
            self.configure_options()

    def prompt_user(self):
        clear()
        print(f"\n{C.BOLD}{C.CYAN}===== {APP_NAME} Setup ====={C.RESET}\n")
        print(
            f"{C.GRAY}This script reads your presence from an nxapi presence server, so one "
            f"has to exist{C.RESET}\n"
            f"{C.GRAY}first and your console has to report to it. Want to set this up?{C.RESET}\n"
            f"\n"
            f"  {C.BOLD}Set up and link your account:{C.RESET} {C.CYAN}{NXAPI_AUTH_URL}{C.RESET}\n"
            f"\n"
            f"{C.GRAY}Then paste the presence URL for your account, or just the NSA ID."
            f" It looks like:{C.RESET}\n"
            f"\n"
            f"  {C.WHITE}{PUBLIC_BASE_URL}/api/presence/<your-nsaid>{C.RESET}\n"
            f"\n"
            f"{C.YELLOW}Press Ctrl+C to quit.{C.RESET}\n"
        )
        print(SEPARATOR)
        while True:
            try:
                answer = input(
                    f"{C.BOLD}Presence URL or NSA ID{C.RESET} "
                    f"{C.GRAY}(for example: 0123456789abcdef):{C.RESET} "
                ).strip()
            except EOFError:
                answer = ""
            if not answer:
                warn("Nothing entered.\n")
                continue
            if answer.lower() in ("q", "quit", "exit"):
                raise KeyboardInterrupt
            nsaid = normalise_nsaid(answer)
            if answer.lower().startswith(("http://", "https://")):
                # A full URL: keep it as-is, so custom servers keep working.
                if not nsaid or not is_nsaid(nsaid):
                    warn(
                        f'"{answer}" doesn\'t look like a presence URL - expected '
                        f"{PUBLIC_BASE_URL}/api/presence/<nsaid>"
                    )
                    continue
                self.config["url"] = answer.rstrip("/")
            elif is_nsaid(nsaid):
                self.config["nsaid"] = nsaid
                self.config["url"] = ""
                self.config["base_url"] = PUBLIC_BASE_URL
            else:
                warn(f'"{answer}" doesn\'t look like an NSA ID (16 hex digits).')
                continue
            if self.test_for_presence():
                self.save_config()
                break
            print(f"{C.GRAY}Please try again.{C.RESET}\n")

    # Boolean options shown on the first-run toggle screen, grouped by category.
    _OPTION_GROUPS: ClassVar = [
        (
            "Connection",
            [
                (
                    "nsaid_prompt",
                    "Re-prompt for the NSA ID if presence can't be read on startup",
                ),
            ],
        ),
        (
            "Elapsed timer",
            [
                ("show_timer", "Display time elapsed in the presence"),
                (
                    "accurate_timer",
                    "Sync the timer to the session time the presence server reports",
                ),
            ],
        ),
        (
            "Activity text",
            [
                (
                    "show_only_in_game",
                    "Only update presence when a game is running (hide on the Home Menu)",
                ),
                (
                    "show_inactive_presence",
                    'Show "Not playing" when the console is on but no game is running',
                ),
                (
                    "show_console",
                    "Show the console name below the game name",
                ),
            ],
        ),
        (
            "Links",
            [
                (
                    "share_friend_code",
                    "Show your friend code on the presence (set it below)",
                ),
                (
                    "show_buttons",
                    "Add 'View profile' and 'Add friend' buttons to the presence",
                ),
                (
                    "one_button",
                    "Only ever show one button, linking to your nxapi profile",
                ),
            ],
        ),
        (
            "Tooltip",
            [
                (
                    "show_tooltip",
                    "Show a details tooltip when hovering over the large image",
                ),
                (
                    "tooltip_as_status_line",
                    "Show the tooltip contents on the status line instead of as a hover tooltip",
                ),
                (
                    "tooltip_session_start",
                    "Include when the session started in the tooltip",
                ),
                (
                    "tooltip_title_id",
                    "Include the title ID (e.g. 0400c3f00006e000) in the tooltip",
                ),
            ],
        ),
        (
            "Cover art",
            [
                (
                    "avatar_when_idle",
                    "Use the Nintendo account avatar when no game is running",
                ),
                (
                    "mii_icon",
                    "Show the Mii icon in the bottom-right corner of the presence",
                ),
                (
                    "prefer_dev_app",
                    "Use Discord dev app images instead of Nintendo's box art",
                ),
            ],
        ),
    ]

    # Non-boolean values asked for after the toggle screen.
    _TEXT_OPTIONS: ClassVar = [
        (
            "friend_code",
            (
                "Your Nintendo Switch friend code, so people can add you "
                "(e.g. SW-1234-5678-9012)"
            ),
        ),
        (
            "profile_url",
            (
                "Your nxapi-auth profile page, which is what the 'View profile' button "
                "links to"
            ),
        ),
        (
            "friend_url",
            (
                "Optional: a Nintendo friend link, if you'd rather not have it "
                "looked up from the profile page"
            ),
        ),
    ]

    def configure_options(self):
        """Let the user pick the play time string."""
        clear()
        print(f"\n{C.BOLD}{C.CYAN}===== First-time Setup: Options ====={C.RESET}\n")
        values = {
            key: bool(self.config.get(key, default_config[key]))
            for _, items in self._OPTION_GROUPS
            for key, _ in items
        }
        values = _toggle_select(
            f"{C.BOLD}View and toggle any options below, then press enter to continue.{C.RESET}\n"
            f"{C.GRAY}Use arrow keys to navigate, "
            f"{C.WHITE}{C.BOLD}space{C.RESET}{C.GRAY} to toggle, "
            f"{C.WHITE}{C.BOLD}enter{C.RESET}{C.GRAY} to confirm.{C.RESET}\n",
            self._OPTION_GROUPS,
            values,
        )
        self.config.update(values)

        keys = [key for key, _ in PLAY_TIME_MODES]
        current = str(self.config.get("play_time") or DEFAULT_PLAY_TIME)
        index = (
            keys.index(current) if current in keys else keys.index(DEFAULT_PLAY_TIME)
        )
        chosen = _arrow_select(
            f"\n{C.BOLD}How should play time be shown?{C.RESET}\n"
            f"{C.GRAY}Arrow keys to move, enter to select.{C.RESET}\n",
            [label for _, label in PLAY_TIME_MODES],
            index,
        )
        self.config["play_time"] = keys[chosen]

        for key, label in self._TEXT_OPTIONS:
            current = str(self.config.get(key) or "")
            print(
                f"\n{C.BOLD}{label}{C.RESET}\n"
                f"{C.GRAY}Currently: {current or '(not set)'}{C.RESET}\n"
                f"{C.GRAY}Leave blank to keep it, or type - to clear.{C.RESET}"
            )
            try:
                answer = input(f"{C.BOLD}> {C.RESET}").strip()
            except EOFError:
                answer = ""
            if answer == "-":
                self.config[key] = ""
            elif answer:
                self.config[key] = answer

        self.save_config()
        print(SEPARATOR)
        print(
            f"{C.GRAY}Your settings can be found at {C.RESET}"
            f"{C.WHITE}{self.config_path}{C.RESET}\n"
        )

    def test_for_presence(self, silent=False) -> bool:
        """Try one poll of the presence server. Reports why it failed."""
        try:
            client = NxapiClient(self.config, session=self.session)
            snapshot = client.fetch()
        except NxapiNotFound as e:
            if not silent:
                err(str(e))
            return False
        except NxapiError as e:
            if not silent:
                err(f"Could not read presence: {e}")
            return False
        if not silent:
            where = snapshot.title_name or snapshot.state.lower()
            ok(
                f'Reading presence for "{snapshot.account_name or snapshot.nsaid}": {where}'
            )
        return True

    def save_config(self):
        self.config["nsaid"] = normalise_nsaid(self.config.get("nsaid"))
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open(mode="w+") as f:
            json.dump(self.config, f, indent=4)

    def connect_to_discord(self):
        while True:
            try:
                self.RPC = Presence(self.config["client_id"])
                self.RPC.connect()
                ok("Successfully connected to Discord client")
                break
            except (DiscordNotFound, ConnectionRefusedError, PyPresenceException) as e:
                err(f'Could not connect to Discord: "{e}"')
                print(
                    f"{C.GRAY}Ensure Discord is running. If {APP_NAME} is a systemd "
                    f"service, Discord must be running in the same user "
                    f"session.{C.RESET}"
                )
                sleep(20)
