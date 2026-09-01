# ADR-0001 — Backend service language for the control plane

## Title and status

- **Identifier:** ADR-0001
- **Status:** **accepted** — Option A (keep Go for services and connectors)
- **Owner (per spec §18.4):** Head of Engineering / CTO
- **Required reviewers:** Principal platform architect, Head of Security/Trust
- **Raised by:** finding 4 in `../OPSPROOF_SPEC_FINDINGS.md`

**Decision: Option A — Go stays the language for `services/` and `connectors/`.**
Accepted by the owner. The alternatives and the reasoning are preserved below
unchanged, so a future reader can see what was weighed rather than only what won.

Per §16.3, a significant deviation from the specification requires an accepted
ADR; per §10.4, a stack change must account for operational cost, security,
portability, hiring and migration impact. Those five axes structure the
comparison below.

---

## Context

### Correction to how this was first raised

Finding 4 originally described the stack as committing to "Go *and* TypeScript on
the backend." **That was wrong, and the error is corrected here.** Reading §10.4
precisely:

| Layer | Language | Scope |
|---|---|---|
| Web application | React, Next.js, TypeScript | `apps/web` only |
| Core platform services | Go | the 16 services in `services/` |
| AI/data services | Python (FastAPI or equivalent) | `ai-gateway`, evaluation, data science |

TypeScript appears **once** in the entire specification, and only for the web
application. There is no second backend language. The split is
frontend / backend / AI — conventional, and defensible on its face.

The real question is narrower and worth deciding deliberately rather than by
default: **is Go the right language for the 16 control-plane services, given this
team and this product?** The cost being weighed is three toolchains in one
monorepo, not two backend languages.

### What the services actually do

From §10.5 and §16.1 — 16 services plus 6 connectors:

| Workload class | Services | Characteristics |
|---|---|---|
| **Customer-side collector** | the Kubernetes collector (§7.2) | Runs **inside the customer's cluster**. Read-only, outbound-only. Subject to a bank's third-party security review. |
| **High-throughput fan-in** | ingestion, normalization | Event stream from many connectors; replay-heavy; backpressure (§10.11) |
| **I/O-bound pollers** | 6 connectors | API polling, webhooks, retries, reconciliation — latency-bound, not CPU-bound |
| **Deterministic logic** | risk, policy, changes, verification | CPU-light, correctness-critical, must be reproducible (§8.4, §8.10) |
| **Graph/query** | topology, search, evidence | PostgreSQL-backed; database does the work |
| **AI** | ai-gateway | Already Python by decision |

### Constraints that bear on the choice

- **§16.1 monorepo** with shared `packages/contracts`. Cross-language contract
  sharing needs codegen (OpenAPI 3.1 / protobuf); single-language sharing does not.
- **§13.7 secure SDLC** — each language adds a dependency-audit and
  vulnerability-management surface.
- **§18.3** already scopes "backend engineers for Go/event/data services," so the
  hiring plan currently assumes Go.
- **§10.8** requires a private/air-gapped edition — deployment artifacts matter.
- Pre-revenue founding team, most roles single-threaded.

---

## Decision

**Option A. Go remains the language for `services/` and `connectors/`.** The
specification's §10.4 stands as written; nothing already committed changes.

Scope: the language for `services/` and `connectors/`. Out of scope, and never in
question: `apps/web` stays TypeScript; `ai-gateway` and the evaluation stack stay
Python.

**Why this option.** The deciding argument is the customer-side collector, and it
is a security argument rather than an ergonomic one. That component runs inside
the customer's Kubernetes cluster and must clear a regulated buyer's third-party
security review, which `OPSPROOF_STRATEGY.md` §5 identifies as the real gate on
every deal. A single statically linked binary with no language runtime, a minimal
base image and a small auditable dependency tree is a materially easier review
than a Node or Python runtime plus its transitive module tree. Options B and C
both weaken exactly that artifact, and their genuine benefits — direct contract
type sharing, one dependency-audit surface, a larger hiring pool — do not buy back
a harder security review on the component that gates revenue.

This is also the lowest-cost decision to reverse. It changes nothing already
written, and §18.3's hiring plan already assumes Go.

**Standing obligations that follow from accepting this option** (from
Consequences below, restated here so they are not missed):

1. Codegen from the OpenAPI 3.1 / protobuf contracts into Go must exist from the
   **first** service. Retrofitting it once several services have diverged is the
   expensive path, and it is the mitigation for the one real cost of this choice.
2. §16.6 coding standards must cover all three languages **before Gate A**, not
   after.

---

## Alternatives

### Option A — Keep Go for services and connectors (the specified default)

**The strongest argument is the collector, and it is a security argument rather
than an ergonomic one.** The Kubernetes collector runs inside the customer's
cluster and must survive a regulated buyer's third-party security review — per
`OPSPROOF_STRATEGY.md` §5, that review is the real gate on every deal. Go
produces a single statically linked binary with no language runtime, no package
manager present at runtime, a minimal base image, and a small, auditable
dependency tree. "Here is one binary, here is its SLSA provenance, here is its
complete dependency list" is a materially easier conversation than explaining a
Node or Python runtime plus its transitive module tree inside a bank's cluster.

Also: mature Kubernetes client tooling (the ecosystem the collector lives in),
predictable memory behavior under the fan-in load of ingestion and normalization,
and no divergence from §18.3's existing hiring plan.

**Costs.** Three toolchains. Contract sharing between `packages/contracts` and Go
services requires codegen rather than direct type imports. A smaller hiring pool
than TypeScript in most markets.

### Option B — Consolidate services onto TypeScript

One language across `apps/web`, `services/` and `connectors/`; two toolchains
total instead of three.

**Benefits.** Shared contract types are imported directly rather than generated —
a genuine reduction in a class of drift bug that codegen only mitigates. One
dependency-audit surface for both web and services under §13.7. Largest hiring
pool. Any engineer can move across the whole product.

**Costs, and the decisive one.** It puts a Node runtime inside the customer's
cluster. That weakens exactly the artifact that has to clear a bank's security
review — larger image, a runtime with its own CVE stream, and a transitive
dependency tree that is materially harder to attest and to explain. There are
mitigations (single-file bundling, distroless images, SEA), and they add
machinery rather than removing it. Secondary: less predictable behavior under
sustained fan-in, and a weaker Kubernetes client ecosystem.

### Option C — Consolidate services onto Python

One backend language shared with `ai-gateway` and the evaluation stack.

**Benefits.** The AI and data work is already Python, so the risk engine's future
ML calibration path (§8.10) and the evaluation harness (§9.8) would share a
language with the services. Excellent Kubernetes clients. Large hiring pool.

**Costs.** Same runtime-in-the-customer's-cluster problem as Option B, plus
heavier deployment artifacts and weaker performance characteristics for the
ingestion and normalization fan-in. It also collapses the deliberate isolation
§10.4 asks for between model/data-science dependencies and platform services —
that separation exists to keep a data-science dependency change from touching the
evidence path, which is the opposite of what this option does.

---

## Consequences

**Option A is accepted** — nothing changes in the spec; this ADR records *why*,
which is the point. Standing obligations: codegen from the OpenAPI 3.1 / protobuf
contracts into Go must exist from the first service (retrofitting it after several
services diverge is the expensive path), and §16.6 coding standards must cover all
three languages before Gate A rather than after.

**Had Option B or C been taken** — §10.4, §16.1's tree, §16.6 and §18.3's hiring
plan all change together, and a follow-up ADR is required for the collector
specifically, since the security-review argument above applies to that component
regardless of what the rest of the services are written in. A **split outcome is
legitimate and possibly the best answer**: Go for the collector and the ingestion
path, one other language for the remaining services.

**Cost of deferring.** By Gate A the tenant model, canonical event contracts,
connector framework and authorization model are all implemented in whichever
language was chosen. Changing after that is a rewrite of the foundation every
later gate builds on, not a refactor.

---

## Validation and rollback

**Validation (optional, now that Option A is accepted).** Option A is the
status-quo choice, so it carries no migration risk to validate against. The slice
below is retained as the method to use if the decision is ever revisited — for
example if the collector's security review turns out easier than assumed, which
would remove this decision's deciding argument.

Build one thin vertical slice — the PagerDuty
connector, ingestion, and a single evidence write — in the candidate language.
Measure what actually differs rather than arguing it: container image size and
dependency count for the customer-side artifact, sustained ingest throughput and
memory under replay, contract drift caught at compile time versus at test time,
and time for one engineer to add a second connector.

**Rollback.** Practical only before Gate A. Service-by-service migration stays
possible afterwards because services communicate over typed HTTP/gRPC and Kafka
rather than shared memory — but `packages/contracts`, the authorization client
and the telemetry conventions are shared surfaces that would need parallel
implementations during any transition, which is the real cost of a late reversal.
