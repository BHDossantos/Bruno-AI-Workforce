# Bruno Personal OS — v2 Behavioral Blueprint (Developer Brief)

**Goal of v2:** turn the platform from a *passive, project-organized dashboard*
into an *active, outcome-organized Chief of Staff*. The behavioral loop changes
from **"Bruno logs in → reads → decides → executes"** to
**"AI senses → scores → plans → Bruno approves → AI executes → AI reports."**

This document is written against the **existing codebase** so most of v2 is
*re-organizing and layering*, not rebuilding.

---

## 0. The one idea

Stop organizing around **projects** (Jobs, Insurance, Music…). Organize around
**objectives** (Generate income, Build a company, Build influence…). Projects
become *sources* that feed objectives. Every agent output becomes a **scored
opportunity** competing for Bruno's scarcest resource: execution bandwidth.

---

## 1. What already exists (reuse — do not rebuild)

| Capability | Where it lives today |
|---|---|
| Backend, auth, RBAC, scheduler/cron | `backend/app/main.py`, `security.py`, `scheduler.py`, `routers/cron.py` |
| Agents (job, insurance, savorymind, music, instagram, ceo) | `backend/app/agents/*` (all extend `BaseAgent`) |
| Outreach engine (email/SMS, dedupe, **touch tracking**, follow-ups) | `outreach.py`, `followups.py`, `integrations/gmail.py`, `sms_engine.py` |
| **Add-any-app + funnel planner** | `integrations/registry.py`, `funnel.py`, `routers/connections.py` |
| **Brand Profile** (seed of the Knowledge Graph) | `models.BrandProfile`, `brand.py`, `routers/profile.py` |
| **Funnel analytics** (Sourced→…→Won) | `routers/analytics.py` |
| Lead/job scoring, apply queue, daily report | `agents/*`, `routers/jobs.py`, `models.DailyReport` |

**Implication:** v2 adds 4 new concepts — **Objectives, Commanders, a Universal
Contact, and a Scored Action** — plus a Knowledge Graph and a Daily Brief. The
agents stay; they just start *emitting scored opportunities* and *reporting up to
commanders* instead of writing straight to their own tables.

---

## 2. Target architecture (6 layers)

```
Layer 6  Outcome Tracking      objectives + rolled-up metrics (money, influence, fitness…)
Layer 5  Automation Engine     tasks, triggers, workflows, automation levels 0–5
Layer 4  Executive Dashboard   5 Command Centers + Daily Brief (single pane of glass)
Layer 3  Commanders            Wealth / Business / Influence / Life — orchestrate agents
Layer 2  AI Workforce          the existing agents (now emit scored actions)
Layer 1  Knowledge Graph       everything about Bruno (profile, contacts, assets, goals)
```

---

## 3. Data model (new tables)

```text
objective
  id, name, command_center(enum), metric(enum: income|revenue|followers|...),
  target_value, current_value, rank(int), weight(float, 0–1), status, notes

command_center  = wealth | business | influence | personal | life_ops

commander
  key, name, command_center, objective_ids[], agent_keys[], goal_text

contact            -- the Universal CRM (one row per human, any context)
  id, name, company, role,
  category(enum: recruiter|job|investor|insurance|restaurant|partner|friend|fan),
  command_center, relationship_score(0–100), value_estimate, probability,
  last_contact_at, times_contacted, next_action, ai_summary,
  source_entity, source_id    -- back-link to lead/restaurant/etc.

action             -- a scored, prioritized thing for Bruno to do
  id, title, command_center, objective_id, source_agent,
  action_type(apply|email|call|post|follow_up|admin|approve),
  value_estimate(float $), probability(0–1), effort(1–5),
  priority_score(float), urgency_days, status(suggested|approved|done|dismissed),
  automation_level(0–5), payload(jsonb), due_date, created_at

profile_entity     -- the Knowledge Graph (flexible)
  id, kind(resume|business|investment|property|book|skill|goal|achievement),
  name, data(jsonb), updated_at

automation_status
  module(job|insurance|savorymind|music|instagram|...), current_level, goal_level
```

Keep the existing `leads`, `jobs`, `restaurants`, etc. They become **sources**;
a sync step projects them into `contact` + `action`.

---

## 4. The Scoring Engine (the brain)

Single formula every agent/commander uses so priorities are comparable across
domains:

```
priority_score = (value_estimate * probability / effort)
                 * objective_weight        # exec-job objective weighted higher than music
                 * urgency_multiplier       # deadlines/decay push things up
```

- **value_estimate** — expected $ (job salary, commission, ARR, or an influence→$ proxy).
- **probability** — agent's confidence the action converts.
- **effort** — 1–5 (a 1-click apply is cheap; a full consulting proposal is not).
- **objective_weight** — from the objective ranking (Section 9).
- **urgency_multiplier** — `1 + (days_to_deadline ≤ 3 ? 0.5 : 0)` etc.

Every agent's `execute()` should additionally emit `Action` rows with these
fields (it already computes most of them — job score, lead score, etc.).

---

## 5. Commanders (orchestration tier)

A `Commander` is a thin orchestrator over existing agents. Add
`backend/app/commanders/` with one class per command center:

- **WealthCommander** → job_hunter, insurance, (new) consulting, (new) investment
- **BusinessCommander** → savorymind, (new) restaurant-acquisition, (new) investor
- **InfluenceCommander** → instagram, music, (new) linkedin, (new) youtube
- **LifeCommander** → (new) residency, legal, banking, travel, health

Each commander: runs its agents, **rolls their outputs into its objective's
`current_value`**, dedupes/*ranks* their `Action`s, and produces its slice of the
Daily Brief. `run-all` becomes "run all commanders."

---

## 6. Daily Brief — the active Chief of Staff (highest-leverage feature)

New endpoint `GET /brief/today` returns:

```json
{
  "greeting": "Good morning, Bruno",
  "focus_score": 87,
  "estimated_value_today": 3800,
  "top_actions": [ {Action, with value/probability/why} x3 ],   // ONLY top 3
  "summary": ["3 high-priority job apps", "2 insurance follow-ups", "1 overdue residency task"],
  "hidden_count": 27
}
```

Rule: **show the top 3 by `priority_score`; hide the rest behind a click.** This
is what forces prioritization. Frontend: replace the home page with this.

---

## 7. Executive Dashboard = 5 Command Centers

Replace project nav with outcome nav. Each command-center page rolls up:
its **objectives** (target vs current), its **top metrics**, and its
**commander's action queue**.

| Center | Sources | Headline metrics |
|---|---|---|
| **Wealth** | job, consulting, insurance, investments | Current income, Expected income, Pipeline $, Monthly cash flow |
| **Business** | SavoryMind, restaurant acq., partnerships, investors | Users, Revenue/ARR, Investors, Partnerships |
| **Influence** | Instagram, Music, LinkedIn, YouTube | Followers, Engagement, Streams, Reach |
| **Personal** | fitness, weight, BJJ, running, sleep | Body fat, Weight, Sessions, Recovery |
| **Life Ops** | Italy residency, taxes, banking, legal, travel | Open tasks, Deadlines, Appointments |

Plus a single top-level **Scoreboard**: Net Worth · Monthly Income · Pipeline $ ·
Followers · Users · Fitness Score. Everything rolls up into these six.

---

## 8. Universal CRM

One `contact` table; a sync job projects every lead/restaurant/influencer/IG
target/recruiter into it with a `category` and `command_center`. Relationship
score = f(recency, # touches, replies, value). One searchable list; each row has
AI summary, last contact, next action, opportunity value. Existing per-project
lists become filtered views over this.

---

## 9. Objective ranking (forces ROI focus)

Seed objectives with explicit rank + weight (COO ranking):

| Rank | Objective | Center | Weight |
|---|---|---|---|
| 1 | Land $250–350k executive role | Wealth | 1.0 |
| 2 | Insurance business (fast cash flow) | Wealth | 0.8 |
| 3 | Consulting business | Wealth | 0.6 |
| 4 | Grow SavoryMind | Business | 0.5 |
| 5 | Music career | Influence | 0.25 |

`objective_weight` flows into the scoring formula, so the music agent can never
out-rank the executive-job agent for today's attention.

---

## 10. Automation maturity (the roadmap)

Track `automation_status.current_level`/`goal_level` per module (0 manual →
5 fully autonomous). Today's honest baseline → target:

| Module | Current | Goal |
|---|---|---|
| Job search | 3 (drafts + 1-click apply) | 5 |
| Insurance | 4 (auto-send w/ approval) | 5 |
| SavoryMind | 4 | 5 |
| Music/IG content | 3 | 5 |
| Life ops | 0 | 3 |

Surface this as a progress view so the roadmap is visible.

---

## 11. Weekly Board Report

Extend `ceo_dashboard` → every Sunday generate a CEO report: income progress,
job pipeline, insurance pipeline, SavoryMind growth, social growth, fitness,
open risks, next-week top priorities. Email + store as `DailyReport(kind=board)`.

---

## 12. Predictive engine (Phase 3)

`POST /strategy/ask {"question": "fastest path to $1M/year"}` → AI ranks paths by
probability using the Knowledge Graph + pipeline data, then re-weights objectives
and the Daily Brief accordingly.

---

## 13. Add-any-app (already built — extend)

The Connections platform already lets Bruno connect any app and auto-builds its
funnel (Attract→Capture→Nurture→Convert→Retain). v2 change: when an app is
connected, **assign it to a Command Center and a Commander**, and let its funnel
emit scored `Action`s like every other source. So "add a new app + run its
sales/marketing funnel" is native, not bolted on.

---

## 14. 90-day phased plan

**Phase 1 — make it think in outcomes (highest leverage)**
1. `objective` + `command_center` + `action` tables; Objective seed/ranking.
2. Scoring engine (`scoring.py`).
3. Agents emit `Action`s.
4. `GET /brief/today` (Top 3) + new home page.
5. Universal `contact` + sync; CRM page.

**Phase 2 — commanders + measurement**
6. `commanders/` tier; `run-all` → commanders; metric roll-ups.
7. 5 Command-Center pages + 6-metric Scoreboard.
8. Revenue Engine (income goal vs projection vs gap) on Wealth.
9. Knowledge Graph (`profile_entity`) + agents reference it.

**Phase 3 — autonomy + foresight**
10. Automation levels enforced per action; Level-5 auto-execute lanes.
11. Predictive "fastest path" engine.
12. Weekly Board Report; agent/connector marketplace.

---

## 15. API surface (new)

```
GET  /brief/today
GET  /objectives            POST /objectives            PUT /objectives/{id}
GET  /command-centers/{key} -> objectives + metrics + action queue
GET  /actions?center=&status=   POST /actions/{id}/approve   /dismiss   /execute
GET  /contacts (universal CRM)  GET /contacts/{id}
GET  /scoreboard            -> the 6 roll-up metrics
GET  /knowledge             PUT /knowledge/{kind}
GET  /automation            PUT /automation/{module}
GET  /reports/board/latest
POST /strategy/ask
```

---

## 16. Guardrails to keep (non-negotiable)

- Cold email auto-send with caps + unsubscribe + dedupe + touch tracking (built).
- SMS only to warm/opted-in (TCPA) (built).
- No bot automation where a platform's ToS forbids it (LinkedIn/IG/Indeed) —
  use the 1-click assisted queue (built).
- Secrets encrypted at rest (built).

---

### TL;DR for the developer
Keep the agents and engines. Add a thin **outcome layer** on top: Objectives →
Commanders → a shared Scoring engine → a Daily-Brief "Top 3" → a Universal
Contact → a Knowledge Graph, and reorganize the UI into 5 Command Centers with a
6-metric Scoreboard. Build Phase 1 first; it delivers ~80% of the "chief of
staff" feel.
