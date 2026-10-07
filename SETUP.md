# Setting up nxapi-cli

Linking your Nintendo Switch account to [nxapi-auth](https://nxapi-auth.fancy.org.uk/),
enabling presence API access, and pointing nxapi-cli at the result. The last two sections
are optional extras.

---

## 1. Link your Nintendo account

1. Go to **<https://nxapi-auth.fancy.org.uk/>**, sign in, and add a Nintendo Switch user.

2. Enter your **friend code** (`SW-XXXX-XXXX-XXXX`) and confirm on the actual console, you'll need to add the 'Shinnosuke' user.

3. **Presence: Completed** under **Linked Nintendo Switch users** means it worked:

   | Nickname | Friend code | Presence | Added |
   |---|---|---|---|
   | boysaremoe | SW-6646-7630-9893 | Completed | 25/09/2026 |

## 2. Enable presence API access

On your account page, scroll to "Presence URL" in the "Presence API" section, and click 'show' to see your **presence URL**:

```
https://nxapi-presence.fancy.org.uk/api/presence/<your-nsaid>
```

Copy this, as it's needed for the script's setup.

## 3. Optional: public profile and the "Add friend" button

Back on https://nxapi-auth.fancy.org.uk, in **Your User > Settings > Public profile**, you can enable Public profile and it will creates a page at:

```
https://nxapi-auth.fancy.org.uk/profile/<token>
```

It shows your nickname, online status, what you're playing, and your recently and most
played titles with their play times. Setup will ask for this optionally. It's used for `profile_url` and when
`show_buttons` is `true`.

That page's JSON can also carry your `friend_code_url` - Nintendo's own
`lounge.nintendo.com` friend link - so **Add friend** works without pasting anything else,
see the next section for how to set this up.

## 4. Optional: other nxapi-auth settings

Handled by nxapi-auth, unread by nxapi-cli, but on the same page:

- **Friend code URL** - publishes the friend-request link, so others can add you directly. This is obtained from the Nintendo Switch App on mobile
- **Discord role connections** - shows your friend code on your Discord profile in servers
  using the linked role. Unrelated to nxapi-cli's own presence.
- **Record play activity** - keeps the history behind the public profile's played lists.

---

## 5. Run nxapi-cli

Open the `nxapi-cli` program.

Paste the whole presence URL when asked, then you'll be able to configure some settings after that.

When that's all done, you'll see something like:

```
Source:    https://nxapi-presence.fancy.org.uk/api/presence/<your-nsaid>
State:     ONLINE
Console:   Nintendo Switch 2
Title:     0400c3f00006e000 | Mario Kart World
Cover:     https://.../atum/i/c/....jpeg
```

Settings are saved to `~/.config/nxapi-cli/nxapicliconfig.json` (`%APPDATA%\nxapi-cli\` on Windows).
