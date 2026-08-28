"""Pending-request store.

In memory for now: a restart forgets outstanding cards, and two instances would not share state.
The interface is intentionally tiny so it can be swapped for SQLite / Redis / Cosmos without touching
the guards or the service.
"""

from __future__ import annotations

import time

from .models import PendingRequest


class PendingStore:
    """In-memory store of sent-but-undecided (or recently decided) requests, keyed by request id.

    Attributes:
        _ttl: Seconds a request is kept before it is forgotten.
        _items: The requests.
    """

    def __init__(self, ttl_s: int) -> None:
        """Create an empty store.

        Args:
            ttl_s: How long (seconds) a request stays answerable / remembered.
        """
        self._ttl = ttl_s
        self._items: dict[str, PendingRequest] = {}

    def add(self, req: PendingRequest) -> None:
        """Remember a request, pruning expired ones first.

        Args:
            req: The request to store; replaces any entry with the same id.
        """
        self._prune()
        self._items[req.request_id] = req

    def get(self, request_id: str | None) -> PendingRequest | None:
        """Look up a request, pruning expired ones first.

        Args:
            request_id: The id from a card click; ``None`` or unknown ids yield ``None``.

        Returns:
            PendingRequest | None: The live request object (mutated in place when decided), or ``None``.
        """
        self._prune()
        return self._items.get(request_id or "")

    def _prune(self) -> None:
        """Drop requests older than the TTL."""
        cutoff = time.time() - self._ttl
        for k in [k for k, v in self._items.items() if v.created < cutoff]:
            del self._items[k]
