"""Decides what is worth remembering.

Stage 1 - rule gate (free): skip the LLM for pure questions, very short
messages and chit-chat. Roughly half of all turns never reach stage 2.

Stage 2 - LLM extraction (structured output): a closed vocabulary of fact types
(GOAL, INTEREST, PREFERENCE, LIFE_AREA, PROFILE, MEMORY) and an explicit
"return an empty list when nothing matters" instruction.

Stage 3 - confidence floor: drop anything below MIN_FACT_CONFIDENCE.
"""
