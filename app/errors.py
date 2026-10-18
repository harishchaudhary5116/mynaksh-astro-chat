"""Failure handling.

Rule: invalid input is a 422. Everything else degrades instead of failing —
the user always gets an answer, and the response carries `degraded: true`
plus the reason.

  LLM down      -> retry once, then a deterministic reply built from context
  Brain down    -> answer from profile + short-term only
  Empty memory  -> answer normally, no memory claims
  No context    -> ask one clarifying question instead of inventing facts
"""

LLM_UNAVAILABLE = "llm_unavailable"
BRAIN_UNAVAILABLE = "shared_brain_unavailable"


def fallback_reply(
    profile_lines: list[str],
    memory_lines: list[str],
    missing_fields: list[str],
) -> str:
    """Written without the LLM, from the context we already selected.

    It must never claim to have answered the question, and never invent an
    astrological reading — it reflects back what we hold and asks the user to
    retry. Sounding useful while being wrong is worse than saying "not now".
    """
    parts = ["I could not reach my guidance engine just now, so here is what I can do."]

    if memory_lines:
        parts.append(
            "I still have your context: " + "; ".join(memory_lines[:3]) + "."
        )
    elif profile_lines:
        parts.append("I still have your profile: " + "; ".join(profile_lines[:2]) + ".")

    if missing_fields and not memory_lines:
        parts.append(
            "It would also help to know your "
            + " and ".join(f.replace("_", " ") for f in missing_fields)
            + "."
        )

    parts.append("Please ask me again in a moment and I will give you a full reading.")
    return " ".join(parts)


def no_context_reply(question: str) -> str:
    """Nothing on file at all: ask once rather than guess."""
    return (
        "I do not have anything on file for you yet, so I would only be guessing. "
        "Tell me your date, time and place of birth and I will answer "
        f"\"{question.strip()}\" properly."
    )
