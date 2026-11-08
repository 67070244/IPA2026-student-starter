import os
import re
from ipaddress import IPv4Interface, IPv4Network

import requests

import logging

logger = logging.getLogger("ipa2026.backend")

_LOOPBACK_RE = re.compile(r"Loopback(\d+)")
_SAFE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9/.\-]*")

def error(code):
    return {"status": "error", "result": code}

def error_from_exception(exc):
    logger.warning("backend error: %s: %s", type(exc).__name__, exc)
    if isinstance(exc, PermissionError):
        return error("authentication_failed")
    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ),
    ):
        return error("connection_failed")
    return error("backend_failed")

def router_credentials():
    return (
        os.environ.get("ROUTER_USER", ""),
        os.environ.get("ROUTER_PASS", ""),
    )

def loopback_number(name):
    """Loopback123 -> 123, ชื่ออื่นให้ raise ValueError"""
    match = _LOOPBACK_RE.fullmatch(str(name))
    if not match:
        raise ValueError(f"not a Loopback interface: {name!r}")
    return int(match.group(1))

def safe_interface_name(name):
    """กันชื่อที่มีช่องว่าง/ขึ้นบรรทัดใหม่/อักษรแปลก"""
    if not _SAFE_NAME_RE.fullmatch(str(name)):
        raise ValueError(f"unsafe interface name: {name!r}")
    return str(name)


def to_cidr(address, netmask=None, prefix_length=None):
    if netmask is not None:
        prefix = IPv4Network(f"0.0.0.0/{netmask}").prefixlen
    else:
        prefix = int(prefix_length)
    return f"{address}/{prefix}"