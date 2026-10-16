"""Replays the conversation from the assignment brief, start to finish.

Prints `context_used` at every step so the Shared Brain is visible without
opening Neo4j Browser:

    1. Rahul introduces himself and mentions a job switch   -> memory created
    2. "What should I focus on for my career?"              -> memory used
    3. "Why do you say that?"                               -> short-term only
    4. new session: "What do you remember about my career?" -> memory recalled

Run with the server up:  python samples/demo.py
"""
