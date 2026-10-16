"""The orchestrator — the file a reviewer opens first.

Reads top-to-bottom exactly like the flow in the brief:

    understand query -> select context -> build prompt -> generate -> update memory

Keep it under ~120 lines. Every step delegates; no business logic inline.
"""
