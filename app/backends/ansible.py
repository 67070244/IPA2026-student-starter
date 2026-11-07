import json
import os
import re
import subprocess
from pathlib import Path

from app.backends.common import (
    error_from_exception,
    loopback_number,
)
from ipaddress import IPv4Interface

ANSIBLE_DIR = Path(__file__).resolve().parents[2] / "ansible"
PLAYBOOK_TIMEOUT = 60

_UNSAFE_TEXT = re.compile(r"[\x00-\x1f\x7f]|\{\{|\{%|\{#")

_AUTH_MARKERS = ("authentication failed", "permission denied", "invalid credentials")
_CONNECTION_MARKERS = ("unreachable", "timed out", "connection refused", "no route to host")


def _default_run_playbook(variables):
    command = [
        "ansible-playbook",
        "-i", str(ANSIBLE_DIR / "inventory.ini"),
        str(ANSIBLE_DIR / "apply_interface.yml"),
        "--extra-vars", json.dumps(variables),
    ]
    env = dict(os.environ, ANSIBLE_HOST_KEY_CHECKING="False", ANSIBLE_NOCOLOR="1")

    try:
        done = subprocess.run(
            command, capture_output=True, text=True,
            timeout=PLAYBOOK_TIMEOUT, env=env, cwd=str(ANSIBLE_DIR),
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectionError("ansible-playbook timed out") from exc

    if done.returncode == 0:
        return

    output = f"{done.stdout}\n{done.stderr}".lower()
    # ปัญหารหัสผ่านก็แสดงเป็น "unreachable" ด้วย -> เช็ก auth ก่อน
    if any(m in output for m in _AUTH_MARKERS):
        raise PermissionError("router rejected the credentials")
    if done.returncode == 4 or any(m in output for m in _CONNECTION_MARKERS):
        raise ConnectionError("router is unreachable")
    raise RuntimeError(f"ansible-playbook failed ({done.returncode})")

def apply_interface(router, desired_interface, run_playbook=None):
    """Apply complete desired interface state using Ansible."""
    run_playbook = run_playbook or _default_run_playbook
    try:
        loopback_number(desired_interface["name"])  # เฉพาะ Loopback

        description = str(desired_interface["description"])
        if _UNSAFE_TEXT.search(description):
            raise ValueError("description contains unsupported characters")

        iface = IPv4Interface(desired_interface["ipv4"])
        run_playbook(
            {
                "router": router,
                "interface_name": desired_interface["name"],
                "description": description,
                "ipv4_address": str(iface.ip),
                "netmask": str(iface.network.netmask),
                "shutdown": desired_interface["admin_state"] == "down",
            }
        )
        return {"status": "ok", "result": "applied"}
    except Exception as exc:
        return error_from_exception(exc)
