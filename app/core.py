import yaml

ALLOWED_ROUTERS = (
    "10.0.29.101", "10.0.29.102", "10.0.29.103",
    "10.0.29.104", "10.0.29.105",
)

SUPPORTED_ACTIONS = {
    "restconf": ("status", "plan", "apply"),
    "netconf": ("status", "plan", "apply"),
    "ansible": ("apply",),
    "netmiko-textfsm": ("status", "delete"),
}

def _error(code):
    return {"status": "error", "result": code}

def validate_request(data):
    """
    Validate one IPA2026 desired-state request.
    Return a response dictionary according to specs/response-spec-v1.md.
    """
    # TODO: implement
    if not isinstance(data, dict):
        return _error("invalid_yaml")
    
    version = data.get("version")

    #version = 1
    if type(version) is not int or version != 1:
            return _error("invalid_version")

    #router
    if data.get("router") is None:
        return _error("missing_router")
    if data["router"] not in ALLOWED_ROUTERS:
        return _error("invalid_router")

    #method
    if data.get("method") is None:
        return _error("missing_method")
    if data["method"] not in SUPPORTED_ACTIONS:
        return _error("invalid_method")

    #action
    if data.get("action") is None:
        return _error("missing_action")
    if data["action"] not in SUPPORTED_ACTIONS[data["method"]]:
        return _error("invalid_action")

    #desired -> interface -> name
    desired = data.get("desired")

    if not isinstance(desired, dict):
        return _error("missing_desired")
    
    interface = desired.get("interface")

    if not isinstance(interface, dict):
        return _error("missing_interface")
    if not interface.get("name"):
        return _error("missing_interface_name")

    #plan กับ apply
    if data["action"] in ("plan", "apply"):
        if interface.get("ipv4") is None:
            return _error("missing_ipv4")
        if interface.get("description") is None:
            return _error("missing_description")
        if interface.get("admin_state") is None:
            return _error("missing_admin_state")
        if interface["admin_state"] not in ("up", "down"):
            return _error("invalid_admin_state")

    return {"status": "ok", "result": "accepted"}

def load_request_file(path):
    """Return (data, None) on success or (None, error_response)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError):
        return None, _error("invalid_yaml")

    if not isinstance(data, dict):
        return None, _error("invalid_yaml")
    return data, None


def process_request_file(path):
    data, err = load_request_file(path)
    if err is not None:
        return err
    return validate_request(data)

def process_request_file(path):
    """
    Read a YAML request file, validate it, and return a response dictionary.
    """
    # TODO: implement
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError:
        return _error("invalid_yaml")
    return validate_request(data)

def load_request_file(path):
    """Return (data, None) on success or (None, error_response)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError):
        return None, _error("invalid_yaml")

    if not isinstance(data, dict):
        return None, _error("invalid_yaml")
    return data, None

def process_request_file(path):
    data, err = load_request_file(path)
    if err is not None:
        return err
    return validate_request(data)
