"""Failure handling.

Rule: invalid input is a 422. Everything else degrades instead of failing —
the user always gets an answer, and the response carries `degraded: true`
plus the reason.

  LLM down      -> retry once, then a deterministic reply built from context
  Brain down    -> answer from profile + short-term only
  Empty memory  -> answer normally, no memory claims
  No context    -> ask one clarifying question instead of inventing facts
"""
