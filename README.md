# nxapi-cli

Show what you're playing on a Nintendo Switch as Discord Rich Presence.

It polls an [nxapi](https://gitlab.fancy.org.uk/samuel/nxapi-znca-api) presence server for
your account's presence and pushes it to Discord.

```
Source:     https://nxapi-presence.fancy.org.uk/api/presence/27c5fb26d15599a6
State:      ONLINE
Console:    Nintendo Switch 2
Account:    reply 2 me
Title:      0400c3f00006e000 | Mario Kart World
Session:    started 17:14 (56m ago)
Play time:  Played for 285 hours
Friend code: SW-6646-7630-9893
Profile:    https://nxapi-auth.fancy.org.uk/profile/BaN1q_1M9eHy0plW6T8T2g
Cover:      https://nxapi-presence.fancy.org.uk/api/presence/resources/atum/i/c/....jpeg
Button:     Add friend    https://nxapi-auth.fancy.org.uk/profile/BaN1q_1M9eHy0plW6T8T2g
```

## Requirements

* A Nintendo account linked to a presence server - see **[SETUP.md](SETUP.md)**, which
  walks through the whole thing
* A console actually reporting presence to that server (ZNC or nxapi on a hacked console)
* Discord installed and running on the PC
* Python 3.13+, unless you're using a build

## Install

### Linux

```bash
git clone <this-repo>
cd nxapi-cli
./start.py
```

### Windows

Download `nxapi-cli_Windows_*.exe` from the latest release - x64 or ARM64.

<details>
  <summary>Running as a Windows service</summary>

Use [NSSM](https://nssm.cc/release/nssm-2.24.zip): `nssm install nxapicli`.
The .exe must stay put, e.g. `C:\nxapi-cli\nxapi-cli.exe`.
</details>

<details>
  <summary>Running as a systemd service</summary>

```bash
mkdir -p ~/.config/systemd/user ~/.config/environment.d/
bash -c 'echo "PATH=${HOME}/.local/bin:" > ~/.config/environment.d/90-path.conf'

bash -c 'echo "
[Unit]
Description=Enables nxapi-cli
Wants=network-online.target
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 $HOME/nxapi-cli/start.py
Restart=on-failure
StandardOutput=journal
StandardError=journal
WorkingDirectory=$HOME/nxapi-cli

[Install]
WantedBy=default.target
" > ~/.config/systemd/user/nxapi-cli.service'

systemctl --user daemon-reload
systemctl --user enable --now nxapi-cli
```

Check on it with `systemctl --user status nxapi-cli`, or follow the log with
`journalctl --user -xeu nxapi-cli`.
</details>

## First run

You get asked for your presence URL, then a screen of toggles. Settings are saved to
`~/.config/nxapi-cli/nxapicliconfig.json` (`%APPDATA%\nxapi-cli\` on Windows).

The prompt takes either form - a bare NSA ID, or the whole
`https://nxapi-presence.fancy.org.uk/api/presence/<nsaid>` URL from your browser. Paste a
full URL and it's kept verbatim, so pointing at your own presence server later still works.

To change things afterwards, edit the JSON, or delete it and let the wizard run again.

<details>
  <summary>Portable mode</summary>

Drop an empty file named `portable.txt` next to the script and the config is read from and
saved to that folder instead of the OS config directory - useful for running off a USB drive.
</details>

## Config

Grouped the same way the first-run screen presents them.

### General
| Key | Default | Description |
|---|---|---|
| `nsaid` | `""` | Your Nintendo account NSA ID (16 hex digits) |
| `base_url` | `https://nxapi-presence.fancy.org.uk` | Presence server to poll |
| `url` | `""` | Full presence URL. When set it **replaces** `base_url` + `nsaid` - see [below](#when-to-use-url) |
| `client_id` | `1512043386327007253` | Discord developer application ID to send presence to |
| `wait_seconds` | `30` | How often to refresh, in seconds (minimum 15) |
| `hibernate_seconds` | `600` | How long to wait before retrying when the presence server is unreachable |
| `stale_seconds` | `7200` | Presence older than this is treated as unreachable and cleared. `0` disables |

### Connection
| Key | Default | Description |
|---|---|---|
| `nsaid_prompt` | `true` | Re-prompt for the NSA ID if presence can't be read on startup |

#### When to use `url`

`nsaid` and `base_url` combine into the standard `{base_url}/api/presence/{nsaid}`. `url`
is the escape hatch for servers with a different shape - nxapi's own local server, for
instance, serves `/api/znc/user/presence` or `/api/znc/friend/{nsaid}/presence`:

```json
{ "url": "http://192.168.1.10:12345/api/znc/friend/27c5fb26d15599a6/presence" }
```

Setting `url` makes `nsaid` irrelevant - the tool polls exactly what's in it and appends
nothing. Leave it empty for a normal public or proxied server.

### Elapsed timer
| Key | Default | Description |
|---|---|---|
| `show_timer` | `true` | Show elapsed time in the presence |
| `accurate_timer` | `true` | Start the timer at the session time the server reports, rather than when this first saw the title |

### Activity text
| Key | Default | Description |
|---|---|---|
| `show_only_in_game` | `true` | Only update presence while a game is running (skips the Home Menu) |
| `show_inactive_presence` | `false` | Show "Not playing" when the console is on but idle. Takes priority over `show_only_in_game` |
| `show_console` | `true` | Show the console name under the game name. Off drops the line rather than shortening it, since Discord already labels the card "Playing" |

### Play time
| Key | Default | Description |
|---|---|---|
| `play_time` | `hour` | How play time is shown - see below |

| Value | Result |
|---|---|
| `hidden` | Never show play time |
| `nintendo` | As a console shows it: "First played 5 days ago" for the first fortnight, then a rounded figure |
| `hour` | Nearest hour - `Played for 285 hours` |
| `hour_since` | ...with first played date |
| `approx5` | Nearest 5 hours |
| `approx5_since` | ...with first played date |
| `exact` | Exact - `Played for 285 hours, 42 minutes` |
| `exact_since` | ...with first played date |

Play time goes in the tooltip, or on the status line with `tooltip_as_status_line`. Modes
that round down to hours show nothing below an hour, so you never get "Played for 0 minutes".

### Friend code and buttons
| Key | Default | Description |
|---|---|---|
| `share_friend_code` | `false` | Show your friend code as the small icon's hover text |
| `friend_code` | `""` | Your friend code, e.g. `SW-1234-5678-9012` |
| `show_buttons` | `false` | Show the "View profile" and "Add friend" buttons |
| `one_button` | `true` | Show only one button, linking to your nxapi profile |
| `profile_url` | `""` | Your nxapi-auth profile page - `https://nxapi-auth.fancy.org.uk/profile/<token>` |
| `friend_url` | `""` | Override for the "Add friend" link; otherwise looked up from `profile_url` |

`share_friend_code` takes priority over `mii_icon`: sharing your code also switches the
small icon to the account avatar, the same as nxapi does it.

Your friend code has to be pasted in - a presence server can't supply it. It comes from the
*authenticated* Nintendo account (`links.friendCode`), which needs the nxapi-auth OAuth flow
or a local server with an `Authorization: na` header; neither is exposed publicly. The
payload's `friend.id` is an internal ZNC ID, and `friend.route` is empty apart from
`channel: FRIEND_CODE`. Any format works: `SW-1234-5678-9012`, `1234-5678-9012`, or bare
digits.

### The buttons

| Button | Goes to | Comes from |
|---|---|---|
| **View profile** | your nxapi-auth profile page | `profile_url` |
| **Add friend** | `https://lounge.nintendo.com/friendcode/<code>/<token>` | looked up automatically |

With `one_button` on (the default) you get a single **Add friend** button pointing at
your nxapi profile, which lists your friend code and play history. Turn it off for both
buttons, where the second becomes a direct Nintendo friend request.

Set `profile_url` to the `/profile/<token>` address from nxapi-auth's **Settings > Public
profile** - not your profile's `@username` page, which looks similar but has no friend link.
From that URL this tool reads the profile JSON once and picks up your `friend_code_url`, so
there's nothing else to paste. `friend_url` overrides it if you'd rather be explicit.

The lounge link can't be built from the friend code: it carries a trailing token only
nxapi-auth can supply, and the path is validated - a wrong token returns 404.

> [!IMPORTANT]
> **Discord never shows activity buttons to the account that owns the presence.** They're
> being sent - the `Button:` line in the log proves it - but only other users see them. Ask
> someone to look at your profile, or check from a second account. This is Discord's
> behaviour, not a bug here: see their
> [docs](https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence)
> and [pypresence#243](https://github.com/qwertyquerty/pypresence/issues/243).

The friend link only resolves while your public profile is enabled - switch it off and that
button disappears, while "View profile" keeps working.

### Tooltip
| Key | Default | Description |
|---|---|---|
| `show_tooltip` | `true` | Show a hover tooltip over the large image (contents from the `tooltip_*` options) |
| `tooltip_as_status_line` | `true` | Put the tooltip on the status line instead of on hover |
| `tooltip_session_start` | `false` | Include when the session started |
| `tooltip_title_id` | `false` | Include the title ID, e.g. `0400c3f00006e000` |

### Cover art
| Key | Default | Description |
|---|---|---|
| `avatar_when_idle` | `true` | Use the account avatar when no game is running |
| `mii_icon` | `true` | Show the Mii icon bottom-right. Ignored when `share_friend_code` is on |
| `prefer_dev_app` | `false` | Use your own Discord assets instead of Nintendo's box art |

### Using your own images

`prefer_dev_app` swaps Nintendo's box art for assets you host. Create an application at the
[Discord Developer Portal](https://discord.com/developers/applications), put its ID in
`client_id`, then upload images under **Rich Presence > Art Assets** named after the
lowercase title ID (e.g. `0400c3f00006e000`). The Home Menu falls back to `home_menu`.

To test the Discord side without a console awake:

```bash
python tests/test_presence.py --simulate
```

## Things worth knowing

* **`accurate_timer` is a best effort.** The server derives `title.since` from
  `presence.updatedAt`, not a real session start, so it moves whenever the console pushes
  presence. Usually right, but it can drift mid-session.
* **`platform` is only sent while a console is online.** Offline and Home Menu responses omit
  it, so the console name falls back to "Nintendo Switch".
* **A sleeping console looks like stale data, not offline.** The server keeps serving the
  last thing it was told, so `updatedAt` is your only hint - hence `stale_seconds`. The
  two-hour default is deliberately generous: an idle console can leave an `ONLINE` record
  sitting there for a long time, and wrongly clearing presence is worse than showing
  slightly old data. Lower it if you'd rather it vanish sooner.
* **`totalPlayTime` is in minutes** and only arrives while a game is running.
* **Discord restarts are handled.** If the RPC pipe drops, this reconnects rather than
  dying on you.

## Credits

* [nxapi](https://gitlab.fancy.org.uk/samuel/nxapi-znca-api) by samuelthomas2774 - the
  presence server and the endpoint this reads
* [nxapi-auth](https://nxapi-auth.fancy.org.uk/) by Ellie - account linking, presence API
  access, public profiles and friend-code links. See [SETUP.md](SETUP.md)
* [pypresence](https://github.com/qwertyquerty/pypresence) - Discord RPC
