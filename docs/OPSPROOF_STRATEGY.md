# OpsProof — Product & Go-To-Market Strategy

**Working name:** OpsProof · **Tagline:** *Every production change — controlled,
explainable, and provable.*

A vendor-neutral **production change-control and incident-evidence layer** for
regulated companies. It sits *above and between* the tools a bank or insurer
already owns — Git, CI/CD, Kubernetes, Terraform, cloud, monitoring, paging,
ITSM — and turns disconnected technical events into one controlled process:
risk-score the change before it ships, tie the incident back to the change that
caused it, prepare a human-approved repair, and emit the evidence a regulator,
risk officer or internal auditor will ask for.

This is a **separate venture** from Bruno AI Workforce. This doc lives here
because it is where the venture strategy lives (see `BNBGLOBAL_GROWTH.md`,
`OUTBOUND_OS_ROADMAP.md`). No app code implements any of it.

### Where this doc sits

`OPSPROOF_EXECUTION_SPEC.md` is the **authoritative** baseline for product,
design, architecture, data, AI, security, testing and commercial packaging. It
supersedes the earlier `OPSPROOF_BUILD_SPEC.md`, which has been removed rather
than left to rot as a weaker duplicate (it remains in git history).

**This doc's unique contribution is the market evidence the spec does not
carry.** The spec's §2.4 draws the competitive boundary by *category* —
observability, ITSM, CI/CD, GRC — and names no vendors. Sections 1, 6, 7 and 9
below name them, state what each already ships, and cite sources. That is the
difference between "we sit above your stack" and knowing that Datadog already
correlates Kubernetes deploys to the failures they cause, that Kosli already
ships an Evidence Vault, and that the nearest priced comparable lists roughly an
order of magnitude below the entry ACV in §7.

Open findings raised against the spec: `OPSPROOF_SPEC_FINDINGS.md`.

---

## 0. The one idea

Not "AI for DevOps" — that market is broad, crowded, and being funded at
unicorn scale. The one idea is narrower and duller and more defensible:

> **A regulated firm cannot currently answer, from one system, whether a
> production change was safe, who approved it, what it broke, how it was
> repaired, and where the proof is.**

Every piece of that answer exists somewhere. None of the pieces are joined, and
nobody owns the join. OpsProof owns the join — and the join is the thing the
regulator actually asks for.

---

## 1. Honest framing — what already exists

Before positioning, the uncomfortable inventory. Most of the capability list in
the original thesis is **already shipped by someone**:

| Capability | Who already ships it |
|---|---|
| Correlate a Kubernetes deploy to the failure it caused | **Datadog Change Tracking + Watchdog** — streams every k8s deploy/update, correlates `CrashLoopBackOff`/`ImagePullBackOff` against recent changes ([blog](https://www.datadoghq.com/blog/watchdog-faulty-kubernetes-deployment/)) |
| Detect a bad release within minutes | **Datadog Automatic Faulty Deployment Detection** ([docs](https://docs.datadoghq.com/watchdog/faulty_deployment_detection/)) |
| Detect that a rollback happened | **Datadog Rollback Detection** ([docs](https://docs.datadoghq.com/continuous_delivery/features/rollbacks_detection/)) |
| Score change risk from tests, scans, deploy history; auto-approve low risk | **ServiceNow DevOps Change Velocity** ([data sheet](https://www.servicenow.com/standard/resource-center/data-sheet/ds-servicenow-devops.html)) |
| Verify a deploy against APM and auto-roll-back | **Harness Continuous Verification** ([product](https://www.harness.io/products/continuous-delivery)) |
| Policy-as-code deployment governance | **Harness OPA policies** |
| Approve a pipeline stage from a change ticket | **Harness ↔ ServiceNow** ([blog](https://www.harness.io/blog/servicenow-ci-cd-pipelines)) |
| Kubernetes change timeline + one-click fixes | **Komodor** ([blog](https://komodor.com/blog/crossing-monitoring-and-observability-gaps-with-change-intelligence/)) |
| Agentic root-cause investigation | **Resolve AI** ($190M raised, $1.5B valuation — [Series A](https://resolve.ai/blog/series-a-funding)), **incident.io AI SRE** ([blog](https://incident.io/blog/introducing-ai-sre)), **Datadog Bits AI SRE** |
| Record every change commit→prod; store compliance evidence | **Kosli** — SDLC governance, ships a feature named *Evidence Vault* ([how it works](https://www.kosli.com/how-it-works/)) |
| Automated control evidence for DORA (Regulation (EU) 2022/2554) / SOC 2 / ISO | **Vanta**, **Drata** ([Vanta DORA](https://www.vanta.com/resources/dora-compliance-checklist)) |

**Three consequences, and they reshape the plan:**

1. **Do not lead with root-cause analysis.** It is the crowded half. Datadog
   already performs the exact demo in the original thesis (memory limit cut →
   OOMKilled → correlated to the deploy), and three well-funded AI-SRE vendors
   are competing on speed of diagnosis. Entering there means competing on a
   feature the buyer's incumbent already bundles.
2. **Do not lead with the risk gate either.** Harness + ServiceNow already
   composes "score it, gate it, verify it, roll it back."
3. **Kosli is the true competitor** — and it already uses "Evidence Vault" as a
   product name. **That name must not ship.** Working replacements: *Control
   Ledger*, *Change Record*, *Proof Ledger*.

### The residual gap — stated narrowly

Every vendor above owns one *stage*. None owns the **chain of custody across all
of them**, and none is vendor-neutral by design:

- Datadog's correlation lives inside Datadog and stops at the incident.
- Harness's verification lives inside Harness's own pipeline.
- ServiceNow's risk score never sees the Kubernetes reality that follows.
- Kosli records what *happened* — it does not gate a change on a pre-deploy risk
  score, and it does not tie a production incident back to a change.
- Vanta/Drata evidence controls at the *policy* level, not per production change.

**OpsProof's claim, and the only one worth defending:** one continuous,
tamper-evident record spanning *risk → approval → deployment → incident →
remediation → verification → evidence*, assembled from whatever tools the
customer already owns.

---

## 2. The repositioned wedge

The original thesis led with prevention and diagnosis. The research says lead
with **change control and evidence**, and treat diagnosis as a consumed input.

| | Original framing | Repositioned |
|---|---|---|
| Lead capability | "Find the cause faster" | "Prove every change was controlled" |
| Competitive field | Resolve AI, Datadog Bits, incident.io, Komodor | Kosli, manual audit prep, spreadsheets |
| Buyer | Head of SRE | Head of Operational Resilience / Technology Risk |
| Budget line | DevOps tooling (crowded, benchmarked) | Operational resilience / regulatory (larger, less price-anchored) |
| Datadog relationship | Competitor | **Input source** |

Consuming Datadog's and Komodor's correlation rather than rebuilding it is also
what "vendor-neutral layer" honestly means. When Datadog has already flagged a
faulty deployment, OpsProof ingests that verdict, ranks it against its own
change graph, and — this is the part nobody does — **writes it into an
append-only record that names the approver, the policy that applied, the tests
that ran, and the remediation that closed it.**

RCA stays in the product. It is not the pitch.

---

## 3. The four surfaces

| Surface | Who lives in it | What it answers |
|---|---|---|
| **Change Control** | Platform/SRE, change manager | "Is this change safe to ship, and what controls does it need?" |
| **Live Incident Room** | SRE on call | "Which recent change most likely caused this, and what is the evidence?" |
| **Remediation Center** | Service owner + approver | "What is the repair, its blast radius, and who signs it off?" |
| **Control Ledger** *(renamed)* | Risk, audit, resilience | "Show me every change to this service, who approved it, and whether controls were bypassed." |

The Control Ledger is the surface that justifies the price. The other three
are how the data gets into it honestly.

**Non-negotiable design rule:** every conclusion shows its evidence. A
confidence number is a documented score with its inputs visible, never an
oracle. See `OPSPROOF_BUILD_SPEC.md` §6.

---

## 4. The regulatory map

DORA (Regulation (EU) 2022/2554) has applied to covered EU financial entities
since **17 January 2025**. The operative detail for this product is not DORA
itself but its RTS: **Commission Delegated Regulation (EU) 2024/1774, Article 17
— ICT change management**, which expands DORA Art. 9(4)(e)
([text](https://www.springlex.eu/en/packages/dora/rts-rmf-regulation/article-17/),
[context](https://legal.pwc.de/en/news/articles/doras-core-commission-delegated-regulations-published-in-eus-official-journal)).

For **all** changes to software, hardware, firmware, systems or security
parameters, Art. 17 requires:

| Art. 17 requirement | OpsProof artifact |
|---|---|
| Verification that ICT security requirements were met | Policy-engine result attached to the change record |
| **Independence of the approving function from the requesting and implementing functions** | Approver identity checked against requester/implementer; separation-of-duties violation recorded as a control exception |
| Clear description of roles and responsibilities | Requester, implementer, approver, service owner captured per change |
| Changes are specified and planned | Change record with scope, affected services, planned window |
| An adequate transition is designed | Rollout method (canary/staged), rollback plan, verification plan |
| Changes are tested and finalised | Test evidence linked; missing tests recorded as a control gap, not silently passed |

DORA Art. 17–23 (ICT-related incident management, classification and reporting)
maps to the Live Incident Room and Control Ledger: incident timeline,
classification inputs, root-cause evidence, remediation and closure.

**Read that separation-of-duties line again.** It is a *technical* control that
almost no engineering stack enforces or evidences today, and it is the single
best cold-open in the sales conversation.

The full standards register — NIST AI RMF and the Generative AI Profile, NIST
SSDF, OWASP LLM guidance, OpenTelemetry, WCAG 2.2 AA, SLSA — is in
`OPSPROOF_EXECUTION_SPEC.md` §13.9 and Appendix J. Verification notes and the
EU AI Act's revised dates are in `OPSPROOF_SPEC_FINDINGS.md` finding 3. The
RTS Art. 17 mapping stays here because it is the one that sells.

> **Discipline rule — applies to all collateral, decks, and the product UI.**
> OpsProof helps a firm **collect, structure and evidence** its ICT change and
> incident controls. It does not make anyone compliant, and no OpsProof material
> ever says or implies that buying the software confers compliance. Compliance
> is a determination for the firm, its auditors and its regulator.

---

## 5. ICP and buying committee

**Target firm:** regional bank, insurer, fintech, payment company, or regulated
technology provider · 500–5,000 employees · 20–200 production services ·
Kubernetes + Terraform · Datadog/Dynatrace/Splunk/Prometheus · PagerDuty and/or
ServiceNow · a real platform/SRE function · a history of change-caused incidents
· live audit or regulatory pressure · no appetite to replace existing tools.

Not tiny startups (no regulatory pain, no budget). Not tier-1 global banks first
(24-month procurement cycles will kill a company with no revenue).

| Role | What they want | Their objection |
|---|---|---|
| **Head of Operational Resilience / Tech Risk** — *economic buyer* | Demonstrable controls and evidence over ICT change | "Our GRC platform already claims this" |
| Head of Platform Eng / Director SRE — *champion* | Fewer change-caused incidents, no new toil | "Is this another dashboard I have to feed?" |
| CTO / CIO | Production stability without slowing delivery | "Does this add a gate that hurts velocity?" |
| CISO | Controlled production access, separation of duties | "What does your collector read, and where does it send it?" |
| Change Manager | Risk assessments that reflect technical reality | "Our CAB already does this on paper" |
| Internal Audit | Evidence without chasing engineers for screenshots | "Will an auditor accept this record?" |
| SRE / DevOps engineers | Faster context during an incident | "I already have Datadog open" |

**The change from the original thesis:** the champion is still the platform
lead, but the economic buyer is the resilience/risk office, not the CTO. The
CTO buys *tools* and benchmarks them against tool prices. The resilience office
buys *controls* and benchmarks them against audit findings and consultant fees.
That distinction is what makes §7's pricing survivable.

**The CISO's question is the real gate.** The collector's security model —
read-only, outbound-only, metadata-not-payload — is a sales artifact before it
is an engineering one. See `OPSPROOF_BUILD_SPEC.md` §3.

---

## 6. Objection handling: "why not just more Datadog?"

The old answer ("Datadog tells you what your system is doing") no longer holds —
Datadog *does* correlate deploys to failures. The honest answer:

> "Datadog will tell you the payments deploy caused the outage, and it will tell
> you fast. What it won't tell your regulator is who approved that deploy, that
> the approver wasn't the person who wrote it, which tests were skipped, which
> policy allowed it through on a Friday, and that the fix was reviewed before it
> went out. That record doesn't exist in one place today — your engineers
> reconstruct it by hand after the fact, from screenshots. We keep Datadog. We
> keep your correlation. We add the part your resilience report is missing."

Corollaries:
- Against **Kosli**: "Kosli records what happened. We also stop what shouldn't
  happen — a risk score and a policy gate *before* the deploy, and the incident
  linked back to the change afterwards."
- Against **Vanta/Drata**: "They evidence your policies. We evidence every
  individual production change."
- Against **ServiceNow**: "Your CAB risk score is based on what the requester
  typed in a form. Ours is based on what the change actually touches."

---

## 7. The offer ladder and pricing

| Stage | Price | What it is |
|---|---|---|
| **Production Change Risk Diagnostic** | €15–25k | 90 days of incidents + changes analyzed; control gaps, missing evidence, recurring failure patterns, automation opportunity. **Deliverable today, with no product.** |
| **8-week pilot** | €30–50k, creditable against year one | One critical app, ≤50 services, 4–5 integrations, read-only, historical incident replay, live change scoring, evidence packets |
| **Year one — one business unit** | €120–180k | The number to prove |
| **Larger regulated deployment** | €250–500k | Multi-BU, multi-environment |
| **Private/single-tenant deployment** | €500k+ | Network-restricted, customer-controlled |
| **Implementation & integrations** | €25–100k one-time | |

**Pricing metric:** critical services × production environments × business units
× integration complexity. **Never alert volume** — it punishes the customer for
observing more, and it anchors the deal against monitoring spend.

### The honest pricing risk

Kosli — the closest comparable — publishes an Enterprise tier around **$3,250**
on annual contracts ([pricing](https://www.kosli.com/pricing/)); Komodor prices
per node. **€120–180k is roughly an order of magnitude above the nearest comp.**

That gap closes only one way: the deal must be underwritten by the operational
resilience / technology risk budget, where the comparison set is *audit
remediation programs and Big-4 consulting engagements*, not developer tools. If
the deal gets routed to the DevOps tooling budget, expect to be benchmarked
against Kosli and to lose the price.

**Therefore the pricing is a hypothesis, not a plan.** The diagnostic and the
pilot exist to test it with real money before a single line of platform code is
written for a customer.

---

## 8. The unfair advantage

The founder's track record is the wedge's credibility: Director-level SRE/Cloud
Ops, SLA raised 98.5% → 99.95%, ~30% cloud cost reduction, SRE leadership at CVS
Health. That is already the spine of the **Reliability/SRE wedge** in
`BNBGLOBAL_GROWTH.md`.

**OpsProof is that wedge productized.** And critically: **B&B Global is the
delivery vehicle for the diagnostic before OpsProof exists as software.** The
€15–25k diagnostic is a consulting engagement the founder can personally deliver
now — it needs a spreadsheet, an interview guide and read access, not a platform.

That has three effects: revenue before product, the ICP's real data as the
product spec, and a named reference customer at the point the platform ships.

---

## 9. Moat

Ranked by how much it actually defends:

1. **Per-customer change→failure history.** After a year, OpsProof knows which
   change shapes are dangerous *in that firm*. A competitor starts at zero.
2. **Embedded approval workflow.** Once a firm's change gates run through
   OpsProof, ripping it out means re-papering a regulated control. This is the
   strongest lock-in and the slowest to build.
3. **Regulatory control mappings.** Art. 17 line-item → artifact, maintained as
   the RTS and supervisory expectations evolve. Boring, unglamorous, valuable.
4. **The operational knowledge graph** — business service down to commit.

**Not a moat, despite the temptation to claim it:** vendor-neutral integrations.
Integrations are a cost of entry that any funded competitor replicates in a
quarter. Say so internally; never build the strategy on it.

---

## 10. Risks and kill criteria

| Risk | Signal to watch | If it fires |
|---|---|---|
| Price floor is fiction | Three diagnostics all route to the DevOps tooling budget | Re-price to €40–70k entry and rebuild the model, or repivot to a services-led business |
| RCA commoditizes to zero | Resolve AI / Datadog Bits bundle change-evidence export | Accelerate onto the ledger + policy surface; abandon any RCA differentiation claim |
| Kosli moves into the seam | Kosli ships pre-deploy risk scoring or incident linkage | Compete on the incident half and the regulatory mapping depth; expect a price fight |
| ServiceNow closes the loop natively | Change Velocity ingests k8s/Terraform reality | Target firms that are *not* ServiceNow-centric; lead with vendor neutrality |
| Collector fails third-party security review | Two design partners stall in InfoSec review | Ship a fully in-tenant / air-gapped deployment mode before selling further |
| Nobody feels the pain enough to pay | Diagnostics sell but none converts to a pilot | **Kill.** The pain is real but not budgeted; do not fund a platform on it |

---

## 11. First 90 days

Deliberately product-free. The goal is paid evidence that the thesis is real.

1. **Weeks 1–2** — write the diagnostic methodology: interview guide, the
   evidence checklist mapped to RTS Art. 17, the change/incident data pull, the
   report template. This *is* the product spec, drafted from the outside in.
2. **Weeks 1–6** — sell three diagnostics from the existing SRE/insurance
   network. US relationships will very likely close faster than a cold Spanish
   bank; the venture can be Barcelona-based and still land its first customer
   anywhere. Run outreach through the founder personally, not a sequence.
3. **Weeks 4–10** — deliver them. Every finding becomes a product requirement.
   Record: which questions the customer couldn't answer, how long the answer
   took, and who had to be interrupted to get it. Those three numbers are the
   business case for every subsequent deal.
4. **Weeks 8–12** — convert one diagnostic into a paid pilot with a written
   success definition (see `OPSPROOF_BUILD_SPEC.md` §13). Only then start
   building.
5. **Ongoing** — publish the founder's POV on change control and Art. 17 (this
   audience reads, and almost nobody is writing to it from an engineering seat).

**Geography:** Barcelona for engineering and product; Madrid for enterprise
sales, banking/insurance relationships and resilience-office access. Neither
constrains where the first customer comes from.

---

## 12. Open items before spending money

- [ ] **Name and domain clearance** for "OpsProof" — trademark search in EU/US
      software classes, domain availability.
- [x] **Rename the evidence surface** — decided: **Control Ledger**. "Evidence
      Vault" is Kosli's shipped feature name. **Still open in the spec**, which
      uses Evidence Vault throughout (§4.2, §7.12, §14.11, Appendix D, P0-19);
      tracked as finding 2 in `OPSPROOF_SPEC_FINDINGS.md`. Fold into the
      trademark clearance item above rather than running it separately.
- [ ] **Resolve the "DORA" collision.** To an engineer, DORA means *DevOps
      Research and Assessment* metrics; to the buyer it means the *regulation*.
      Never use the word unqualified in collateral — write "DORA (Regulation
      (EU) 2022/2554)" or "DORA metrics", never bare "DORA".
- [ ] **Legal review of every compliance claim** before any of it is published.
- [ ] **Confirm the pricing hypothesis** with the first three diagnostics.

---

## Sources

- [RTS (EU) 2024/1774 Art. 17 — ICT change management](https://www.springlex.eu/en/packages/dora/rts-rmf-regulation/article-17/) ·
  [DORA delegated regulations (PwC Legal)](https://legal.pwc.de/en/news/articles/doras-core-commission-delegated-regulations-published-in-eus-official-journal)
- [Kosli — how it works](https://www.kosli.com/how-it-works/) · [Kosli pricing](https://www.kosli.com/pricing/)
- [Datadog — faulty deployment detection](https://docs.datadoghq.com/watchdog/faulty_deployment_detection/) ·
  [Watchdog + faulty k8s deployments](https://www.datadoghq.com/blog/watchdog-faulty-kubernetes-deployment/) ·
  [rollback detection](https://docs.datadoghq.com/continuous_delivery/features/rollbacks_detection/)
- [ServiceNow DevOps Change Velocity](https://www.servicenow.com/standard/resource-center/data-sheet/ds-servicenow-devops.html)
- [Harness Continuous Delivery](https://www.harness.io/products/continuous-delivery) ·
  [Harness ↔ ServiceNow](https://www.harness.io/blog/servicenow-ci-cd-pipelines)
- [Komodor — change intelligence](https://komodor.com/blog/crossing-monitoring-and-observability-gaps-with-change-intelligence/)
- [Resolve AI Series A](https://resolve.ai/blog/series-a-funding) · [incident.io AI SRE](https://incident.io/blog/introducing-ai-sre)
- [Vanta — DORA compliance checklist](https://www.vanta.com/resources/dora-compliance-checklist)
