import re

from app.backends.common import (
    error,
    error_from_exception,
    loopback_number,
    safe_interface_name,
    to_cidr,
)

def _canonical(name):
    """Lo123 และ Loopback123 ผลเหมือนกัน"""
    match = re.fullmatch(r"([A-Za-z\-]+)\s*(\d[\d/.:]*)", str(name).strip())
    if not match:
        return str(name).strip().lower()
    prefix, number = match.group(1).lower(), match.group(2)
    if "loopback".startswith(prefix):
        prefix = "loopback"
    return f"{prefix}{number}"

def _field(record, key):
    """อ่านค่าจาก dict ของ TextFSM โดยไม่สนตัวพิมพ์เล็ก/ใหญ่"""
    for name, value in record.items():
        if str(name).lower() == key:
            return value
    return None

def _first(value):
    """เอา List ตัวแรก"""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value

def _normalize(interface_name, ip_info, descriptions):
    wanted = _canonical(interface_name)

    record = next(
        (r for r in ip_info if _canonical(_field(r, "interface") or "") == wanted),
        None,
    )
    if record is None:
        return None

    address = _first(_field(record, "ip_address"))
    prefix = _first(_field(record, "prefix_length"))
    ipv4 = to_cidr(address, prefix_length=prefix) if address and prefix else None

    link = str(_field(record, "link_status") or "").lower()
    admin_state = "down" if "administratively down" in link else "up"

    description = None
    for item in descriptions:
        if _canonical(_field(item, "port") or "") == wanted:
            description = _field(item, "description") or None
            break

    return {
        "name": interface_name,
        "ipv4": ipv4,
        "description": description,
        "admin_state": admin_state,
    }

def _default_netmiko_get(router, interface_name):
    from netmiko import ConnectHandler

    from app.backends.common import router_credentials

    user, password = router_credentials()
    connection = ConnectHandler(
        device_type="cisco_ios", host=router, username=user,
        password=password, timeout=10, conn_timeout=10,
    )
    try:
        ip_info = connection.send_command(
            f"show ip interface {interface_name}", use_textfsm=True
        )
        descriptions = connection.send_command(
            "show interfaces description", use_textfsm=True
        )
    finally:
        connection.disconnect()
    # ถ้า TextFSM อ่านไม่ออก netmiko จะคืนข้อความดิบ (str) ไม่ใช่ list
    if not isinstance(ip_info, list):
        ip_info = []
    if not isinstance(descriptions, list):
        descriptions = []
    return ip_info, descriptions

def _default_netmiko_delete(router, interface_name):
    from netmiko import ConnectHandler

    from app.backends.common import router_credentials

    name = f"Loopback{loopback_number(interface_name)}"
    user, password = router_credentials()
    connection = ConnectHandler(
        device_type="cisco_ios", host=router, username=user,
        password=password, timeout=10, conn_timeout=10,
    )
    try:
        before = connection.send_command(
            f"show ip interface {name}", use_textfsm=True
        )
        if not isinstance(before, list) or not before:
            return "not_found"
        connection.send_config_set([f"no interface {name}"])
        return "deleted"
    finally:
        connection.disconnect()

def get_interface_state(router, interface_name,netmiko_get=None):
    """Return normalized interface status using Netmiko + TextFSM."""
    netmiko_get = netmiko_get or _default_netmiko_get
    try:
        name = safe_interface_name(interface_name)
        ip_info, descriptions = netmiko_get(router, name)
        interface = _normalize(name, ip_info or [], descriptions or [])
        if interface is None:
            return {"status": "ok", "result": "not_found", "interface": None}
        return {"status": "ok", "result": "found", "interface": interface}
    except Exception as exc:
        return error_from_exception(exc)

def delete_interface(router, interface_name, netmiko_delete=None):
    """Delete an interface using Netmiko."""
    netmiko_delete = netmiko_delete or _default_netmiko_delete
    try:
        loopback_number(interface_name)  # ลบได้เฉพาะ Loopback
        result = netmiko_delete(router, interface_name)
    except Exception as exc:
        return error_from_exception(exc)

    if result == "deleted":
        return {"status": "ok", "result": "deleted"}
    if result == "not_found":
        return {"status": "ok", "result": "not_found", "interface": None}
    return error("backend_failed")

