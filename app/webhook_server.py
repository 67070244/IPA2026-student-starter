"""Part 4 student implementation."""
import signal

import threading

import time

import json

import logging

import os

from concurrent.futures import ThreadPoolExecutor

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from tempfile import TemporaryDirectory

from app.integration import process_request

from app.webex_client import WEBEX_API_BASE, WebexClient

logger = logging.getLogger("ipa2026.webhook")

BACKEND_FAILED_RESPONSE = {"status": "error", "result": "backend_failed"}
MAX_BODY_BYTES = 1_000_000

class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        # TODO: implement according to Part 4 specification
        if not isinstance(event, dict):
            return None
        if event.get("resource") != "messages" or event.get("event") != "created":
            return None

        data = event.get("data")
        if not isinstance(data, dict):
            return None
        message_id = data.get("id")
        if not isinstance(message_id, str) or not message_id:
            return None

        # ไม่ตอบข้อความของตัวเอง (กัน loop) ตรวจก่อนเรียก API
        if data.get("personId") == self.bot_person_id:
            return None

        try:
            message = self.client.get_message(message_id)
        except Exception:
            logger.exception("could not fetch message %s", message_id)
            return None

        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message.get("roomId")
        if not room_id:
            return None

        try:
            result = self._process_message(message)
        except Exception:
            logger.exception("processing message %s failed", message_id)
            result = dict(BACKEND_FAILED_RESPONSE)

        try:
            self.client.send_message(room_id, json.dumps(result))
        except Exception:
            logger.exception("could not reply to room %s", room_id)

        return result
    def _process_message(self, message):
        mentioned_people = message.get("mentionedPeople")
        files = message.get("files") or []
        if not isinstance(files, list):
            files = []

        if len(files) > 1:
            return {"status": "error", "result": "multiple_attachments"}
        if not files:
            return self.processor(mentioned_people, None, self.bot_person_id)

        content = self.client.download_file(files[0])

        # โฟลเดอร์ชั่วคราวถูกลบอัตโนมัติ แม้ processor จะ raise
        with TemporaryDirectory() as directory:
            path = Path(directory) / "request.yaml"
            path.write_bytes(content)
            return self.processor(mentioned_people, path, self.bot_person_id)

def _json_response(handler, status, body):
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)

def make_http_handler(submit_event):
    # TODO: implement according to Part 4 specification
    class WebhookRequestHandler(BaseHTTPRequestHandler):
        def _path(self):
            return self.path.split("?", 1)[0]

        def _not_found(self):
            _json_response(self, 404, {"status": "error", "result": "not_found"})

        def _invalid_event(self):
            _json_response(self, 400, {"status": "error", "result": "invalid_event"})

        def do_GET(self):
            if self._path() == "/health":
                _json_response(self, 200, {"status": "ok", "result": "healthy"})
            else:
                self._not_found()

        def do_POST(self):
            if self._path() != "/webhook":
                self._not_found()
                return

            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._invalid_event()
                return

            if not 1 <= length <= MAX_BODY_BYTES:
                self._invalid_event()
                return

            body = self.rfile.read(length)
            if len(body) != length:
                self._invalid_event()
                return

            try:
                event = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                self._invalid_event()
                return

            if not isinstance(event, dict):
                self._invalid_event()
                return

            try:
                submit_event(event)
            except Exception:
                logger.exception("could not queue event")
                _json_response(self, 500, BACKEND_FAILED_RESPONSE)
                return

            _json_response(self, 200, {"status": "ok", "result": "accepted"})

        def do_PUT(self):
            self._not_found()

        def do_DELETE(self):
            self._not_found()

        def do_PATCH(self):
            self._not_found()

        def log_message(self, format, *args):
            logger.info("%s - %s", self.address_string(), format % args)

    return WebhookRequestHandler

def _resolve_bot_person_id(client, attempts=5, delay=2.0):
    """ถาม Webex ว่า bot นี้คือใคร (ลองซ้ำเมื่อเครือข่ายสะดุด)"""
    last_error = None
    for attempt in range(attempts):
        try:
            response = client.session.get(
                f"{WEBEX_API_BASE}/people/me",
                headers=client.headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()["id"]
        except Exception as exc:
            last_error = exc
            logger.warning(
                "people/me failed (%s/%s): %s", attempt + 1, attempts, exc
            )
            time.sleep(delay)
    raise RuntimeError("could not resolve the bot person ID") from last_error

def main():
    # TODO: implement according to Part 4 specification
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "8000"))

    try:
        client = WebexClient()
    except PermissionError:
        logger.error("WEBEX_BOT_TOKEN is not set; refusing to start")
        raise SystemExit(1)

    bot_person_id = _resolve_bot_person_id(client)
    logger.info("bot person id resolved")

    handler = WebexEventHandler(client, bot_person_id)

    # worker เดียว: คำขอรันทีละอัน การแก้ router จึงไม่ซ้อนกัน
    executor = ThreadPoolExecutor(max_workers=1)

    def run_event(event):
        try:
            handler.handle_event(event)
        except Exception:
            logger.exception("unhandled error while processing an event")

    def submit_event(event):
        executor.submit(run_event, event)

    server = ThreadingHTTPServer((host, port), make_http_handler(submit_event))

    # docker stop ส่ง SIGTERM: ปิดเซิร์ฟเวอร์เองแทนที่จะรอให้ถูกบังคับฆ่า
    def stop(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)

    logger.info("listening on %s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        executor.shutdown(wait=True)

if __name__ == "__main__":
    main()
