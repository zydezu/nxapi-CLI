# nxapi-cli

Show what you're playing on your Nintendo Switch system as Discord Rich Presence.

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/boysaremoe) [![pypresence](https://img.shields.io/badge/using-pypresence-00bb88.svg?style=for-the-badge&logo=discord&logoWidth=20)](https://github.com/qwertyquerty/pypresence)

It polls an [nxapi](https://gitlab.fancy.org.uk/samuel/nxapi-znca-api) presence server for
your Switch's status and shows it to Discord.

```
Source:     https://nxapi-presence.fancy.org.uk/api/presence/27c5fb26d15599a6
State:      ONLINE
Console:    Nintendo Switch 2
Account:    boysaremoe
Title:      0400c3f00006e000 | Mario Kart World
Session:    started 17:14 (56m ago)
Play time:  Played for 285 hours
Friend code: SW-6646-7630-9893
Profile:    https://nxapi-auth.fancy.org.uk/profile/BaN1q_1M9eHy0plW6T8T2g
Cover:      https://nxapi-presence.fancy.org.uk/api/presence/resources/atum/i/c/....jpeg
Button:     Add friend    https://nxapi-auth.fancy.org.uk/profile/BaN1q_1M9eHy0plW6T8T2g
```

## Requirements

* A Nintendo account linked to a presence server - see [SETUP.md](SETUP.md), which shows you how to set this up
* Discord installed and running on the PC
* Python 3.13+, unless you're using a build

## Usage

Download the relevant package for your system from [releases](https://github.com/zydezu/PS3-RPC/releases).

### Cloning

```bash
git clone https://github.com/zydezu/nxapi-CLI
cd nxapi-cli
./start.py
```

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

> [!TIP]
> Read [SETUP.md](SETUP.md), on how to link your Nintendo Switch user to the presence server. 
> Do this before running this script!

You'll be guided through a setup, where you're asked for your presence URL and are then able
to configure all the options. 

Settings are saved to `~/.config/nxapi-cli/nxapicliconfig.json` (`%APPDATA%\nxapi-cli\` on Windows).

The prompt takes either a bare NSA ID, or the whole
`https://nxapi-presence.fancy.org.uk/api/presence/<nsaid>` URL from your browser, so you can
paste this in.

To change things afterwards, edit the JSON, or delete it and let the config setup run again.

<details>
  <summary>Portable mode</summary>

Drop an empty file named `portable.txt` next to the script and the config is read from and
saved to that folder instead of the OS config directory - useful for running off a USB drive.
</details>

> [!NOTE]
> `profile_url` needs the `/profile/<token>` address from nxapi-auth's **Your User > Settings > Public
> profile**. The `@username` page looks similar but has no JSON API, so the lounge link can't
> be resolved from it. This only matters if `one_button` is off.

> [!WARNING]
> The "Add Friend" button is only shown while public profile is enabled, if it's off the "Add friend"
and "View profile" button wont show.

> [!IMPORTANT]
> Discord doesn't show buttons on your own account showing the presence, only other users
can see the buttons.

<details>
  <summary>Using your own images</summary>

Create an application at the [Discord Developer Portal](https://discord.com/developers/applications),
put its ID in `client_id`, then upload images under **Rich Presence > Art Assets** named after
the lowercase title ID (e.g. `0400c3f00006e000`). The Home Menu falls back to `home_menu`.

To test the Discord side without a console awake: `python tests/test_presence.py --simulate`
</details>

## Credits

* [nxapi](https://gitlab.fancy.org.uk/samuel/nxapi-znca-api) by samuelthomas2774 - the
  presence server and the endpoint this reads
* [nxapi-auth](https://nxapi-auth.fancy.org.uk/) by Ellie - account linking, presence API
  access, public profiles and friend-code links. See [SETUP.md](SETUP.md)
* [pypresence](https://github.com/qwertyquerty/pypresence) - Discord RPC
