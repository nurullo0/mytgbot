"""
Lightweight in-memory throttle cache. Keeps the last action timestamp per
user and answers whether enough time has passed since the last action.
No external dependency (no Redis required) - good enough for a single
process bot serving thousands of users, since it's just a dict lookup.
"""

import time
from typing import Dict


class ThrottleCache:
    def __init__(self):
        self._last_seen: Dict[int, float] = {}

    def is_throttled(self, user_id: int, rate: float) -> bool:
        now = time.monotonic()
        last = self._last_seen.get(user_id)
        if last is not None and (now - last) < rate:
            return True
        self._last_seen[user_id] = now
        return False


throttle_cache = ThrottleCache()
