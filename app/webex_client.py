"""Part 4 student implementation."""

import os

import requests

WEBEX_API_BASE = 'https://webexapis.com/v1'
REQUEST_TIMEOUT = 10

class WebexClient:
    def __init__(self, token=None, session=None):
        # TODO: implement according to Part 4 specification
        self.token = token or os.environ.get("WEBEX_BOT_TOKEN")
        if not self.token:
            raise PermissionError("WEBEX_BOT_TOKEN is not set")
        self.session = session if session is not None else requests.Session()

    @property
    def headers(self):
        # TODO: implement according to Part 4 specification
        return {"Authorization": f"Bearer {self.token}"}

    def get_message(self, message_id):
        # TODO: implement according to Part 4 specification
        response = self.session.get(
            f"{WEBEX_API_BASE}/messages/{message_id}",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def download_file(self, file_url):
        # TODO: implement according to Part 4 specification
        response = self.session.get(
            file_url,
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.content

    def send_message(self, room_id, text):
        # TODO: implement according to Part 4 specification
        response = self.session.post(
            f"{WEBEX_API_BASE}/messages",
            headers=self.headers,
            json={"roomId": room_id, "text": text},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
