"""Short-term conversation context: the last N turns of one session.

In-process `deque(maxlen=N)` per session_id. Never written to the graph.
Production note: swap this class for Redis; nothing else changes.
"""
