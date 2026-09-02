# Shared in-memory push notification queue.
# Populated by the push_proposals APScheduler job in main.py.
# Drained on each POST /chat response in conversation/router.py.
_push_queue: list[str] = []
