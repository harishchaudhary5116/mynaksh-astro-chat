"""Anthropic implementation of LLMClient.

Model routing: LLM_EXTRACTION_MODEL (small, cheap) pulls facts out of a
message; LLM_CHAT_MODEL (larger) writes the reply. Extraction uses structured
outputs so the JSON is schema-valid without parsing tricks.
"""
