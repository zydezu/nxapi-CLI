"""Manual presence test - pushes the live presence to Discord."""

import argparse
import sys
from pathlib import Path
from time import sleep, time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pypresence import DiscordNotFound, InvalidID, InvalidPipe, ServerError
from pypresence.presence import Presence

from nxapi_cli.config import PrepWork, default_config
from nxapi_cli.nxapi import NxapiClient, PresenceSnapshot

WAIT = 15

SIMULATED = PresenceSnapshot(
    nsaid="0000000000000000",
    account_name="Simulated Account",
    avatar_url="",
    state="ONLINE",
    platform=1,
    updated_at=None,
    title_id="0400c3f00006e000",
    title_name="Mario Kart World",
    image_url="https://nxapi-presence.fancy.org.uk/api/presence/resources/atum/i/c/ef905731495643798a0b3e51ab8f32b6_1024.jpeg",
    total_play_time=16989,
)


def load_config():
    prep = PrepWork()
    if prep.config_path.is_file():
        prep.read_config()
        print(f"Loaded config from {prep.config_path}")
    else:
        prep.config = default_config.copy()
        print(f"No config found at {prep.config_path} - using defaults.")
    return prep


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="push fake 'in game' data instead of polling the presence server",
    )
    args = parser.parse_args()

    prep = load_config()
    client = NxapiClient(prep.config)

    client_id = prep.config["client_id"]
    print(f"Connecting to Discord (client_id={client_id})...")
    rpc = Presence(client_id)
    try:
        rpc.connect()
    except (DiscordNotFound, InvalidPipe, ConnectionRefusedError) as e:
        print(f"Could not connect to Discord: {e}")
        print("Make sure Discord is running.")
        return
    print("Connected.\n")

    snapshot = SIMULATED if args.simulate else client.fetch()
    timer = None
    if client.config["show_timer"]:
        timer = snapshot.since_epoch or int(time())

    from nxapi_cli.__main__ import _presence_kwargs

    kwargs = _presence_kwargs(prep, client, snapshot, timer)

    print(
        f"Setting presence: {snapshot.title_name or snapshot.state} ({snapshot.title_id})"
    )
    for key, value in kwargs.items():
        print(f"  {key}: {value}")
    print(f"\nUpdating every {WAIT}s - press Ctrl+C to stop.\n")

    try:
        while True:
            try:
                rpc.update(**kwargs)
                print("Presence updated.")
            except (InvalidPipe, InvalidID):
                print("Lost Discord connection, reconnecting...")
                rpc.close()
                rpc = Presence(client_id)
                rpc.connect()
            except ServerError as e:
                print(f"Discord rejected update: {e}")
            sleep(WAIT)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        rpc.clear()
        rpc.close()


if __name__ == "__main__":
    main()
