"""
Async webhook dispatch with retry logic.

Sends JSON payloads to registered webhook URLs when events occur.
Uses asyncio background tasks for non-blocking delivery.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from . import database

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 5
WEBHOOK_TIMEOUT_SECONDS = 10


async def _send_webhook(url: str, payload: dict) -> bool:
    """Send a POST request to a webhook URL. Returns True on success (2xx)."""
    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Launatrausti-Webhooks/1.0"},
        )
        response.raise_for_status()
        return True


async def _deliver_webhook(url: str, payload: dict) -> None:
    """Deliver a webhook with 1 retry after RETRY_DELAY_SECONDS on failure."""
    try:
        await _send_webhook(url, payload)
        logger.info("Webhook delivered to %s", url)
    except Exception as exc:
        logger.warning("Webhook delivery failed for %s: %s — retrying in %ds", url, exc, RETRY_DELAY_SECONDS)
        await asyncio.sleep(RETRY_DELAY_SECONDS)
        try:
            await _send_webhook(url, payload)
            logger.info("Webhook retry succeeded for %s", url)
        except Exception as retry_exc:
            logger.error("Webhook retry also failed for %s: %s", url, retry_exc)


async def dispatch_event(event_type: str, data: dict) -> None:
    """
    Dispatch a webhook event to all registered URLs for this event type.
    Creates background tasks so the caller is not blocked.
    """
    webhooks = database.get_webhooks_for_event(event_type)
    if not webhooks:
        return

    payload = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    for webhook in webhooks:
        asyncio.create_task(_deliver_webhook(webhook["url"], payload))


def fire_event(event_type: str, data: dict) -> None:
    """
    Fire a webhook event. Works from both async and sync contexts.
    In async context (FastAPI), creates background tasks.
    In sync context (scripts), runs synchronously.
    """
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context — schedule as a background task
        loop.create_task(dispatch_event(event_type, data))
    except RuntimeError:
        # No running event loop — run synchronously
        asyncio.run(dispatch_event(event_type, data))
