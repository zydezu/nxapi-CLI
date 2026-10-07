# Setting up nxapi-cli

This walks through linking your Nintendo account to [nxapi-auth](https://nxapi-auth.fancy.org.uk/),
enabling presence API access, and pointing nxapi-cli at it. The last section covers the
optional public profile, which is what the "Add friend" button links to.

There are two separate systems involved, and it's worth keeping them apart:

| System | What it does |
|---|---|
| **Your console** (via ZNC or nxapi) | Reports what you're playing |
| **A presence server** (e.g. `nxapi-presence.fancy.org.uk`) | Stores it and serves it as JSON |
| **nxapi-cli** | Reads that JSON and pushes it to Discord |

nxapi-cli does none of the reporting. If the console isn't reporting, there's nothing for
it to read - no amount of Discord-side configuration will help.

---

## 1. Link your Nintendo account

1. Go to **<https://nxapi-auth.fancy.org.uk/>** and sign in with your Nintendo Account.

2. Enter your **friend code** - the `SW-XXXX-XXXX-XXXX` number, which is *not* your
   nsaId and *not* your Nintendo Account email. You'll need it from the console:
   HOME Menu → your user icon → **Profile** → friend code, bottom right.

   > Your friend code is different from the nsaId this tool polls. Write both down:
   > the friend code is for linking (step 1) and for the optional profile link (step 5),
   > the nsaId is what identifies you to a presence server.

3. **Confirm on the console.** This part can't be done from the browser - the Switch or
   Switch 2 has to show a friend-request prompt and you have to accept it. That's why
   nxapi-auth says linking requires *"your friend code and access to a Nintendo Switch
   console"*.

4. Check **Linked Nintendo Switch users**. Once accepted, the row should show:

   | Nickname | Friend code | Presence | Added |
   |---|---|---|---|
   | reply 2 me | SW-6646-7630-9893 | Completed | 25/09/2026 |

   **Presence: Completed** means the link succeeded. If it's still pending, the console
   step is outstanding.

   > This table is also where you get the friend code for the optional `friend_code`
   > setting in step 6.

## 2. Enable presence API access

On your nxapi-auth account page, turn on **access to the presence API**. The site's own
description of this option is *"show your Nintendo Switch presence in Discord or your own
website"* - which is precisely this tool's job.

Once enabled, nxapi-auth gives you a **presence URL** for your account, shaped like:

```
https://nxapi-presence.fancy.org.uk/api/presence/<your-nsaid>
```

Keep that URL - it's the only thing nxapi-cli needs.

## 3. Get your console reporting

Your console has to actually push presence to that server. That means running something like
[ZNC](https://github.com/RyuaNerin/znca) or nxapi on a hacked console, which is outside
this tool's scope - but nothing works until it's in place. The
[nxapi documentation](https://gitlab.fancy.org.uk/samuel/nxapi) covers standing one up.

The presence host itself, `https://nxapi-presence.fancy.org.uk`, is an API with no web
page, so visiting it returns 404. It's only useful as the address your presence URL is
built from.

A quick way to check, without any of the above being set up properly:

```bash
curl https://nxapi-presence.fancy.org.uk/api/presence/<your-nsaid>
```

- `200` with a JSON body containing `friend.presence` - working
- `404` - the server has never heard of that nsaId (wrong ID, or nothing has reported yet)
- `403` - expected for `/api/presence` without an ID; bulk access is deliberately opt-in

## 4. Run nxapi-cli

```bash
cd nxapi-cli
./start.py
```

On first run it asks for your presence URL. **Paste the whole URL** - the wizard accepts
either a full URL or a bare nsaId, and if you give it a full URL it stores that verbatim,
which keeps working if you later move to your own presence server.

It fetches once to confirm, then shows the option screen, then starts polling:

```
Source:    https://nxapi-presence.fancy.org.uk/api/presence/<your-nsaid>
State:     ONLINE
Console:   Nintendo Switch 2
Title:     0400c3f00006e000 | Mario Kart World
Cover:     https://.../atum/i/c/....jpeg
```

Settings live in `~/.config/nxapi-cli/nxapicliconfig.json`. Delete that file to go back
through the wizard, or edit it by hand for anything not on the screen.

## 5. Optional: the public profile and "Add friend" button

Your **Settings** panel has a **Public profile** entry. Enabling it creates a public page
at a URL of the form:

```
https://nxapi-auth.fancy.org.uk/profile/<token>
```

That page shows your nickname, whether you're online, what you're playing, your recently
played titles, and your most-played titles with total play time and when you first played
each one.

To use it, paste that exact URL into `profile_url` and turn `show_buttons` on:

```json
"show_buttons": true,
"profile_url": "https://nxapi-auth.fancy.org.uk/profile/<token>"
```

Use the `/profile/<token>` address from the Public profile setting, **not** your profile's
`@username` page - the two look alike but only the first one carries the friend link.

That gives you two buttons. **View profile** opens the page; **Add friend** opens your
Nintendo friend-code link, which this tool fetches from the profile page for you. You don't
need to paste that second URL anywhere, though `friend_url` will override it if you'd
rather.

Two things to know:

- **You won't see the button on your own presence.** Discord never shows activity buttons
  to the account that owns the presence. It's being sent - the tool prints a `Button:`
  line to prove it - but only other users see it. Ask someone to look at your profile, or
  check from a second account.
- **Anyone with the link can see that page.** It's unlisted rather than private, so treat
  the token as semi-public and don't share it more widely than you want. Leave the setting
  off if you'd rather not have a public profile at all; nothing else here depends on it.

## 6. Optional: show your friend code

Your friend code can't come from a presence server - it comes from the authenticated
Nintendo account, so nxapi-cli can't fetch it. Paste it in instead:

```json
"share_friend_code": true,
"friend_code": "SW-6646-7630-9893"
```

`friend_code` accepts `SW-1234-5678-9012`, `1234-5678-9012` or the bare twelve digits, and
normalises it. With it on, the Mii icon in the corner of the card gets the friend code as
its hover text - and unlike buttons, **you can see that one yourself**.

## 7. Optional: other nxapi-auth settings

These are handled by nxapi-auth and nxapi-cli doesn't read them, but they're on the same
page if you're curious:

- **Friend code URL** - publishes the friend-request URL (the same "Copy as URL" payload
  the Switch App generates), so others can send you a friend request.
- **Discord role connections** - links your Nintendo user to a Discord user, surfacing
  your friend code on your Discord profile in servers that use the linked role. Unrelated
  to nxapi-cli's own rich presence.
- **Record play activity** - keeps the play history that powers the public profile's
  "recently played" and "most played" lists. Without it, that page is much emptier.

---

## Troubleshooting

**`404` from the presence server.** The server has no data for that nsaId. Either the ID is
wrong, or the console has never reported. Check your console is on and reporting.

**Presence shows a game but the session time is wrong.** The `accurate_timer` option starts
the elapsed timer at the time the server last reported, not a true session start, so it can
drift if your console pushes presence mid-game. Turn it off to time from when the script
first saw the title.

**`Console: Nintendo Switch` instead of `Nintendo Switch 2`.** The platform is only sent
while a console is online, so an offline or Home Menu response falls back to the default.

**A game appears but won't clear.** A sleeping console stops reporting while the server
keeps serving the last thing it was told. Raise `stale_seconds` to wait longer, or set it
to `0` to disable the check and keep showing whatever the server last had.

**No button appears at all.** Confirm the terminal printed a `Button:` line - that tells you
whether it was sent. If it was, it's the Discord limitation above, not a fault here.
