"""Every prompt template lives here, so prompts can be reviewed and diffed
in one place instead of being scattered through the code."""

CHAT_SYSTEM = """You are MyNaksh, a warm and practical astrology guide.

Answer the user's question directly, in two or three short paragraphs.
Weave in what you know about them only where it genuinely applies — never
list their details back at them, and never invent a detail you were not given.
If something you would need is missing, ask one short question for it.
Keep astrology light and encouraging; give advice a person can actually act on.
"""

# Section headers double as the contract with the fake provider used in tests:
# anything the model should treat as "known" is a "- " bullet under one of these.
PROFILE_HEADER = "## What you know about this user"
MEMORY_HEADER = "## Relevant things they told you before"
HISTORY_HEADER = "## Recent conversation"
MISSING_HEADER = "## Not on record (ask, do not assume)"


def build_chat_system(
    profile_lines: list[str],
    memory_lines: list[str],
    missing_fields: list[str] | None = None,
) -> str:
    """Assemble the system prompt from the selected context only.

    What is *not* here matters as much as what is: no full graph dump, no full
    transcript. Only the lines context selection chose.
    """
    blocks = [CHAT_SYSTEM]
    if profile_lines:
        blocks.append(PROFILE_HEADER + "\n" + "\n".join(f"- {l}" for l in profile_lines))
    if memory_lines:
        blocks.append(MEMORY_HEADER + "\n" + "\n".join(f"- {l}" for l in memory_lines))
    if missing_fields:
        blocks.append(MISSING_HEADER + "\n" + ", ".join(missing_fields))
    if not profile_lines and not memory_lines:
        blocks.append(
            "You know nothing about this user yet. Answer generally and ask one "
            "question that would let you personalise next time."
        )
    return "\n\n".join(blocks)


def fact_line(fact: dict) -> str:
    """One retrieved fact, rendered for the prompt as compactly as it reads."""
    verb = {
        "HAS_GOAL": "Goal",
        "INTERESTED_IN": "Interested in",
        "PREFERS": "Prefers",
        "FOCUSES_ON": "Important life area",
        "REMEMBERS": "Remembers",
        "HAS_ZODIAC": "Sun sign",
    }.get(fact["rel_type"], fact["rel_type"])
    line = f"{verb}: {fact['label']}"
    attributes = fact.get("attributes") or {}
    if attributes:
        detail = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(attributes.items()))
        line += f" ({detail})"
    return line


# ------------------------------------------------------------------- extraction

EXTRACTION_SYSTEM = """You decide what is worth remembering about a user across
future conversations. You are not summarising the message.

Return ONLY facts that will still be useful weeks from now:
  GOAL       something they are working towards        ("switching jobs next year")
  INTEREST   a lasting topic they care about           ("entrepreneurship")
  PREFERENCE a stable choice                           ("replies in Hindi")
  LIFE_AREA  a part of life that keeps coming up       ("career", "marriage")
  PROFILE    identity facts: name, dob, tob, birth_place, language
  MEMORY     a specific event worth recalling          ("wedding in December")

Do NOT return: questions, opinions about astrology, passing moods, small talk,
anything about the current moment only, or anything you inferred rather than
were told. When nothing qualifies, return {"facts": []} — that is the common case.

`confidence` is how sure you are the user actually stated this: 0.9+ for an
explicit statement, 0.6-0.8 for a clear implication, below 0.6 for a guess.
Set `slot` only when a new value must replace an old one, using a stable name
such as "preference:language" or "profile:birth_place".

LABEL RULES — these matter more than anything else here.
`label` becomes a node shared by every user who mentions the same thing, so it
must be a SHORT, REUSABLE entity name: 2-4 words, Title Case, no dates, no
pronouns, no sentences. Every specific detail goes in `attributes` instead.

  "I'm planning to switch jobs next year"
      label "Career Change"                  attributes {"target_year": "2027"}
  "I'm preparing for a PM interview in November"
      label "Product Management Interview"   attributes {"timeframe": "November"}
  "I want to start my own company one day"
      label "Entrepreneurship"               attributes {"horizon": "someday"}
  "Please reply in Hindi from now on"
      label "Hindi"                          attributes {"kind": "language"}
      slot  "preference:language"

The label is always the VALUE, never the category: "Hindi", not "Language
Preference". Set `slot` whenever the value can only be one thing at a time,
so a later change supersedes it instead of piling up beside it.

A label like "Switching Jobs Next Year" is WRONG — no other user would ever
share that node, which defeats the point of a shared brain.

For PROFILE facts, `attributes` uses real field names and nothing else:
name, dob (YYYY-MM-DD), tob (HH:MM), birth_place, language.

  "My name is Rahul and I was born in Delhi"
      label "Rahul"   attributes {"name": "Rahul", "birth_place": "Delhi"}
"""


def extraction_system(today: str) -> str:
    """Today's date is injected so "next year" can resolve to a real year."""
    return (
        f"{EXTRACTION_SYSTEM}\n"
        f"Today's date is {today}. Resolve relative times to absolute values "
        f"where you reasonably can: \"next year\" becomes a year, "
        f"\"next month\" becomes a month name."
    )

FACT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["GOAL", "INTEREST", "PREFERENCE", "LIFE_AREA", "MEMORY", "PROFILE"],
                    },
                    "label": {"type": "string"},
                    "attributes": {"type": "object", "additionalProperties": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "slot": {"type": ["string", "null"]},
                },
                "required": ["type", "label", "attributes", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}
