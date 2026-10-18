# MyNaksh — Personalized Astrology Chat with a Shared Brain

A conversational service that remembers the right things about a user in a
graph, and sends only the relevant memories to the LLM.

The brief says the same two things twice, so they are what this build
optimises for:

> "The system should **not store every message** as long-term memory."
>
> "The system should **avoid sending the entire user graph and entire
> conversation history** to the LLM."

Both are enforced in code, not in prose: a three-stage write gate decides what
is kept, and hard caps (5 facts, 6 turns) decide what is sent. Every response
reports what it actually used, so the claim is checkable.

---

## 1. Quick start

**Run it with a real LLM** (Gemini — any provider works, see §6):

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your GOOGLE_API_KEY
uvicorn app.main:app --reload
```

Then open **http://localhost:8000/docs** for the interactive API.

**Run the tests** — no network, no Docker, no API key, under a second:

```bash
pytest -q
# 10 passed
```

The tests use a scripted `FakeLLM` and the in-process graph, so a reviewer can
verify the whole system without credentials.

> **On the Gemini free tier** the limit is 20 requests/day *per model*. If you
> exhaust it, the app does not break — it returns 200 with `degraded: true`
> and a fallback reply (that is scenario 9, and it is worth seeing once). To
> keep chatting, point `LLM_CHAT_MODEL` at another model, which carries its
> own quota, or set `LLM_PROVIDER=fake` to exercise the full flow offline.

---

## 2. Architecture

```
POST /chat
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│ ChatService                     app/chat/service.py      │
│ 106 lines, reads top-to-bottom in the brief's own order  │
└───┬──────────────────────────────────────────────────────┘
    │
    │ 1. select context ──────► ContextSelector  app/chat/context.py
    │                             ├── profile      (always)
    │                             ├── short-term   (last 6 turns)
    │                             └── long-term    (≤5 facts, by intent)
    │                                      │
    │                                      ▼
    │                                 BrainStore ◄── InMemory │ Neo4j
    │
    │ 2. build prompt ────────► app/llm/prompts.py
    │
    │ 3. generate ────────────► LLMClient ◄── Gemini │ Anthropic │ Fake
    │                             (retry once, then a safe fallback)
    │
    │ 4. RESPOND  ◄── the user is served here
    │
    └─ 5. update memory ─────► MemoryWriter  (BackgroundTasks)
                                 └── MemoryExtractor
                                       ├── stage 1  rule gate   (free)
                                       ├── stage 2  LLM extract (structured)
                                       └── stage 3  confidence floor
```

Three boundaries are interfaces, each with a fake used by the tests:
`LLMClient`, `BrainStore`, `SessionStore`. That is why the suite runs offline
and why swapping a provider is one new file.

Step 5 runs **after** step 4 deliberately: extraction is a second model call,
and the user should not wait for it.

---

## 3. Shared Brain schema

### Entities

| Node | Key | Example |
|---|---|---|
| `:User` | `user_id` | `{user_id, name, dob, tob, birth_place, language}` |
| `:Goal` | `key` | `{key: "career-change", name: "Career Change"}` |
| `:Interest` | `key` | `{key: "entrepreneurship"}` |
| `:Preference` | `key` | `{key: "hindi"}` |
| `:LifeArea` | `key` | `{key: "marriage"}` |
| `:ZodiacSign` | `key` | `{key: "leo"}` |
| `:Memory` | `key` | `{key: "wedding-in-december"}` |

`key` is a slug, so `"Career Change"`, `"career change"` and `"CAREER
CHANGE!!"` all `MERGE` onto one node. Dedup lives in the key.

### Relationships

`HAS_GOAL`, `INTERESTED_IN`, `PREFERS`, `FOCUSES_ON`, `HAS_ZODIAC`,
`REMEMBERS` — matching the brief's own example:

```
User (Rahul)
├── HAS_GOAL      → Career Change   (target_year: 2027)
├── INTERESTED_IN → Entrepreneurship
├── PREFERS       → Hindi
└── HAS_ZODIAC    → Leo
```

### The decision worth defending: per-user truth lives on the relationship

```
 (:User {user_id:"user-123"})
        │
        │  HAS_GOAL { confidence: 0.9, status: "active",
        │             attributes: {target_year: "2027"},
        │             source_session: "session-456", mentions: 1,
        │             created_at, updated_at, valid_to: null }
        ▼
 (:Goal {key:"career-change"})   ◄── SHARED by every user who wants this
```

The `Career Change` node belongs to everybody. Put `confidence: 0.9` on the
node and you have claimed *every* user is 90% confident. Rahul can be 0.9 and
Priya 0.6 about the same node only if those numbers sit on their own edges.

This is also what makes the brain *shared* rather than a per-user notes file,
and it is what enables cohort traversal later ("what else do career-changers
ask about?"). The extraction prompt enforces the invariant that makes it work:
labels must be short reusable entity names, with specifics pushed into
`attributes`. `"Switching Jobs Next Year"` would be a bug — no second user
would ever share that node.

### How information is retrieved

```python
brain.query_facts(user_id, rel_types=["HAS_GOAL", "FOCUSES_ON"], limit=5)
```

- **active only** — superseded edges are never sent to the LLM;
- **ordered by `confidence DESC, updated_at DESC`** — if we can afford five
  facts, they should be the ones we are surest of and that were reinforced
  most recently;
- **hard `limit`**, default 5.

`HAS_ZODIAC` is excluded from broad retrieval: the sun sign already rides on
the profile line, and spending one of five slots to repeat it is the waste the
brief warns about.

### Why this storage, and the honest trade-off

**Neo4j is the preferred option in the brief and the schema is written for it**
(`app/brain/schema.cypher`, `docker-compose.yml`). What ships running by
default is `InMemoryBrainStore`: a real graph — shared entity nodes, per-user
edges, supersession, the same `BrainStore` interface — held in process.

The brief permits this ("another graph database or lightweight graph
implementation **if you can justify the choice**"), so here is the
justification: it makes the whole system reviewable in one command with no
Docker and no credentials, and because both sit behind one interface the
behaviour is identical. **The cost is real and I will not hide it: there is no
persistence across restarts and no multi-process sharing.** `app/brain/neo4j_store.py`
is the remaining work, and the in-memory store's semantics are the spec for it.

For the data volume in this assignment a Postgres table with a JSONB column
would honestly be simpler. The graph earns its place only on the cohort
queries above.

---

## 4. Memory strategy

### Short-term vs long-term

| | Short-term | Long-term |
|---|---|---|
| Holds | last 6 turns of *this* session | facts worth keeping |
| Lives in | `deque(maxlen=12)` in process | the Shared Brain graph |
| Scoped to | `session_id` | `user_id` |
| Written | every turn | rarely |
| Production swap | Redis | Neo4j |

"Why do you say that?" is answered from short-term. "What do you remember
about my career goals?" three weeks later is answered from long-term.

### What is stored — three filters, cheapest first

**Stage 1 — rule gate (free, no model call).** Rejects roughly half of turns:

| Verdict | Message |
|---|---|
| `chit_chat` | "hi", "thanks!" |
| `too_short` | "ok cool" (under 4 words) |
| `question_only` | "What should I focus on for my career?" |
| `statement` ✅ | "I'm planning to switch jobs next year." |

The question rule matters most: **most messages in a chat app are questions**,
and each would otherwise cost an extraction call that returns nothing. Mixed
messages are split, and only the declarative half is sent:

```
"I'm thinking about entrepreneurship. What does my chart say?"
   → extracts from: "I'm thinking about entrepreneurship."
```

**Stage 2 — LLM extraction**, structured output against a JSON schema, with a
closed six-type vocabulary (`GOAL`, `INTEREST`, `PREFERENCE`, `LIFE_AREA`,
`PROFILE`, `MEMORY`). Anything outside it is dropped by validation. The prompt
says to return `{"facts": []}` when nothing qualifies and that this is the
common case — otherwise models invent something to look useful. Today's date
is injected so "next year" resolves to a real year.

**Stage 3 — confidence floor** at 0.6. `confidence` means "how sure am I the
user actually said this", not "how important is it".

```
"I might do something, maybe someday who knows"
   → gate: statement   → extracted at 0.3   → dropped   → nothing written
```

Two filters, two different jobs: the gate catches questions, the floor catches
non-commitments.

### What is NOT stored

Questions, chit-chat, passing moods, anything true only right now, anything
the model inferred rather than was told, and anything below the floor.

### How memories are represented and updated

A fact is `(type, label, attributes, confidence, slot)`. `label` becomes the
shared node; `attributes` carries the specifics; `slot` marks values that can
only be one thing at a time.

| Case | Example | Result |
|---|---|---|
| Repeat | "Still planning to switch jobs" | `updated` — confidence 0.90 → 0.95, `mentions` 1 → 2 |
| Enrich | "...into product" | `updated` — attributes merge |
| Contradict | "Actually, English" | `superseded` |

**Corrections supersede, they never delete.** Real output from a live Gemini
run:

```
PREFERS  hindi    slot=preference:language  superseded  superseded_by=english
PREFERS  english  slot=preference:language  active
```

The old belief keeps a `valid_to` timestamp and a pointer to its replacement.
That is auditable ("why did it answer in Hindi in March?" — because that was
true in March), reversible when extraction gets it wrong, and honest: the old
fact was not wrong, it was true *then*.

Writes run in `BackgroundTasks` after the reply, and the writer never raises —
losing a memory is survivable, losing the user's answer is not.

---

## 5. Context-selection approach

Three channels per message:

1. **Profile** — always. It is three lines and relevant to almost anything.
2. **Short-term** — last 6 turns, capped by the deque.
3. **Long-term** — up to 5 facts, *only if the query needs them*.

### Follow-ups skip the graph entirely

"Why do you say that?" is answered from the recent turns alone, and the graph
is never queried (`retrieval_strategy: short_term_only`).

Detecting that is subtler than word count — my first version classified
*"Should I wear blue on Tuesday?"* as a follow-up. A follow-up must open like
one, be a ≤3-word nudge, or point backwards with a bare `that`/`it` — **and**
match no topic keyword. So:

| Message | Intent | Graph queried? |
|---|---|---|
| "Why do you say that?" | `follow_up` | no |
| "Why is my career going badly?" | `career` | **yes** — "career" wins over the "why" opener |
| "Should I wear blue on Tuesday?" | `broad` | yes |

### Intent → relationships

Rules first because they are free; a miss falls back to a broad query.

| Intent | Triggers | Traverses |
|---|---|---|
| `recall` | remember, recall, told you | all 5 |
| `career` | career, job, interview, startup | `HAS_GOAL`, `FOCUSES_ON`, `INTERESTED_IN` |
| `relationships` | marriage, partner, love | `FOCUSES_ON`, `HAS_GOAL`, `REMEMBERS` |
| `preference` | language, hindi, english | `PREFERS` |
| `life_area` | health, money, study, travel | `FOCUSES_ON`, `HAS_GOAL`, `REMEMBERS` |
| `broad` | *(no match)* | all 5 |

A career question does not pull back your language preference.

### What the model actually receives

The complete system prompt for turn 2 of the brief's conversation — four
context lines, not a graph dump:

```
You are MyNaksh, a warm and practical astrology guide.
[...instructions...]

## What you know about this user
- Name: Rahul
- Born: 15 August 1995 at 09:30 in Delhi
- Sun sign: Leo (fire) — confident, wants visible work and recognition

## Relevant things they told you before
- Goal: Career Change (target year 2027)
```

### `context_used` is computed, never hardcoded

It is the evidence that selection happened:

| `retrieval_strategy` | Meaning |
|---|---|
| `short_term_only` | follow-up, graph deliberately skipped |
| `graph:career` | queried career relationships, found facts |
| `graph:career:empty` | queried, nothing stored yet |
| `graph:*:unavailable` | graph is down, answered without it |

`empty` and `unavailable` are kept distinct — "we know nothing about you" and
"the database is unreachable" are very different bugs.

### The brief's conversation, end to end

Real run against Gemini:

| Turn | `retrieval_strategy` | `context_used` |
|---|---|---|
| "…switch jobs next year" | `graph:career:empty` | `user_profile` |
| "What should I focus on for my career?" | `graph:career` | `user_profile`, `short_term_context`, `goal:career-change` |
| "Why do you say that?" | `short_term_only` | `user_profile`, `short_term_context` |
| *(new session)* "What do you remember…?" | `graph:recall` | `user_profile`, `goal:career-change` |

The fourth reply opened: *"You've shared that you are aiming for a significant
career change, with your sights set on 2027."* — recalled across a session
boundary, with the year it had resolved and stored earlier.

---

## 6. LLM layer

```python
class LLMClient(ABC):
    def chat(self, system, messages) -> str: ...
    def extract_json(self, system, user_text, schema) -> dict: ...
```

| Implementation | Status |
|---|---|
| `GeminiLLM` | ✅ default — `gemini-flash-latest` + `gemini-flash-lite-latest` |
| `FakeLLM` | ✅ scripted, offline, used by every test |
| `AnthropicLLM` | stub — one file to add, nothing else changes |

**Model routing:** a cheap model (`flash-lite`) extracts facts, a stronger one
(`flash`) writes the reply. Extraction runs at `temperature: 0`.

Two provider quirks are contained inside the Gemini adapter, which is exactly
what the interface is for:

- Gemini's `responseSchema` has no `additionalProperties`, so it cannot
  express a free-form string map. `attributes` travels as a key/value array
  and is folded back into a dict before it leaves the class. The rest of the
  app never learns this happened.
- The API key is sent as an `x-goog-api-key` header, **not** `?key=` — httpx
  logs request URLs at INFO, so a query-string key would land in application
  logs and any proxy in front of them.

Called over plain REST with `httpx`, already a dependency. The vendor SDK
would add a package for about forty lines of HTTP.

---

## 7. Error handling

**The user always gets an answer. The only 4xx is invalid input.**

| Failure | Behaviour |
|---|---|
| Invalid input | **422**, rejected by Pydantic before the service layer |
| LLM down | retry once, then a deterministic reply from context, `degraded: true` |
| Graph down | profile + short-term only, `retrieval_strategy: *:unavailable` |
| Empty memory | answer normally, claim no memories |
| No context at all | ask one clarifying question rather than invent |
| Extraction fails | reply unaffected; the memory is simply not written |

The LLM fallback never pretends to have answered — it reflects back what we
still hold and asks the user to retry. Sounding useful while being wrong is
worse than saying "not now".

---

## 8. Tests

```bash
pytest -q
# 10 passed in 0.1s
```

| # | Scenario |
|---|---|
| 1 | New user — answers fine, `context_used` is profile only |
| 2 | Creates long-term memory (`career-change`, `target_year`) |
| 3 | Retrieves it on a career question, and it reaches the prompt |
| 4 | Follow-up uses short-term only — graph never queried |
| 5 | New session recalls previous information |
| 6 | Chit-chat stores nothing *and costs no extraction call* |
| 7 | Correction supersedes, old fact retained with `valid_to` |
| 8 | Missing DOB — no crash, no invented zodiac, prompt asks for it |
| 9 | LLM failure → 200, fallback reply, `degraded: true` |
| 10 | Graph failure → answers from profile + short-term |

The tests drive the **real** `ChatService`, `ContextSelector` and
`MemoryWriter`, faking only the two outside edges.

**They were mutation-tested** — the code was deliberately broken to confirm
the suite notices. All five caught:

| Mutation | Result |
|---|---|
| Gate lets everything through | test 6 fails |
| Supersession disabled | test 7 fails |
| Follow-ups query the graph anyway | test 4 fails |
| LLM fallback broken | test 9 fails |
| `missing_fields` always empty | test 8 fails |

### How I would evaluate whether the Shared Brain is helping

| Metric | Method |
|---|---|
| Memory accuracy | hand-label 100 writes: precision (was it worth keeping?) and recall (what did we miss?) |
| Context relevance | precision@5 — of the 5 facts retrieved, how many mattered to that question? |
| Personalization | brain-on vs brain-off A/B on a fixed question set, pairwise LLM judge |
| Consistency | ask the same question in two sessions; do the answers agree? |
| Irrelevant context | rate of retrieved facts a human marks unrelated |
| Memory persistence | replay a multi-session script; assert recall after each boundary |

The leading indicator in production is the **user-correction rate**: if people
increasingly correct stored facts, extraction is drifting.

---

## 9. Design decisions and trade-offs

| Decision | Why | Cost |
|---|---|---|
| Properties on the relationship, not the node | the node is shared across users | slightly more verbose Cypher |
| Supersede instead of delete | auditable, reversible, honest about time | graph grows; needs pruning eventually |
| Rules before LLM for the gate and intent | free, deterministic, covers the common cases | keyword lists need maintenance |
| In-memory graph by default | reviewable in one command, no Docker | **no persistence across restarts** |
| Memory write after the response | extraction is a second model call | a crash between the two loses one memory |
| Hard caps (5 facts / 6 turns) | cost, latency, and answer quality | a rare question may want a 6th fact |
| REST instead of the vendor SDK | one less dependency | manual schema translation |

**Deliberately out of scope**, not forgotten: real ephemeris calculations,
vector DB / embeddings, LangChain or LangGraph, auth, rate limiting,
streaming, CI, an app Dockerfile.

---

## 10. Production considerations

- **Sessions → Redis.** `InMemorySessionStore` dies with the process and does
  not survive more than one worker. The `SessionStore` interface is the seam.
- **Extraction → a queue.** `BackgroundTasks` is in-process; a crash between
  reply and write loses the memory. Move it to a worker with retries.
- **Prompt caching** on the system preamble and profile block — they barely
  change between turns.
- **Multi-tenancy:** every query is already scoped by `user_id`; add it as a
  mandatory index and enforce it at the store, not the caller.
- **PII and consent.** Birth date, time and place are sensitive. Encrypt at
  rest, keep `DELETE /users/{id}/memory` as the honoured right-to-be-forgotten
  path, and add consent capture before any cohort traversal across users.
- **Cost:** ~1 chat call per turn plus ~0.5 extraction calls (the gate removes
  the rest). Track tokens per conversation; the caps bound the worst case.
- **Observability:** `retrieval_strategy`, `context_used` and `WriteReport`
  are already the three things worth logging per turn.

---

## 11. Roadmap

1. Finish `Neo4jBrainStore` — the in-memory store's semantics are the spec.
2. The LLM intent classifier for context selection when the keyword rules
   miss; today a miss falls back to a broad 5-fact query.
3. Memory decay — confidence that ages, so a goal from two years ago stops
   outranking one from last week.
4. Conversation summarisation when a session exceeds the 6-turn window.
5. The evaluation harness in §8, wired to a golden set, running in CI.

---

## 12. Sample requests and responses

[`samples/requests.http`](samples/requests.http) — nine request/response pairs
captured from a live Gemini run, covering the full conversation from the
brief, the Shared Brain dump and the 422 case.
