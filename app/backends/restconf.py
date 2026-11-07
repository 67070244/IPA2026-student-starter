from ipaddress import IPv4Network, IPv4Interface
from app.backends import planning
import requests
import os
import re

REQUEST_TIMEOUT = 10
YANG_JSON = "application/yang-data+json"

def _error(code):
    return {"status": "error", "result": code}

def _error_from_exception(exc):
    if isinstance(exc, PermissionError):
        return _error("authentication_failed")
    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ),
    ):
        return _error("connection_failed")
    return _error("backend_failed")

def _auth():
    return (
        os.environ.get("ROUTER_USER", ""),
        os.environ.get("ROUTER_PASS", ""),
    )

def _default_http_get(url):
    return requests.get(
        url,
        auth=_auth(),
        headers={"Accept": YANG_JSON},
        verify=False,
        timeout=REQUEST_TIMEOUT,
    )

def _default_http_put(url, json):
    return requests.put(
        url,
        json=json,
        auth=_auth(),
        headers={"Accept": YANG_JSON, "Content-Type": YANG_JSON},
        verify=False,
        timeout=REQUEST_TIMEOUT,
    )

def get_interface_state(router, interface_name, http_get=None):
    """Return normalized interface status using RESTCONF."""
    http_get = http_get or _default_http_get
    try:
        url = (
            f"https://{router}/restconf/data/"
            f"ietf-interfaces:interfaces/interface={interface_name}"
        )
        response = http_get(url)
        code = response.status_code

        if code == 404:
            return {"status": "ok", "result": "not_found", "interface": None}
        if code in (401, 403):
            return _error("authentication_failed")
        if code != 200:
            return _error("backend_failed")

        data = response.json()["ietf-interfaces:interface"]

        ipv4 = None
        addresses = data.get("ietf-ip:ipv4", {}).get("address", [])
        if addresses:
            addr = addresses[0]
            prefix = IPv4Network(f"0.0.0.0/{addr['netmask']}").prefixlen
            ipv4 = f"{addr['ip']}/{prefix}"

        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": data["name"],
                "ipv4": ipv4,
                "description": data.get("description"),
                "admin_state": "up" if data.get("enabled") else "down",
            },
        }
    except Exception as exc:
        return _error_from_exception(exc)

def plan_interface(router, desired_interface, http_get=None):
    """Return create/update/no_change plan using RESTCONF status."""
    def status(router_, name):
        return get_interface_state(router_, name, http_get)
    
    return planning.plan_interface(router, desired_interface, status)

def apply_interface(router, desired_interface, http_put=None):
    """Apply complete desired interface state using RESTCONF."""
    http_put = http_put or _default_http_put
    try:
        #รับเฉพาะ Loopback
        match = re.fullmatch(r"Loopback(\d+)", desired_interface["name"])
        if not match:
            return _error("backend_failed")
        number = int(match.group(1))

        iface = IPv4Interface(desired_interface["ipv4"])
        loopback = {
            "name": number,
            "description": desired_interface["description"],
            "ip": {
                "address": {
                    "primary": {
                        "address": str(iface.ip),
                        "mask": str(iface.network.netmask),
                    }
                }
            },
        }
        if desired_interface["admin_state"] == "down":
            loopback["shutdown"] = [None]

        payload = {"Cisco-IOS-XE-native:Loopback": loopback}
        url = (
            f"https://{router}/restconf/data/"
            f"Cisco-IOS-XE-native:native/interface/Loopback={number}"
        )

        response = http_put(url, json=payload)
        code = response.status_code

        if code in (200, 201, 204):
            return {"status": "ok", "result": "applied"}
        if code in (401, 403):
            return _error("authentication_failed")
        return _error("backend_failed")
    except Exception as exc:
        return _error_from_exception(exc)