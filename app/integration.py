"""Part 4 student implementation."""
import logging

from app.backends.common import error
from app.core import load_request_file, validate_request
from app.dispatcher import dispatch_request
from app.request_handler import validate_webex_envelope

logger = logging.getLogger(__name__)

def process_request(mentioned_people, attachment_path, bot_person_id):
    # TODO: implement according to Part 4 specification
    # 1: mention และไฟล์แนบ
    envelope_error = validate_webex_envelope(
        mentioned_people, attachment_path, bot_person_id
    )
    if envelope_error is not None:
        return envelope_error

    # 2: อ่าน YAML ครั้งเดียว แล้วตรวจ
    data, load_error = load_request_file(attachment_path)
    if load_error is not None:
        return load_error

    validation = validate_request(data)
    if validation.get("status") != "ok":
        return validation

    # 3: ส่งให้ backend
    try:
        return dispatch_request(data)
    except Exception:
        logger.exception("dispatch failed")
        return error("backend_failed")
