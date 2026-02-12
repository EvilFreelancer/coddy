"""Minimal webhook HTTP server for Git platform events.

Serves health check and webhook path; verification and handlers to be
added.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from coddy.config import AppConfig

LOG = logging.getLogger("coddy.webhook")


class WebhookHandler(BaseHTTPRequestHandler):
    """Handle GET /health and POST /webhook/github (and others)."""

    config: AppConfig

    def do_GET(self) -> None:
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "coddy"}).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path == self.config.github.webhook_path:
            self._handle_github_webhook()
            return
        self.send_response(404)
        self.end_headers()

    def _handle_github_webhook(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        # TODO: verify X-Hub-Signature-256 using config.webhook_secret_resolved
        try:
            payload = json.loads(body.decode()) if body else {}
            event = self.headers.get("X-GitHub-Event", "")
            LOG.info("Webhook event: %s (payload keys: %s)", event, list(payload.keys()) if payload else [])
            from coddy.webhook.handlers import handle_github_event

            handle_github_event(self.config, event, payload)
        except json.JSONDecodeError:
            LOG.warning("Invalid webhook JSON")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"received": True}).encode())

    def log_message(self, format: str, *args: Any) -> None:
        LOG.debug(format, *args)


def run_webhook_server(config: AppConfig) -> None:
    """Run HTTP server for webhooks and health check."""
    host = config.webhook.host
    port = config.webhook.port
    WebhookHandler.config = config
    server = HTTPServer((host, port), WebhookHandler)
    LOG.info("Webhook server listening on %s:%s", host, port)
    server.serve_forever()
