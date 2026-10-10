"""Poll loop: read presence, push it to Discord."""

import contextlib
from time import sleep, time

from pypresence import PyPresenceException, ServerError

from nxapi_cli.config import APP_NAME, PrepWork
from nxapi_cli.nxapi import NxapiClient, NxapiError, NxapiNotFound, normalise_nsaid
from nxapi_cli.ui import C, clear, err, stdin_is_interactive, warn


def _print_header(config_path):
    print(f"{C.BOLD}{C.CYAN}{APP_NAME}{C.RESET}  {C.GRAY}(Ctrl+C to stop){C.RESET}")
    print(f"{C.GRAY}Config:{C.RESET}   {C.WHITE}{config_path}{C.RESET}\n")


def _presence_kwargs(prepWork, client, snapshot, timer):
    """Build the pypresence.update() kwargs for the current snapshot."""
    show_tooltip = prepWork.config["show_tooltip"]
    as_status_line = show_tooltip and prepWork.config["tooltip_as_status_line"]
    tooltip_text = client.build_tooltip(snapshot)

    # With the tooltip on the status line, the hover text falls back to the title ID.
    if as_status_line:
        large_text = snapshot.title_id if prepWork.config["tooltip_title_id"] else None
        details = tooltip_text
    else:
        large_text = tooltip_text
        details = None

    # Small image sits bottom-right; a shared friend code wins over the Mii.
    small_image, small_text = client.small_image(snapshot)

    kwargs = {
        "name": snapshot.title_name or snapshot.account_name,
        "details": details,
        "state": client.activity_state(snapshot),
        "large_image": client.cover_image(snapshot),
        "large_text": large_text,
        "small_image": small_image,
        "small_text": small_text,
        "start": timer,
    }
    # Discord rejects the whole activity if `buttons` is present but empty, so
    # only send it when there's something to show.
    buttons = client.build_buttons()
    if buttons:
        kwargs["buttons"] = buttons
    return kwargs


def main():
    prepWork = PrepWork()
    try:
        prepWork.read_config()
    except KeyboardInterrupt:
        print()
        warn("Setup cancelled - nothing was saved. Exiting.")
        return

    has_target = (
        normalise_nsaid(prepWork.config.get("nsaid"))
        or str(prepWork.config.get("url") or "").strip()
    )
    if not has_target:
        print()
        err(f"No Nintendo account was configured, so {APP_NAME} can't start.")
        print(
            f"{C.GRAY}Run it again with your console online, or set the "
            f'"nsaid" value in {prepWork.config_path} directly.{C.RESET}'
        )
        return

    try:
        prepWork.connect_to_discord()
        client = NxapiClient(prepWork.config, session=prepWork.session)
        run_loop(prepWork, client)
    except KeyboardInterrupt:
        print(f"\n{C.GRAY}Shutting down {APP_NAME}.{C.RESET}")
        if prepWork.RPC is not None:
            try:
                prepWork.RPC.clear()
                prepWork.RPC.close()
            except Exception as e:  # noqa: BLE001 - teardown must not raise
                # Best effort: the pipe may already be gone, but say so rather
                # than dying on the way out.
                print(f"{C.GRAY}Cleanup skipped: {e}{C.RESET}")


def run_loop(prepWork, client):
    closed = False
    presence_active = False
    show_timer = prepWork.config["show_timer"]
    accurate_timer = prepWork.config["accurate_timer"]
    stale_limit = int(prepWork.config.get("stale_seconds") or 0)
    prev_game = None
    timer = int(time()) if show_timer else None

    while True:
        clear()
        _print_header(prepWork.config_path)

        try:
            snapshot = client.fetch()
        except NxapiNotFound as e:
            err(str(e))
            if not prepWork.config["nsaid_prompt"] or not stdin_is_interactive():
                err("Set the correct NSA ID in the config file and restart.")
                with contextlib.suppress(PyPresenceException):
                    prepWork.RPC.clear()
                    prepWork.RPC.close()
                return
            try:
                prepWork.prompt_user()
            except KeyboardInterrupt:
                print()
                warn("Setup cancelled - exiting.")
                return
            # Account may have changed; reset the timer. `closed` stays accurate.
            prev_game = None
            continue
        except NxapiError as e:
            warn(str(e))
            warn(
                f"Closing RPC and hibernating "
                f"{prepWork.config['hibernate_seconds']} seconds."
            )
            # A bridge that never answers clear() would otherwise crash-loop us.
            with contextlib.suppress(PyPresenceException, RuntimeError):
                if presence_active:
                    prepWork.RPC.clear()
                prepWork.RPC.close()
            closed = True
            presence_active = False
            sleep(float(prepWork.config["hibernate_seconds"]))
            continue

        if closed:
            prepWork.connect_to_discord()
            timer = int(time()) if show_timer else None
            prev_game = None
            closed = False

        client.report(snapshot)
        client.note_cover(snapshot)
        client.note_buttons()

        # A sleeping Switch stops reporting but is still served, so treat a stale
        # timestamp like an unreachable console.
        if snapshot.state == "OFFLINE" or (
            stale_limit > 0 and snapshot.is_stale(stale_limit)
        ):
            with contextlib.suppress(PyPresenceException):
                if presence_active:
                    prepWork.RPC.clear()
            presence_active = False
            sleep(float(prepWork.config["wait_seconds"]))
            continue

        if show_timer:
            game = snapshot.title_id or snapshot.title_name
            if game != prev_game:
                timer = int(time())
                if accurate_timer and snapshot.is_in_game and snapshot.since:
                    timer = snapshot.since_epoch or timer
                prev_game = game

        # show_inactive_presence wins over show_only_in_game.
        show_inactive = prepWork.config["show_inactive_presence"] and snapshot.is_idle
        if (
            prepWork.config["show_only_in_game"]
            and not snapshot.is_in_game
            and not show_inactive
        ):
            print(
                f"{C.GRAY}Not in a game, skipping RPC update "
                f"(show_only_in_game){C.RESET}"
            )
            sleep(prepWork.config["wait_seconds"])
            continue

        try:
            prepWork.RPC.update(**_presence_kwargs(prepWork, client, snapshot, timer))
            presence_active = True
        except ServerError as e:
            err(f"Discord rejected the RPC update: {e}")
            print(
                f"{C.GRAY}Usually another instance of {APP_NAME} is running, or "
                f"the payload had something Discord wouldn't accept.{C.RESET}"
            )
        except PyPresenceException:
            # Discord closed the pipe or went away. PipeClosed, InvalidPipe and
            # the rest are all PyPresenceException subclasses, so catching the
            # base keeps a Discord restart from killing the process.
            with contextlib.suppress(PyPresenceException):
                prepWork.RPC.close()
            closed = False
            prepWork.connect_to_discord()

        sleep(prepWork.config["wait_seconds"])


if __name__ == "__main__":
    main()
