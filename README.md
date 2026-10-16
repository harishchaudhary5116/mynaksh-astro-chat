# MyNaksh — Personalized Astrology Chat with a Shared Brain

A conversational service that remembers the right things about a user in a graph,
and sends only the relevant memories to the LLM.

> Status: scaffold. Sections marked _TODO_ get filled during the build.

---

## 1. Quick start

Runs two ways. The second needs no Docker, so you can review it in one minute.

**With Neo4j (full setup)**

```bash
docker compose up -d                       # Neo4j on bolt://localhost:7687
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # add your API key
uvicorn app.main:app --reload
```

**Without Docker (in-memory Shared Brain)**

```bash
BRAIN_BACKEND=memory uvicorn app.main:app --reload
```

**Run the tests** (no network, no Docker, under 2 seconds)

```bash
pytest -q
```

**See the whole feature in 20 seconds** — replays the conversation from the brief:

```bash
python samples/demo.py
```

---

## 2. Architecture

_TODO: ASCII diagram — request path through context selection, brain, LLM, memory update._

---

## 3. Shared Brain schema

_TODO: entities, relationships, example Cypher, why properties live on the relationship,
why a graph instead of a vector store._

---

## 4. Memory strategy

_TODO: short-term vs long-term; what IS stored; what is NOT stored; the two-stage
write path; how conflicts resolve via supersession._

---

## 5. Context selection

_TODO: the three channels, the follow-up rule, the token budget, `context_used`._

---

## 6. LLM layer

_TODO: the `LLMClient` interface, how to swap provider, model routing
(small model extracts facts, larger model answers)._

---

## 7. Error handling

_TODO: failure -> fallback table._

---

## 8. Design decisions and trade-offs

_TODO: what was deliberately left out and why._

---

## 9. Evaluation — is the Shared Brain actually helping?

_TODO: golden set, memory precision/recall, context precision@k, brain-on vs
brain-off A/B with a pairwise judge, consistency, online correction rate._

---

## 10. Production considerations

_TODO: Redis sessions, queue-based extraction, prompt caching, multi-tenancy,
PII and consent on birth data, cost per conversation._

---

## 11. What I would do with more time

_TODO._

---

## 12. Sample requests and responses

See [`samples/requests.http`](samples/requests.http). _TODO._
