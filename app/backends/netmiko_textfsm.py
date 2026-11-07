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

def _show(connection, command):
    """รันคำสั่ง show คืน list ของ dict หรือ None เมื่อ IOS ปฏิเสธคำสั่ง
    (เช่น interface ที่ไม่มีอยู่)"""
    from ntc_templates.parse import parse_output

    raw = connection.send_command(command)  # ไม่ใช้ use_textfsm
    lowered = raw.lower()
    if "% invalid" in lowered or "invalid input" in lowered:
        return None
    return parse_output(platform="cisco_ios", command=command, data=raw)

def _translate_netmiko_error(exc):
    """แปลง exception ของ Netmiko/paramiko ให้เป็นชนิดที่ error_from_exception รู้จัก
    ตรวจจากชื่อคลาส เพื่อไม่ต้อง import netmiko/paramiko (ใน venv และ CI อาจไม่มี)"""
    if isinstance(exc, PermissionError):
        return exc
    names = {cls.__name__ for cls in type(exc).__mro__}
    if names & {"NetmikoAuthenticationException", "AuthenticationException"}:
        return PermissionError(str(exc))
    if names & {"NetmikoTimeoutException", "SSHException"} or isinstance(exc, OSError):
        return ConnectionError(str(exc))
    return exc

def _default_netmiko_get(router, interface_name):
    from netmiko import ConnectHandler

    from app.backends.common import router_credentials

    user, password = router_credentials()
    connection = ConnectHandler(
        device_type="cisco_ios", host=router, username=user,
        password=password, timeout=30, conn_timeout=30,
        auth_timeout=30, banner_timeout=30,
    )
    try:
        ip_info = _show(connection, f"show ip interface {interface_name}")
        if ip_info is None:
            return [], []
        descriptions = _show(connection, "show interfaces description") or []
    finally:
        connection.disconnect()
    return ip_info, descriptions

def _default_netmiko_delete(router, interface_name):
    from netmiko import ConnectHandler

    from app.backends.common import router_credentials

    name = f"Loopback{loopback_number(interface_name)}"
    user, password = router_credentials()
    connection = ConnectHandler(
        device_type="cisco_ios", host=router, username=user,
        password=password, timeout=30, conn_timeout=30,
        auth_timeout=30, banner_timeout=30,
    )
    try:
        before = _show(connection, f"show ip interface {name}")
        if not before:
            return "not_found"
        connection.send_config_set([f"no interface {name}"])
        after = _show(connection, f"show ip interface {name}")
        if after:
            raise RuntimeError(f"{name} still present after delete")
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
        return error_from_exception(_translate_netmiko_error(exc))

def delete_interface(router, interface_name, netmiko_delete=None):
    """Delete an interface using Netmiko."""
    netmiko_delete = netmiko_delete or _default_netmiko_delete
    try:
        loopback_number(interface_name)  # ลบได้เฉพาะ Loopback
        result = netmiko_delete(router, interface_name)
    except Exception as exc:
        return error_from_exception(_translate_netmiko_error(exc))

    if result == "deleted":
        return {"status": "ok", "result": "deleted"}
    if result == "not_found":
        return {"status": "ok", "result": "not_found", "interface": None}
    return error("backend_failed")

