"""Create or update the Webex webhooks for both IPA2026 rooms.
Usage: python scripts/register_webhook.py https://xxxx.trycloudflare.com
Reads WEBEX_BOT_TOKEN from the environment or from .env.
"""

import os
import sys
from pathlib import Path

import requests

API = "https://webexapis.com/v1"
ROOM_TITLES = ("IPA2026", "IPA2026 Exam Room")

def load_token():
    token = os.environ.get("WEBEX_BOT_TOKEN")
    if token:
        return token
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("WEBEX_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None

def call(method, path, token, **kwargs):
    response = requests.request(
        method, f"{API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10, **kwargs,
    )
    response.raise_for_status()
    return response.json()


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    token = load_token()
    if not token:
        print("WEBEX_BOT_TOKEN not found")
        return 1

    target = argv[1].rstrip("/")
    if not target.startswith("https://"):
        print("URL must start with https://")
        return 2
    if not target.endswith("/webhook"):
        target += "/webhook"

    rooms = call("GET", "/rooms?max=1000", token).get("items", [])
    room_ids = {room["title"]: room["id"] for room in rooms}
    hooks = call("GET", "/webhooks?max=100", token).get("items", [])

    code = 0
    for title in ROOM_TITLES:
        room_id = room_ids.get(title)
        if room_id is None:
            print(f"[missing] bot is not a member of {title!r}")
            code = 1
            continue
        name = "ipa2026-" + title.lower().replace(" ", "-")
        existing = next((h for h in hooks if h.get("name") == name), None)
        if existing:
            call("PUT", f"/webhooks/{existing['id']}", token,
                 json={"name": name, "targetUrl": target})
            print(f"[updated] {title!r} -> {target}")
        else:
            call("POST", "/webhooks", token, json={
                "name": name, "targetUrl": target,
                "resource": "messages", "event": "created",
                "filter": f"roomId={room_id}",
            })
            print(f"[created] {title!r} -> {target}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))