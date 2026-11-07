import xml.etree.ElementTree as ET
from ipaddress import IPv4Interface, IPv4Network
from xml.sax.saxutils import escape
import re
import os

from app.backends import planning
from app.backends.common import error as _error
from app.backends.common import error_from_exception as _error_from_exception
from app.backends.common import router_credentials as _auth

IF_NS = "urn:ietf:params:xml:ns:yang:ietf-interfaces"
IP_NS = "urn:ietf:params:xml:ns:yang:ietf-ip"
NETCONF_PORT = 830
REQUEST_TIMEOUT = 10

def _text(parent, tag, ns):
    """อ่านข้อความของ element ลูก ถ้าไม่มีให้คืน None"""
    node = parent.find(f"{{{ns}}}{tag}")
    if node is None or node.text is None:
        return None
    return node.text.strip()

def _translate_ncclient_error(exc):
    """แปลง exception ของ ncclient/paramiko"""
    import paramiko
    from ncclient.operations import TimeoutExpiredError
    from ncclient.transport.errors import (
        AuthenticationError,
        SessionCloseError,
        SSHError,
        TransportError,
    )

    if isinstance(exc, (AuthenticationError, paramiko.AuthenticationException)):
        return PermissionError(str(exc))
    if isinstance(
        exc,
        (
            SSHError,
            SessionCloseError,
            TransportError,
            TimeoutExpiredError,
            paramiko.SSHException,
            OSError,
        ),
    ):
        return ConnectionError(str(exc))
    return RuntimeError(str(exc))

def _connect(router):
    from ncclient import manager

    user, password = _auth()
    return manager.connect(
        host=router,
        port=NETCONF_PORT,
        username=user,
        password=password,
        hostkey_verify=False,
        allow_agent=False,
        look_for_keys=False,
        timeout=REQUEST_TIMEOUT,
        device_params={"name": "iosxe"},
    )

def _default_get_config(router, filter_xml):
    try:
        with _connect(router) as session:
            reply = session.get_config(
                source="running", filter=("subtree", filter_xml)
            )
            return reply.data_xml
    except Exception as exc:
        raise _translate_ncclient_error(exc) from exc

def _default_edit_config(router, config_xml):
    try:
        with _connect(router) as session:
            session.edit_config(target="running", config=config_xml)
    except Exception as exc:
        raise _translate_ncclient_error(exc) from exc

def get_interface_state(router, interface_name, netconf_get_config=None):
    """Return normalized interface status using NETCONF."""
    netconf_get_config = netconf_get_config or _default_get_config
    try:
        filter_xml = (
            f'<interfaces xmlns="{IF_NS}">'
            f"<interface><name>{escape(interface_name)}</name></interface>"
            f"</interfaces>"
        )
        xml_text = netconf_get_config(router, filter_xml)
        root = ET.fromstring(xml_text)

        # หา interface ที่ชื่อตรงกัน
        iface = None
        for node in root.iter(f"{{{IF_NS}}}interface"):
            if _text(node, "name", IF_NS) == interface_name:
                iface = node
                break
        if iface is None:
            return {"status": "ok", "result": "not_found", "interface": None}

        ipv4 = None
        address = iface.find(f"{{{IP_NS}}}ipv4/{{{IP_NS}}}address")
        if address is not None:
            ip = _text(address, "ip", IP_NS)
            netmask = _text(address, "netmask", IP_NS)
            prefix_length = _text(address, "prefix-length", IP_NS)
            if netmask:
                prefix = IPv4Network(f"0.0.0.0/{netmask}").prefixlen
            else:
                prefix = int(prefix_length)
            ipv4 = f"{ip}/{prefix}"

        enabled = _text(iface, "enabled", IF_NS)

        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": interface_name,
                "ipv4": ipv4,
                "description": _text(iface, "description", IF_NS),
                "admin_state": "down" if enabled == "false" else "up",
            },
        }
    except Exception as exc:
        return _error_from_exception(exc)

def plan_interface(router, desired_interface, netconf_get_config=None):
    """Return create/update/no_change plan using NETCONF status."""
    def status(router_, name):
        return get_interface_state(router_, name, netconf_get_config)

    return planning.plan_interface(router, desired_interface, status)


def apply_interface(router,desired_interface,netconf_edit_config=None):
    """Apply complete desired interface state using NETCONF."""
    netconf_edit_config = netconf_edit_config or _default_edit_config
    try:
        # รับเฉพาะ Loopback เพื่อไม่ให้แตะ interface อื่นของ router
        match = re.fullmatch(r"Loopback(\d+)", desired_interface["name"])
        if not match:
            return _error("backend_failed")
        number = int(match.group(1))

        iface = IPv4Interface(desired_interface["ipv4"])
        description = escape(str(desired_interface["description"]))
        shutdown = (
            "<shutdown/>" if desired_interface["admin_state"] == "down" else ""
        )

        # operation="replace" แทนที่ Loopback ทั้งตัว ไม่ให้ IP เก่าค้างเป็น secondary
        config_xml = (
            '<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" '
            'xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">'
            '<native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">'
            "<interface>"
            '<Loopback nc:operation="replace">'
            f"<name>{number}</name>"
            f"<description>{description}</description>"
            "<ip><address><primary>"
            f"<address>{iface.ip}</address>"
            f"<mask>{iface.network.netmask}</mask>"
            "</primary></address></ip>"
            f"{shutdown}"
            "</Loopback>"
            "</interface>"
            "</native>"
            "</config>"
        )

        netconf_edit_config(router, config_xml)
        return {"status": "ok", "result": "applied"}
    except Exception as exc:
        return _error_from_exception(exc)
