"""Events POSTed to the client's webhook, so it never has to poll."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.request

from core.config import settings

log = logging.getLogger("cva.webhooks")
TIMEOUT_S = 5


def send(client_id: str, event: str, data: dict) -> None:
    """Best effort: a failed delivery is logged; the caller can always GET the state."""
    url = settings.webhooks.get(client_id)
    if not url:
        return
    body = json.dumps({"event": event, "data": data}).encode()
    headers = {"Content-Type": "application/json"}
    if settings.webhook_secret:
        signature = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-CVA-Signature"] = f"sha256={signature}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        urllib.request.urlopen(request, timeout=TIMEOUT_S).close()
    except OSError as exc:
        log.warning("webhook %s to %s failed: %s", event, client_id, exc)
