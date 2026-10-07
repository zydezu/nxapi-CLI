"""Nintendo Switch presence client for nxapi presence servers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from time import time
from urllib.parse import urlsplit

import requests

from nxapi_cli.ui import C, ok, warn

PUBLIC_BASE_URL = "https://nxapi-presence.fancy.org.uk"
DEFAULT_TIMEOUT = 15

# Discord dev-app asset key
IDLE_ASSET = "home_menu"

headers = {"User-Agent": "nxapi-cli/1.0 (Switch presence via nxapi)"}

_LABEL_WIDTH = 12  # widest label is "Friend code:"

# PresencePlatform, as defined by the presence server.
PLATFORM_NAMES = {1: "Nintendo Switch", 2: "Nintendo Switch 2"}
DEFAULT_PLATFORM = 1

# PresenceState: ONLINE/PLAYING in an app, INACTIVE at the Home Menu.
ONLINE_STATES = frozenset({"ONLINE", "PLAYING"})
IDLE_STATES = frozenset({"INACTIVE"})

_NSAID_RE = re.compile(r"^[0-9a-f]{16}$")
_TITLE_ID_RE = re.compile(r"/apps/([0-9a-f]{16})", re.IGNORECASE)
_URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_FRIEND_CODE_RE = re.compile(r"^(?:sw-?)?(\d{4})-?(\d{4})-?(\d{4})$", re.IGNORECASE)

# Play time modes, mirroring nxapi's "Play time" dropdown labels.
PLAY_TIME_MODES = (
    ("hidden", "Never show play time"),
    ("nintendo", "Show play time as it appears on a Nintendo Switch console"),
    ("hour", "Show approximate play time (nearest hour)"),
    ("hour_since", "Show approximate play time (nearest hour) with first played date"),
    ("approx5", "Show approximate play time (nearest 5 hours)"),
    (
        "approx5_since",
        "Show approximate play time (nearest 5 hours) with first played date",
    ),
    ("exact", "Show exact play time"),
    ("exact_since", "Show exact play time with first played date"),
)
DEFAULT_PLAY_TIME = "hour"
PLAY_TIME_LABELS = dict(PLAY_TIME_MODES)

# Discord renders at most two buttons on an activity.
MAX_BUTTONS = 2


class NxapiError(Exception):
    """Base class for anything that stops us reading a presence."""


class NxapiUnavailable(NxapiError):
    """The presence server is unreachable, throttling us, or erroring."""


class NxapiNotFound(NxapiError):
    """The server has no presence data for this NSA ID (HTTP 404)."""


class NxapiBadResponse(NxapiError):
    """The server answered, but not with anything we can read."""


def _log(label, value=""):
    """Dim, table-aligned debug line: 'label      value'."""
    padded = label.ljust(_LABEL_WIDTH)
    if value:
        print(f"{C.GRAY}{padded}{C.RESET} {value}")
    else:
        print(f"{C.GRAY}{label}{C.RESET}")


def normalise_nsaid(value) -> str:
    """Accept a bare NSA ID or a whole presence URL and return the NSA ID.

    Take the last path segment (URLs).
    """
    text = str(value or "").strip().strip("\"'")
    if not text:
        return ""
    if _URL_RE.match(text) or "/" in text:
        text = text.rstrip("/").split("?", 1)[0].rsplit("/", 1)[-1]
    return text.replace("-", "").replace(" ", "").lower()


def is_nsaid(value) -> bool:
    """True if `value` normalises to a 16-hex-digit NSA ID."""
    return _NSAID_RE.match(normalise_nsaid(value)) is not None


def normalise_friend_code(value) -> str:
    """'1234-5678-9012' / 'SW123456789012' -> 'SW-1234-5678-9012'. '' if invalid."""
    match = _FRIEND_CODE_RE.match(str(value or "").strip())
    if not match:
        return ""
    return "SW-" + "-".join(match.groups())


def _hrduration(minutes) -> str:
    """nxapi's hrduration(): 16989 -> '283 hours, 9 minutes'. Takes minutes."""
    minutes = int(minutes)
    hours, remainder = divmod(minutes, 60)
    if hours >= 1:
        text = f"{hours} hour" + ("" if hours == 1 else "s")
        if remainder:
            text += f", {remainder} minute" + ("" if remainder == 1 else "s")
        return text
    return f"{remainder} minute" + ("" if remainder == 1 else "s")


def _approximate_minutes(minutes) -> int:
    """Nearest hour below 10 hours, nearest 5 hours above - as nxapi does it."""
    minutes = int(minutes)
    return (minutes // 60) * 60 if minutes < 600 else (minutes // 300) * 300


def _plural(count, word) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _first_played_text(first_played_at):
    """'First played 3 hours ago' - used by the 'as on a console' mode."""
    now = time()
    minutes = int(now // 60) - int(first_played_at // 60)
    if minutes <= 0:
        return None
    if minutes <= 60:
        return f"First played {_plural(minutes, 'minute')} ago"
    hours = int(now // 3600) - int(first_played_at // 3600)
    if hours <= 24:
        return f"First played {_plural(hours, 'hour')} ago"
    days = int(now // 86400) - int(first_played_at // 86400)
    return f"First played {_plural(days, 'day')} ago"


def play_time_text(mode, total_minutes, first_played_at):
    """The play-time line for the current `mode`, or None to show nothing."""
    if mode == "hidden" or total_minutes is None or total_minutes < 0:
        return None
    total_minutes = int(total_minutes)

    if total_minutes < 60 and mode in (
        "hour",
        "hour_since",
        "approx5",
        "approx5_since",
    ):
        return None

    if mode == "nintendo":
        days_played = (
            int(time() // 86400) - int(first_played_at // 86400)
            if first_played_at
            else 0
        )
        if days_played <= 10:
            return _first_played_text(first_played_at) if first_played_at else None
        if total_minutes < 60:
            return "Played for a little while"
        return f"Played for {_hrduration(_approximate_minutes(total_minutes))} or more"

    if mode in ("approx5", "approx5_since"):
        text = f"Played for {_hrduration(_approximate_minutes(total_minutes))} or more"
    elif mode in ("hour", "hour_since"):
        # Round down to a whole hour, then render in hours.
        text = f"Played for {_hrduration((total_minutes // 60) * 60)}"
    else:  # exact / exact_since
        if total_minutes < 1:
            return None
        text = f"Played for {_hrduration(total_minutes)}"

    if mode.endswith("_since"):
        if not first_played_at:
            return f"{text} since now"
        played = datetime.fromtimestamp(first_played_at, tz=timezone.utc)
        return f"{text} since {played.strftime('%-d %b %Y')}"
    return text


def format_ago(seconds) -> str:
    """3660 -> '1h 1m ago'."""
    if seconds is None or seconds < 0:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        remainder = minutes % 60
        return f"{hours}h {remainder}m ago" if remainder else f"{hours}h ago"
    return f"{hours // 24}d ago"


def _profile_endpoint(profile_url):
    """'https://host/profile/<token>' -> 'https://host/api/profile/<token>'.

    Returns None for anything that doesn't look like an nxapi-auth profile page.
    """
    parts = urlsplit(str(profile_url or "").strip())
    if parts.scheme not in ("http", "https"):
        return None
    token = parts.path.rstrip("/").rsplit("/", 1)[-1]
    if not token or token in ("profile", ""):
        return None
    return f"{parts.scheme}://{parts.netloc}/api/profile/{token}"


def _parse_timestamp(value):
    """Parse an ISO 8601 timestamp."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _title_id_from_shop_url(shop_uri):
    """'https://ec.nintendo.com/apps/0400c3f00006e000/GB' -> '0400c3f00006e000'."""
    match = _TITLE_ID_RE.search(str(shop_uri or ""))
    return match.group(1).lower() if match else None


@dataclass
class PresenceSnapshot:
    """Parse the presence server."""

    nsaid: str = ""
    account_name: str = ""
    avatar_url: str = ""
    avatar2_url: str = ""
    state: str = "OFFLINE"
    platform: int | None = None
    updated_at: int | None = None
    logout_at: int | None = None
    title_id: str | None = None
    title_name: str | None = None
    image_url: str | None = None
    since: datetime | None = None
    total_play_time: int | None = None
    first_played_at: int | None = None

    @property
    def is_in_game(self) -> bool:
        return self.state in ONLINE_STATES and bool(self.title_name)

    @property
    def is_idle(self) -> bool:
        """Console is on, but nobody has picked an application."""
        return self.state in IDLE_STATES

    @property
    def console_name(self) -> str:
        return PLATFORM_NAMES.get(self.platform, PLATFORM_NAMES[DEFAULT_PLATFORM])

    @property
    def age_seconds(self):
        """Seconds since the console last reported presence, if it ever has."""
        if not self.updated_at:
            return None
        return time() - self.updated_at

    def is_stale(self, limit) -> bool:
        """True if the console hasn't reported in `limit` seconds.

        A sleeping Switch stops pushing presence, so an old `updatedAt` is the
        only signal we get that the console went away.
        """
        age = self.age_seconds
        return age is not None and age > limit

    @property
    def since_epoch(self):
        """`since` as epoch seconds, for Discord's `start` field."""
        return int(self.since.timestamp()) if self.since else None

    def state_summary(self):
        """'(colour, text)' describing the state in plain English."""
        if self.state == "OFFLINE":
            return C.GRAY, "offline"
        if self.is_idle:
            return C.BLUE, "Home Menu"
        if self.state == "PLAYING":
            return C.GREEN, "in game (online)"
        return C.GREEN, "in game"


class NxapiClient:
    """Polls an nxapi presence server and reports what it finds."""

    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update(headers)
        self._prev_cover = None
        self._prev_buttons = []
        self._friend_url_cache = {}
        self._stale_warned = False

    def presence_url(self) -> str:
        """The URL to poll: `url` if set, else `base_url` + `nsaid`."""
        explicit = str(self.config.get("url") or "").strip()
        if explicit:
            return explicit.rstrip("/")
        base = str(self.config.get("base_url") or "").strip().rstrip("/")
        if not base:
            base = PUBLIC_BASE_URL
        nsaid = normalise_nsaid(self.config.get("nsaid"))
        if not nsaid:
            raise NxapiError("No NSA ID is configured.")
        return f"{base}/api/presence/{nsaid}"

    def fetch(self) -> PresenceSnapshot:
        url = self.presence_url()
        try:
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as e:
            raise NxapiUnavailable(
                f"Presence server unreachable ({type(e).__name__})."
            ) from e

        if response.status_code == 404:
            raise NxapiNotFound(
                "The presence server has no data for this NSA ID - check that "
                "the ID and base URL are correct and that the console has "
                "reported in at least once."
            )
        if response.status_code == 429:
            raise NxapiUnavailable("The presence server is rate-limiting us.")
        if not response.ok:
            raise NxapiUnavailable(
                f"The presence server answered HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise NxapiBadResponse("The presence server didn't return JSON.") from e

        return self._to_snapshot(self._parse(payload))

    def _parse(self, payload):
        if not isinstance(payload, dict):
            raise NxapiBadResponse(
                f"Expected an object from the presence server, got {type(payload).__name__}."
            )
        error = payload.get("error")
        if error:
            detail = payload.get("error_message") or "no detail given"
            raise NxapiNotFound(f"The presence server reported {error} ({detail}).")
        return payload

    def _to_snapshot(self, payload) -> PresenceSnapshot:
        friend = payload.get("friend") or {}
        presence = friend.get("presence") or {}
        game = presence.get("game") or {}
        title = payload.get("title") or {}

        title_id = title.get("id") or _title_id_from_shop_url(game.get("shopUri"))
        snapshot = PresenceSnapshot(
            nsaid=friend.get("nsaId") or normalise_nsaid(self.config.get("nsaid")),
            account_name=friend.get("name") or "",
            avatar_url=friend.get("imageUri") or "",
            avatar2_url=friend.get("image2Uri") or "",
            state=str(presence.get("state") or "OFFLINE").upper(),
            platform=presence.get("platform"),
            updated_at=presence.get("updatedAt"),
            logout_at=presence.get("logoutAt"),
            title_id=title_id.lower() if title_id else None,
            title_name=title.get("name") or game.get("name") or None,
            image_url=game.get("imageUri") or title.get("image_url") or None,
            since=_parse_timestamp(title.get("since")),
            total_play_time=game.get("totalPlayTime"),
            first_played_at=game.get("firstPlayedAt"),
        )
        return snapshot

    # --- logging --------------------------------------------------------

    def report(self, snapshot: PresenceSnapshot) -> None:
        """Print the steady state of a snapshot (reprinted every poll)."""
        stale = self._staleness(snapshot)

        _log("Source:", str(self.presence_url()))
        colour, _ = snapshot.state_summary()
        state = f"{colour}{snapshot.state}{C.RESET}"
        if stale:
            state += f" {C.YELLOW}(stale - last seen {format_ago(snapshot.age_seconds)}){C.RESET}"
        _log("State:", state)
        _log("Console:", self.console_label(snapshot))
        if snapshot.account_name:
            _log("Account:", f"{C.GRAY}{snapshot.account_name}{C.RESET}")
        if snapshot.title_name:
            title = f"{C.WHITE}{C.BOLD}{snapshot.title_name}{C.RESET}"
            if snapshot.title_id:
                title = (
                    f"{C.GRAY}{snapshot.title_id}{C.RESET} {C.GRAY}|{C.RESET} " + title
                )
            _log("Title:", title)
        if snapshot.since:
            since = snapshot.since.astimezone().strftime("%H:%M")
            _log(
                "Session:",
                f"started {since} {C.GRAY}({format_ago(time() - snapshot.since_epoch)}){C.RESET}",
            )
        play_time = self.play_time(snapshot)
        if play_time:
            _log("Play time:", play_time)
        friend_code = self.friend_code()
        if self.config.get("share_friend_code"):
            if friend_code:
                _log("Friend code:", f"{C.GRAY}{friend_code}{C.RESET}")
            else:
                _log(
                    "Friend code:",
                    f"{C.YELLOW}not set - add friend_code to the config{C.RESET}",
                )
        if self.config.get("show_buttons"):
            profile_url = str(self.config.get("profile_url") or "").strip()
            if profile_url:
                _log("Profile:", f"{C.GRAY}{profile_url}{C.RESET}")

    def note_cover(self, snapshot: PresenceSnapshot) -> None:
        """Print the cover only when it changes."""
        cover = self.cover_image(snapshot)
        if cover == self._prev_cover:
            return
        self._prev_cover = cover
        colour = C.CYAN if str(cover).startswith("http") else C.GRAY
        _log("Cover:", f"{colour}{cover}{C.RESET}")

    def note_buttons(self) -> None:
        """Print the activity's buttons."""
        buttons = self.build_buttons()
        labels = [b["label"] for b in buttons]
        if labels == self._prev_buttons:
            return
        self._prev_buttons = labels
        if labels:
            for button in buttons:
                _log(
                    "Button:",
                    f"{C.YELLOW}{button['label']}{C.RESET} {C.GRAY}{button['url']}{C.RESET}",
                )
        else:
            _log("Buttons:", f"{C.GRAY}none{C.RESET}")

    def _staleness(self, snapshot: PresenceSnapshot) -> bool:
        limit = int(self.config.get("stale_seconds") or 0)
        if limit <= 0:
            return False
        stale = snapshot.is_stale(limit)
        if stale and not self._stale_warned:
            self._stale_warned = True
            warn(
                f"Presence is {format_ago(snapshot.age_seconds)} old - the console "
                "is probably asleep, switched off, or no longer reporting."
            )
        elif not stale:
            self._stale_warned = False
        return stale

    def console_label(self, snapshot: PresenceSnapshot) -> str:
        """The console's full name, e.g. 'Nintendo Switch 2'."""
        return snapshot.console_name

    def activity_state(self, snapshot: PresenceSnapshot):
        """The status line under the title, e.g. 'Playing on Nintendo Switch 2'."""
        console = snapshot.console_name
        show_console = self.config.get("show_console")
        if snapshot.is_in_game:
            return f"Playing on {console}" if show_console else None
        if self.config.get("show_inactive_presence"):
            # nxapi's inactive presence is a flat "Not playing", console or not.
            return "Not playing"
        if snapshot.is_idle:
            return f"On {console} Home Menu" if show_console else "Home Menu"
        return f"{console} offline" if show_console else "Offline"

    def friend_code(self) -> str:
        """The configured friend code, normalised, or '' if unset/invalid."""
        return normalise_friend_code(self.config.get("friend_code"))

    def play_time(self, snapshot: PresenceSnapshot):
        """The play-time line."""
        mode = str(self.config.get("play_time") or DEFAULT_PLAY_TIME)
        if mode not in PLAY_TIME_LABELS:
            mode = DEFAULT_PLAY_TIME
        return play_time_text(mode, snapshot.total_play_time, snapshot.first_played_at)

    def cover_image(self, snapshot: PresenceSnapshot):
        """What to hand Discord as `large_image`."""
        if not snapshot.is_in_game:
            if self.config.get("avatar_when_idle") and snapshot.avatar_url:
                return snapshot.avatar_url
            return IDLE_ASSET
        if self.config.get("prefer_dev_app") and snapshot.title_id:
            # Discord asset key: lowercase title ID.
            return snapshot.title_id
        if snapshot.image_url:
            return snapshot.image_url
        return snapshot.title_id or IDLE_ASSET

    def small_image(self, snapshot: PresenceSnapshot):
        """`(image, text)` for the small-image slot, or `(None, None)`."""
        friend_code = self.friend_code()
        if self.config.get("share_friend_code") and friend_code:
            image = snapshot.avatar2_url or snapshot.avatar_url
            return (image, friend_code) if image else (None, None)
        if self.config.get("mii_icon") and snapshot.avatar_url:
            # No point repeating the avatar if it's already the large image.
            if self.cover_image(snapshot) == snapshot.avatar_url:
                return None, None
            return snapshot.avatar_url, snapshot.account_name or None
        return None, None

    def build_buttons(self):
        """Up to two buttons: your nxapi profile, and a Nintendo friend link.

        With `one_button` on there's just the nxapi profile link, labelled for
        adding you. That skips the friend-link lookup entirely, since nothing
        uses its result.
        """
        if not self.config.get("show_buttons"):
            return []
        profile_url = str(self.config.get("profile_url") or "").strip()

        if self.config.get("one_button"):
            if not profile_url:
                return []
            return [{"label": "Add friend", "url": profile_url}]

        buttons = []
        if profile_url:
            buttons.append({"label": "View profile", "url": profile_url})
        friend_url = self.friend_url()
        if friend_url:
            buttons.append({"label": "Add friend", "url": friend_url})
        return buttons[:MAX_BUTTONS]

    def friend_url(self):
        """The 'Add friend' target, or None if it can't be worked out.

        `friend_url` wins if set, otherwise the profile page's JSON API supplies
        `friend_code_url`. Cached per profile URL, so it's one request a session
        rather than one per poll.
        """
        manual = str(self.config.get("friend_url") or "").strip()
        if manual:
            return manual

        profile_url = str(self.config.get("profile_url") or "").strip()
        if not profile_url:
            return None
        if profile_url in self._friend_url_cache:
            return self._friend_url_cache[profile_url]

        endpoint = _profile_endpoint(profile_url)
        resolved = ""
        if endpoint:
            try:
                response = self.session.get(endpoint, timeout=DEFAULT_TIMEOUT)
                if response.ok:
                    resolved = str(response.json().get("friend_code_url") or "").strip()
            except (requests.RequestException, ValueError, AttributeError):
                resolved = ""
        self._friend_url_cache[profile_url] = resolved or None

        if resolved:
            ok("Resolved an Add friend link from your profile page")
        elif "/@" in profile_url:
            warn(
                "profile_url is your profile's page address, which has no "
                "friend link. Use the /profile/<token> URL shown under "
                "Settings > Public profile instead."
            )
        else:
            warn(
                "No friend code link from the profile page - is the public "
                "profile enabled? Set friend_url to override."
            )
        return self._friend_url_cache[profile_url]

    def build_tooltip(self, snapshot: PresenceSnapshot):
        """Hover text for the large image."""
        if not self.config.get("show_tooltip"):
            return None
        parts = []
        if self.config.get("tooltip_session_start") and snapshot.since:
            parts.append(f"Since {snapshot.since.astimezone().strftime('%H:%M')}")
        play_time = self.play_time(snapshot)
        if play_time:
            parts.append(play_time)
        if self.config.get("tooltip_title_id") and snapshot.title_id:
            parts.append(snapshot.title_id)
        return " | ".join(parts) or None
