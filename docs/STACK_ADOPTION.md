# Stack Adoption Decisions — Personal OS

You proposed ~20 best-in-class OSS projects. This maps each to a **decision**, so
we adopt the high-leverage ones the *right way* instead of running 20 servers.

**Adoption modes:**
- **LIBRARY** — `pip install` into the existing FastAPI app. Cheap, no new server.
- **SERVICE** — run as its own container (real cost + ops). Use sparingly.
- **PATTERN** — copy the UX/data-model ideas into our Next.js app; don't run it.
- **DEFER/AVOID** — overlaps what we have, or not worth the cost/risk yet.

---

## Core shared services → decision

| Shared service | Best OSS (yours) | Decision | Why |
|---|---|---|---|
| **AI orchestration** | LangGraph | **LIBRARY** | CEO→Commander→Agent graph, state, human-approval, durable runs. Backbone. Replaces our hand-rolled `run-all`. |
| **AI Memory + Knowledge Graph** | Mem0 (+ Letta ideas) | **LIBRARY** | "Bruno remembers everyone/everything." Biggest single upgrade. Runs in-process. |
| **Vector store** | Qdrant | **use pgvector instead** | We already run Postgres (Cloud SQL). `pgvector` = embeddings with **zero new servers**. Qdrant only if we outgrow it. |
| **Universal CRM** | Twenty CRM, Plane | **PATTERN** | Build one `contact` + `pipeline` in our DB; copy Twenty's timeline/relationship UX. Don't fork a second app or your data splits. |
| **Workflow builder (visual)** | Flowise | **PATTERN (later)** | LangGraph gives the engine now; a visual editor is a nice-to-have, not Phase 1. |
| **Integrations** | n8n | **SERVICE (already in repo)** | `docker-compose` already includes n8n. Use it for LinkedIn/Calendar/Drive/Slack glue instead of coding each. |
| **Browser automation** | Browser Use / Open Operator | **SERVICE (worker, gated)** | Powerful for *your own* portals (insurance, CRM, bookings). ⚠️ Do **not** point it at LinkedIn/Indeed — automated applies violate ToS and get accounts banned. Headless Chrome won't run well in Cloud Run; needs a small dedicated worker VM. |
| **Marketing automation** | Mautic | **PATTERN** | We already have sequences, lead scoring, dedupe, send caps. Borrow Mautic's campaign-builder UX; don't run a PHP stack. |
| **Social scheduling** | Mixpost | **PATTERN** | Build a scheduler over our existing content agents + connections; copy Mixpost's calendar UX. |
| **Search** | Meilisearch | **DEFER** | Postgres full-text covers "search recruiters/companies/notes" now. Add Meilisearch only when volume demands. |
| **Assistant UI** | Open WebUI | **PATTERN** | Add a chat panel to our dashboard (talks to our agents); don't run a second app with its own memory. |
| **Email infra** | Postal | **DEFER** | Gmail send (app-password/OAuth) works for your volume. Postal only for true mass-send. |
| **Auth / DB / storage** | Supabase | **AVOID (keep ours)** | We're on Cloud SQL + JWT already. Migrating = work, no benefit now. Borrow nothing urgent. |
| **Dashboard widgets** | Appsmith | **PATTERN** | Copy chart/table/widget ideas into our Next.js Command Centers. |
| **Self-coding agents** | OpenHands / OpenDevin | **DEFER** | Cool, but not core to your outcomes. Later. |
| **Agent crew patterns** | CrewAI | **PATTERN** | Use its role ideas (researcher/closer/manager) inside LangGraph nodes. |

---

## What this means in practice

**Run (services):** the current app (FastAPI+Next on Cloud Run) + Postgres + **n8n** (already), and — only if you want true browser auto-apply on your own portals — one small **Browser-Use worker**. That's it.

**Integrate (libraries, into the one app):** **LangGraph** (orchestration) and **Mem0 + pgvector** (memory/knowledge graph). These are the two transformative adds and neither needs a new server.

**Borrow (patterns):** Twenty/Plane (CRM + pipelines), Mautic (campaigns), Mixpost (scheduling), Appsmith (widgets), Open WebUI (chat panel) — implemented natively so all your data stays in one place.

---

## Recommended build order (compressed, not 90 days)

1. **Memory/Knowledge Graph = Mem0 + pgvector** — agents and the Daily Brief read/write a single "Bruno memory" (people, prefs, companies, goals, history). *Highest leverage, no new infra.*
2. **LangGraph orchestration** — refactor agents into CEO → Commander → Agent with shared state + human-approval gates (your exact hierarchy).
3. **Universal CRM + Pipelines** (Twenty/Plane patterns) — one contact list + per-objective pipelines.
4. **Approve/Execute from the Daily Brief** — top-3 actions become one-click (LangGraph human-in-the-loop).
5. **Browser-Use worker** (own portals only) + **n8n** glue for the rest.
6. Scheduling/campaign/chat UX polish (Mixpost/Mautic/Open WebUI patterns).

Steps 1–4 are all inside the current app. Step 5 is the only new server.

---

## Cost & risk notes (so there are no surprises)

- **pgvector + Mem0**: ~free (uses your Postgres) + OpenAI embedding calls (cents).
- **LangGraph**: free library; same OpenAI usage as today.
- **n8n**: already in compose; a small Cloud Run/VM (~few $/mo) if hosted.
- **Browser-Use worker**: a small always-on VM (headless Chrome) — modest cost; **ToS-gated to your own accounts/portals**, never LinkedIn/Indeed auto-apply.
- Everything else = $0 (patterns, not servers).
