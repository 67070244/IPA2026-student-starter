"""Part 4 student implementation."""
import logging

from app.backends import ansible, netconf, netmiko_textfsm, restconf
from app.backends.common import error

logger = logging.getLogger(__name__)

# (method, action) -> (โมดูล, ชื่อฟังก์ชัน, ส่งอะไรให้ backend)
ROUTES = {
    ("restconf", "status"): (restconf, "get_interface_state", "name"),
    ("restconf", "plan"): (restconf, "plan_interface", "interface"),
    ("restconf", "apply"): (restconf, "apply_interface", "interface"),
    ("netconf", "status"): (netconf, "get_interface_state", "name"),
    ("netconf", "plan"): (netconf, "plan_interface", "interface"),
    ("netconf", "apply"): (netconf, "apply_interface", "interface"),
    ("ansible", "apply"): (ansible, "apply_interface", "interface"),
    ("netmiko-textfsm", "status"): (netmiko_textfsm, "get_interface_state", "name"),
    ("netmiko-textfsm", "delete"): (netmiko_textfsm, "delete_interface", "name"),
}

def dispatch_request(data):
    # TODO: implement according to Part 4 specification
    route = ROUTES.get((data.get("method"), data.get("action")))
    if route is None:
        return error("invalid_action")

    module, function_name, argument = route
    router = data["router"]
    interface = data["desired"]["interface"]

    # หาฟังก์ชัน "ตอนเรียก" (ไม่เก็บไว้ในตาราง) เพื่อให้เทสต์สลับเป็น fake ได้
    backend = getattr(module, function_name)

    try:
        if argument == "name":
            return backend(router, interface["name"])
        return backend(router, interface)
    except Exception:
        logger.exception("backend %s.%s raised", module.__name__, function_name)
        return error("backend_failed")
