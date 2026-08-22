# OpsProof — MVP Technical Build Spec

Engineering spec for the OpsProof MVP. **This is a standalone product.** None of
it belongs in the Bruno AI Workforce codebase, shares its database, or is
constrained by its invariants — it is a separate repository, a separate deploy,
and a separate security posture. This doc lives here only because this is where
the venture docs live.

Strategy and positioning: `OPSPROOF_STRATEGY.md`. Read it first — several
decisions below (lead with evidence, not RCA; consume Datadog's correlation
rather than compete with it) come from there.

---

## 1. Non-goals

Stating these first because each one is a plausible-sounding request that would
sink the MVP:

- **Not an observability platform.** No metric storage, no log ingestion at
  scale, no tracing. OpsProof reads *verdicts and events*, not telemetry.
- **Not a Datadog replacement.** Datadog's change correlation is an **input**.
- **Not an autonomous production agent.** v1 never mutates production. It opens
  pull requests a human approves.
- **Not cloud-cost optimization. Not security monitoring. Not a help desk.**
- **Not a hundred integrations.** Five, done properly (§11).
- **No ML in the risk engine.** Transparent weighted rules only (§5).

---

## 2. Layered architecture

```
CUSTOMER ENVIRONMENT
  GitHub · CI/CD · Kubernetes · Terraform · AWS/Azure/GCP
  Datadog · PagerDuty · (ServiceNow, v2) · runbooks
        │  read-only, outbound-only
        ▼
  [1] COLLECTOR            in customer tenant; metadata only
        ▼
  [2] NORMALIZATION        heterogeneous events → canonical Change/Event
        ▼
  [3] KNOWLEDGE GRAPH      business service → … → commit → author
        │
   ┌────┴─────────────┐
   ▼                  ▼
  [4] RISK ENGINE    [5] CORRELATION ENGINE
   │                  │
   ▼                  ▼
  [6] POLICY ENGINE  [7] REMEDIATION
   └────┬─────────────┘
        ▼
  [8] CONTROL LEDGER  →  [9] API / UI / export
```

| Layer | Responsibility | Primary failure mode to design against |
|---|---|---|
| 1 Collector | Pull change/incident metadata | Over-collection → fails security review |
| 2 Normalization | One canonical event shape | Silent field loss; unmapped event types dropped |
| 3 Graph | Relationships and blast radius | Stale topology → wrong blast radius, wrong score |
| 4 Risk engine | Explainable pre-deploy score | Unexplainable score → auditor rejects it |
| 5 Correlation | Ranked cause hypotheses | False confidence → engineers stop trusting it |
| 6 Policy | Enforce the firm's own rules | Gate that blocks delivery → champion turns hostile |
| 7 Remediation | Draft the repair | A patch that widens the incident |
| 8 Ledger | Append-only, tamper-evident record | Any mutability → the whole product's value is void |
| 9 API/UI | Surfaces + export | — |

**The ledger is the product.** Layers 1–7 exist to fill it with true records.

---

## 3. The collector and its security model

**This is the deal-blocker, and it is a sales artifact before it is an
engineering one.** A bank's third-party security review will decide the deal
here. Design so every answer is short and boring.

**Deployment.** A small container in the customer's own Kubernetes cluster or
cloud account. Ships as an image + Helm chart, versioned and signed.

**Hard constraints — v1, non-negotiable:**

| Property | Rule |
|---|---|
| Direction | **Outbound only.** No inbound listener, no ingress, no webhook receiver on the customer side. |
| Access | **Read-only** credentials everywhere. A k8s `ClusterRole` with `get`/`list`/`watch` on a documented resource list; a GitHub App with read scopes; read-only API keys for Datadog/PagerDuty. |
| Production mutation | **None.** The collector holds no credential that can deploy, patch, or delete. |
| Payload | **Metadata, not content.** |
| Auditability | Every read the collector performs is logged locally in a customer-readable audit log, with a retention the customer sets. |
| Egress | Single documented endpoint, TLS, mTLS or signed-JWT auth, customer-pinnable. Payload schema published. |
| Kill switch | Customer can stop the collector without OpsProof's involvement. |

**Explicitly never transmitted:** source code, source diffs' file contents,
customer/PII records, secrets or environment-variable values, raw log bodies,
database contents, full Kubernetes manifests containing secrets.

**Transmitted:** deployment timestamps, commit SHAs + message subjects + author
identity, changed file paths and diff *statistics*, Kubernetes object kinds/
names/namespaces and the specific spec fields OpsProof scores (resource limits,
replicas, probes, image refs), Terraform plan *resource-level* summaries
(resource address, action, changed attribute names), Kubernetes event
types/reasons/counts, alert and incident metadata, approval records.

Diff content and manifest bodies stay in the customer tenant. When the UI needs
to show a diff, it links to the customer's own GitHub — OpsProof references, it
does not copy.

**Deployment modes:** (a) SaaS control plane + in-tenant collector — default;
(b) fully single-tenant / network-restricted — required for the €500k+ tier, and
per `OPSPROOF_STRATEGY.md` §10 must exist before selling past two design
partners.

---

## 4. The operational knowledge graph

Entities and edges (the minimum that makes blast radius computable):

```
BusinessProcess ──supports──> BusinessService ──runs_on──> Application
Application ──deploys──> K8sWorkload ──uses_image──> ContainerImage
ContainerImage ──built_from──> Commit ──authored_by──> Person
TerraformResource ──provisions──> CloudResource ──serves──> Application
Application ──depends_on──> Application
Change ──affects──> {K8sWorkload | CloudResource | Application}
Incident ──impacts──> BusinessService
Incident ──caused_by(confidence)──> Change
Change ──approved_by──> Person
```

**Blast radius** = transitive closure of `depends_on` and `serves` from the
entities a change affects, bounded by depth and annotated with the criticality
of each business service reached. It is a graph traversal, not an LLM judgment.

**Service criticality is imported, never inferred.** From the CMDB, the service
catalog, or a CSV the customer maintains. A criticality tier OpsProof guessed is
worthless in an audit and dangerous in a risk score. Missing criticality is
recorded as *unknown* and surfaced as a data gap — never defaulted to low.

**Dependency edges** come from three sources in priority order: declared config
(service mesh, k8s `Service`/`Ingress`, Terraform references) → observed
call graph from the APM vendor → manual override. Every edge records its source
and last-confirmed timestamp; stale edges degrade the confidence of any score
that used them.

---

## 5. The risk engine

**Transparent, weighted, auditable rules. No ML in v1.** ML is a v3 item, gated
on having enough per-customer change→failure history to train on — and even then
it augments the rule score rather than replacing it, because an auditor must be
able to ask "why 87?" and get a real answer.

**Hard requirement:** every score is *reproducible* — re-running the engine over
the stored inputs must yield the identical score and identical reason strings.
Inputs are stored with the score, versioned with the ruleset version.

Factor set (each emits a contribution and a human-readable reason):

| Factor | Signal |
|---|---|
| Business criticality | Highest tier reached in blast radius |
| Blast radius size | Count/depth of downstream services |
| Change type | k8s resource limits, replicas, probes, image, IAM, network, DB schema, secret rotation… |
| Change magnitude | Diff statistics; % change on a numeric limit |
| Historical failure similarity | Prior incidents whose causing change shares type + target |
| Test evidence | Required test classes present/absent for this service |
| Rollback readiness | Previous artifact available; rollback plan present and machine-checkable |
| Deployment method | All-at-once vs canary vs staged |
| Service stability | Recent incident/change-failure rate for the target |
| Timing | Freeze windows, end of day, end of week, quarter close |
| Emergency flag | Declared emergency change |
| **Separation of duties** | Requester ≠ approver ≠ implementer (RTS Art. 17) |
| Data impact | Schema migration, destructive operation, backup verification |
| Security impact | IAM, network policy, authn/authz, secret material |

Scoring: weighted sum → 0–100, weights per-customer configurable and
version-stamped. Output:

```json
{
  "score": 87, "band": "high", "ruleset_version": "2026.3",
  "factors": [
    {"key": "change_type.memory_limit_reduction", "contribution": 22,
     "reason": "Memory limit reduced 1Gi → 512Mi (-50%)"},
    {"key": "history.similar_failure", "contribution": 18,
     "reason": "Incident 3311 (2026-02-14) caused by a memory limit reduction on this workload"},
    {"key": "tests.load_test_missing", "contribution": 12,
     "reason": "No load test recorded since commit a91f2c"}
  ],
  "recommended_controls": ["canary_5pct", "two_approvals", "verified_rollback_plan"]
}
```

**Anti-requirement:** the engine must never be the reason a deploy is blocked
without a stated factor. An unexplained block destroys the champion relationship
faster than a missed incident.

---

## 6. The incident correlation engine

Produces a **ranked set of hypotheses**, each with evidence. It does not declare
a root cause.

Candidate set: every change affecting an entity within the blast radius of the
impacted service, in a configurable lookback window (default 24h, extended for
infrastructure changes).

Scoring inputs, combined into a documented 0–1 confidence:

| Input | Contribution |
|---|---|
| Temporal proximity | Change→symptom delay against the expected delay for that change type |
| Topology reachability | Graph distance from change target to impacted service |
| Change-type prior | Base rate of this change type causing this symptom class |
| Symptom match | Do observed events match this change type's signature (e.g. limit reduction → `OOMKilled`) |
| Historical recurrence | Prior incidents with this change type + target |
| Exclusivity | Absence of other candidate changes in the window |
| **External verdict** | Datadog faulty-deployment / Komodor change-intelligence flags, ingested as a strong signal |

Output per hypothesis: rank, confidence, the evidence rows that produced it, and
the *disconfirming* evidence considered.

**What the confidence number means, stated in the UI and the docs:** a relative
ranking score, calibrated against the customer's own replayed incident history.
It is not a probability of causation. Publishing an honest definition is what
keeps engineers trusting the tool after the first wrong answer.

---

## 7. The LLM boundary — a hard rule

| The model **may** | The model **may not** |
|---|---|
| Explain the evidence in natural language | Determine the root cause |
| Summarize an incident or write the post-incident narrative | Assign or alter a risk score |
| Search and cite internal runbooks | Approve a change or a remediation |
| Suggest diagnostic commands (never auto-run) | Execute anything in production |
| Draft a rollback plan, k8s or Terraform patch | Merge or deploy that patch |
| Draft the evidence-packet narrative | Write into the ledger directly |

**Structured engines decide; the model narrates.** Every ledger record is written
by deterministic code from structured inputs; model-generated prose is stored as
an *annotation* on a record, labelled as generated, never as the record itself.

This is a safety property and a sales asset. A technology risk officer who hears
"the AI decides which change caused the outage" ends the meeting. "The correlation
is a deterministic scoring model; the AI writes the summary" is the answer that
survives model risk review.

---

## 8. The policy engine

The customer's own rules, declarative and version-controlled:

```yaml
policy: tier1-high-risk
when:
  service_criticality: tier_1
  risk_score: ">75"
  environment: production
require:
  - approvals: 2
  - approver_independence: true      # RTS Art. 17
  - rollout: canary
  - rollback_plan: verified
  - post_deploy_monitoring: 30m
on_violation: hold
```

Evaluation: all matching policies evaluate; requirements union; the strictest
`on_violation` wins (`hold` > `warn` > `log`). Emergency changes may bypass with
a declared reason and are automatically queued for retrospective review within a
configured window — **the bypass itself is a first-class ledger record**, because
"controls bypassed" is a query auditors run.

Every evaluation — matched policies, requirements, met/unmet, decision — is
written to the ledger whether the change proceeds or not.

---

## 9. The Control Ledger

*(Naming: "Evidence Vault" is Kosli's product name and must not be used — see
`OPSPROOF_STRATEGY.md` §12.)*

**Append-only and tamper-evident.** No update path, no delete path — not in the
API, not in the schema, not for support. Corrections are new records that
supersede, with the supersession recorded.

Each record: monotonic sequence number, timestamp, actor, record type, payload,
`prev_hash`, `hash = H(prev_hash ‖ canonical(payload))`. Periodic checkpoint
digests are published so a customer can independently verify no history was
rewritten. Retention is customer-set with a documented minimum.

Record types: `change_requested`, `risk_scored`, `policy_evaluated`,
`approval_granted`, `control_bypassed`, `deployment_started`,
`deployment_completed`, `incident_opened`, `hypothesis_ranked`,
`remediation_proposed`, `remediation_approved`, `remediation_applied`,
`verification_completed`, `incident_closed`, `corrective_action_recorded`.

Every record carries the control reference it evidences (e.g.
`rts_2024_1774.art17.approver_independence`), which is what makes the export
useful to an auditor rather than merely complete.

**Queries the ledger must answer directly** (these are the demo):
all changes to a service · changes approved by a person · all emergency changes ·
changes that caused incidents · changes deployed without required tests ·
incidents impacting a critical business service · whether remediation completed ·
where controls were bypassed · repeat incidents sharing a cause.

**Export:** PDF (evidence packet), JSON, CSV. ServiceNow/GRC push is v2.

---

## 10. Remediation

v1 output is **a proposal, never an action**:

- A revert PR, Terraform patch, or Kubernetes manifest patch — opened in the
  customer's own repo, via their own review process.
- Estimated blast radius of the *repair*.
- A verification plan: the specific metrics and thresholds that define recovery.
- A rollback-of-the-remediation — what to do if the fix makes it worse.
- Required approvers, derived from the policy engine.

A qualified human approves; the customer's existing pipeline executes; OpsProof
observes and records verification.

**Out of v1 scope, documented for later:** "approve and execute" for a narrow set
of pre-agreed low-risk repair classes, gated on per-customer track record. Do not
build it before a customer has watched the proposals be right for months.

---

## 11. MVP integration set

| Integration | Purpose | v1 |
|---|---|---|
| Kubernetes | Workload specs, events, rollout state | ✅ |
| GitHub | Commits, PRs, approvals, checks; PR creation for remediation | ✅ |
| Terraform | Plan/apply metadata, resource-level changes | ✅ |
| Datadog | Alerts, deployment/change verdicts, verification metrics | ✅ |
| PagerDuty | Incident lifecycle, responders, timeline | ✅ |
| ServiceNow | Change requests, CMDB criticality, evidence push | v2 |
| Prometheus | Alternative metrics source | v2 |
| GitLab, Argo CD, Jenkins, Dynatrace, Splunk | | v2+ |

**Cut from the original list for v1:** Prometheus — pick one metrics source and
do it well; the ICP has Datadog. ServiceNow — real work, and only worth it when
a design partner blocks on it (at which point CMDB criticality import makes it
worth more than the metrics integration would have been).

---

## 12. Phased build order

One shippable, demo-able increment per phase. Each phase ends with something a
design partner can watch.

| Phase | Ships | Demo |
|---|---|---|
| **1** | Collector + normalization + graph + change timeline | "Here is every production change last week and exactly what each one touched" |
| **2** | Risk engine + policy engine + Change Control surface | "This change scores 87 because of these four factors, and your own policy says it needs a canary and two approvals" |
| **3** | Incident correlation + Live Incident Room | "This incident's top hypothesis is deploy 9f3a2 — here is the evidence, and here is what we ruled out" |
| **4** | Remediation proposals (revert PR, patch, verification plan) | "Here is the repair, its blast radius, and who has to approve it" |
| **5** | Control Ledger + evidence packet export | "Here is every Art. 17 control for this change, and the PDF your auditor asked for" |

Phases 1, 2 and 5 are the sellable spine (the strategy leads with control and
evidence). 3 and 4 make the record complete and win the engineers — but if the
schedule slips, **5 ships before 4**.

---

## 13. Pilot success criteria

The 8-week pilot converts or it doesn't, and that is decided by measurable
checks agreed **in writing before it starts**. Proposed defaults:

| Criterion | Target |
|---|---|
| Historical incident replay | On ≥ 20 replayed change-caused incidents, the true causing change ranks **#1 in ≥ 70%** and top-3 in ≥ 90% |
| Change coverage | ≥ 95% of production changes in scope detected and attributed to affected services |
| Risk-score credibility | Platform lead agrees with the band (low/med/high) on ≥ 80% of sampled changes; every disagreement has a named factor to fix |
| Evidence acceptance | Internal audit accepts an evidence packet for a sampled change **without** contacting an engineer for supplementary material |
| Control gaps found | ≥ 5 real control gaps surfaced that the firm did not already have on its register |
| Toil | Zero new manual data entry required from engineers |
| Security | Collector cleared by the firm's third-party security review |

The **evidence acceptance** row is the one that matters. If an internal auditor
accepts the packet unaided, the resilience budget is reachable and the pricing in
`OPSPROOF_STRATEGY.md` §7 has a chance. If they don't, nothing else in this
table saves the deal.
