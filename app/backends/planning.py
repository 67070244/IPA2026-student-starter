from app.planner import build_plan

def plan_interface( router, desired_interface, get_interface_state):
    """Build a Part 2 plan from backend status."""
    status = get_interface_state(router, desired_interface["name"])

    if status["status"] != "ok":
        return status                      # error คืนตามเดิม

    if status["result"] == "found":
        current = status["interface"]
    else:                                  # not_found
        current = None

    return build_plan(desired_interface, current)
    raise NotImplementedError
