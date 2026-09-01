# OpsProof — open findings against Execution Specification v1.0

Findings raised against `OPSPROOF_EXECUTION_SPEC.md`, which is authoritative. Per
that spec's §16.3, disagreement is recorded rather than edited into the baseline —
this file is where it is recorded until each item is accepted, rejected, or turned
into an ADR.

Four items. Each states the finding, the evidence, and a proposed resolution. Three
are corrections; one is a naming conflict the spec cannot resolve on its own.

---

## 1. The hypothesis engine has no "absence of evidence" rule — a broken connector can exonerate the guilty change

**Severity: high. RESOLVED — Amendment A1** in `OPSPROOF_EXECUTION_SPEC.md`
(sections 7.10, 8.5, P0-16). The finding is kept below as the rationale for that
amendment. This was a correctness defect in the product's core claim.

§8.5 (incident hypothesis evidence score) and §7.10 (Hypothesis Workspace) define
supporting and contradicting evidence, but nothing in the spec distinguishes:

- **not observed** — we have no data on this, because a connector is down, a source
  is stale, or a signal was never collected; and
- **observed not to have occurred** — we have complete data for this window, and
  the thing did not happen.

Searching the specification for this distinction returns nothing.

**Why it matters.** Under the current logic, a Datadog connector that stops
delivering during an incident produces *absence* of correlating signal for the
change that caused the outage. If absence is scored as contradicting evidence, the
true cause is ranked **down** precisely when the evidence chain is weakest — and the
resulting hypothesis is presented with the same visual confidence as one built on
complete data. §8.3's data-confidence score correctly handles this at the
*assessment* level; the hypothesis engine has no equivalent.

**Where it bit, concretely.** Two components in §8.5's scoring table carried the
defect. *Corroborating telemetry* (15 points) scored **zero** when telemetry was
merely unavailable — indistinguishable from telemetry that was available and
showed nothing. And the *contradictory evidence penalty* (up to −25) had no
precondition on source health, so silence from a degraded source could be read as
argument against the hypothesis. Together they could cost a correct hypothesis up
to 40 points for the sole reason that a connector was down.

**Resolution as shipped (Amendment A1).** Added to §8.5:

- Evidence for a hypothesis resolves to one of four states: `supporting`,
  `contradicting`, `not_observed`, `not_applicable`.
- `not_observed` never contributes negative weight. It reduces the hypothesis's
  evidence completeness and is rendered as a gap.
- A hypothesis whose ranking depends on `not_observed` evidence must be labelled as
  such in the Hypothesis Workspace, naming the unavailable source.
- Contradicting evidence is only admissible where the underlying source was
  confirmed healthy and current for the relevant window.

This aligns the hypothesis engine with the principle the spec already applies to
risk in §8.3–§8.4, and with non-negotiable decision 8 (missing evidence must remain
visible).

---

## 2. "Evidence Vault" is a competitor's shipped product name

**Severity: medium — commercial and legal, not technical.**

The spec uses **Evidence Vault** as a first-class product surface throughout: Gate F
(§4.2), §7.12, §14.11, Appendix D, and epic P0-19.

**Kosli ships a feature called Evidence Vault.** Kosli is SDLC governance for
regulated software delivery — recording every change from commit to production and
storing compliance evidence — which places it in the same evaluation as OpsProof for
the same buyer, against the same use case.
Source: [kosli.com/how-it-works](https://www.kosli.com/how-it-works/).

**Why it matters.** In a bake-off, using a competitor's feature name for your own
feature makes differentiation harder to articulate and concedes the frame. It is
also a weak position if the name is ever asserted, and the spec's own front matter
already flags that "OpsProof" itself requires trademark clearance.

**Proposed resolution — still open.** Rename the surface. `OPSPROOF_STRATEGY.md` uses **Control
Ledger**, which was the name selected when this conflict was first raised. Adopt it
across the spec (§4.2, §7.12, §14.11, Appendix D, P0-19) or choose an alternative,
but resolve it before any customer-facing material is produced. Roll the decision
into the existing trademark clearance workstream rather than treating it separately.

**Note:** the strategy doc and this file currently disagree with the spec on this
name. That is deliberate — it is the open item, not an inconsistency to be silently
patched.

### Clearance evidence gathered (not a clearance opinion)

Collected to inform the decision. **None of this is legal advice, and none of it
substitutes for a proper trademark search by counsel** — which the spec's own
front matter already requires before external launch.

| Check | Result |
|---|---|
| General web/trademark search for an existing "OpsProof" product or mark | **Nothing surfaced.** Adjacent marks exist in the same naming space (OpsLevel, Opsani, OpsStream, OPSWAT, Opsware) but no "OpsProof". Absence from a general search is weak evidence, not clearance. |
| `opsproof.com` | **Registered** — resolves to AWS addresses in ranges commonly used for registrar parking. Could not load the page to confirm (egress-blocked here), so "parked" is inferred, not observed. |
| `opsproof.io` | **Registered** — same pattern. |
| `opsproof.eu` | **Registered** — resolves to a single non-AWS address. |
| `opsproof.ai` | **No A record** — consistent with unregistered or registered-but-unused. |

**What this changes.** The name looks unclaimed as a *product*, which is the
useful signal. But the three most natural domains are already registered, so
acquiring `opsproof.com` is a purchase negotiation rather than a registration —
that is a cost and a timeline to know about before committing the name to
collateral, not a reason to abandon it.

This evidence bears on the *product name*. It does not touch the separate
question in this finding, which is the **surface name** — Evidence Vault versus
Control Ledger. That one is unaffected and still open.

---

## 3. The standards register should carry the AI Act's revised dates

**Severity: low. RESOLVED — Amendment A2** in `OPSPROOF_EXECUTION_SPEC.md`
(§13.9, Appendix J). The spec was not wrong; it was less useful than it could be.
Kept below as the rationale for that amendment.

§13.9's EU AI Act position is well-judged: it requires an AI-use inventory, requires
legal analysis of classification, and commits to human oversight, transparency,
monitoring and data governance regardless of how the product is classified. It
correctly avoids asserting a status. **Nothing in it needs correcting.**

What it lacks is the dates a buyer's risk function will ask about, which changed
recently enough that most written material is stale:

- The **Digital Omnibus on AI** deferred stand-alone Annex III high-risk obligations
  from 2 August 2026 to **2 December 2027**; AI embedded in Annex I regulated
  products moves to **2 August 2028**. The Council approved it 29 June 2026 and it
  **entered into force 27 July 2026**.
- The AI Act's **transparency obligations took effect 2 August 2026** and are
  enforceable now — these did *not* move.

There is also a substantive point worth stating in the register: OpsProof is
**unlikely to fall within Annex III at all**. That entry covers AI used as a *safety
component* in managing critical digital infrastructure or utility supply; a
change-control system inside a bank's own IT estate is not obviously that, and the
"safety component" threshold turns on endangering health or safety. This should be
recorded as *scope undetermined, pending counsel* — not resolved in either
direction. Claiming high-risk status the product does not have manufactures
obligations it does not need; disclaiming it in writing is a legal opinion.

**Resolution as shipped (Amendment A2).** §13.9 now carries a dated obligations
table and states the Annex III position as *scope undetermined, pending counsel*,
with the existing "obtain legal analysis" instruction preserved as the operative
requirement. Appendix J is now a table with precise identifiers and per-row
verification status.

**Also verified and safe to cite in Appendix J:** NIST AI RMF (AI 100-1)
Govern/Map/Measure/Manage with the Generative AI Profile **NIST AI 600-1** (July
2024, 12 GAI risk categories) · **NIST SP 800-218** SSDF, read with **SP 800-218A**
for generative AI · **WCAG 2.2** (W3C Recommendation, 5 October 2023; AA = 55
criteria, 31 A + 24 AA), with WCAG 3.0 still a Working Draft not expected to reach
Recommendation before ~2028, so 2.2 AA remains the correct target · **SLSA v1.0**
Build Track under OpenSSF, operationalizing SSDF practices PS.1–PS.3.

**The OWASP item is now closed — Amendment A3.** It was left open by A2 because
`genai.owasp.org` is egress-blocked here and I would not paraphrase a list I had
not read. The list was subsequently verified against the project's own repository
(`GenAI-Security-Project/GenAI-LLM-Top10`), which is reachable. The **2026
edition, published 4 August 2026**, is now cited in Appendix J with the full list,
and the diff against §9.4 has been performed rather than deferred — see A3 for its
three consequences.

---

## 4. The backend service language was never justified by an ADR

**Severity: low — a cost to accept knowingly, not a defect. ANALYSIS DELIVERED —
see `adr/ADR-0001-backend-service-language.md` (status: proposed).**

### Correction to how this was originally raised

This finding first described the stack as committing to "**Go *and* TypeScript on
the backend**." **That was wrong.** Checking §10.4 precisely: TypeScript appears
exactly once in the entire specification, for the web application only. Go covers
the 16 services in `services/`; Python covers `ai-gateway` and the
data/evaluation stack. The split is frontend / backend / AI — conventional, and
defensible on its face. There is no second backend language.

The overstatement mattered, because it framed the decision as correcting an
anomaly when the real question is a sound default worth confirming rather than
inheriting.

### The finding, restated correctly

§10.4 itself says the stack is "a default, not a religion" and that changes
require an ADR covering operational cost, security, portability, hiring and
migration impact. No such ADR exists for the backend language. The genuine
question: **is Go right for the 16 services, given this team?** — weighed against
consolidating onto TypeScript (one language across web and services) or Python
(one language with the AI stack). Three toolchains in one monorepo is still a real
cost under §13.7's dependency-audit requirements and §16.6's coding standards,
carried by the founding team in §18.3 before revenue.

**Resolution.** `ADR-0001` sets out all three options against §10.4's five axes
and stops short of choosing — the decision belongs to the Head of
Engineering/CTO under §18.4. Its central finding: the strongest argument for Go is
**the customer-side collector**, and it is a *security* argument rather than an
ergonomic one. That component runs inside the customer's Kubernetes cluster and
must clear a regulated buyer's third-party security review, which
`OPSPROOF_STRATEGY.md` §5 identifies as the real gate on every deal. A single
static binary with no language runtime is a materially easier review than a Node
or Python runtime plus its transitive dependency tree. The ADR also records that a
**split outcome is legitimate** — Go for the collector and ingestion path, another
language elsewhere.

Making the call late is far more expensive than making it now: by Gate A the
tenant model, event contracts, connector framework and authorization model are all
implemented in whatever was chosen.

---

## Status

| # | Finding | Type | Proposed owner (§18.4) |
|---|---|---|---|
| 1 | ~~Hypothesis engine lacks `not_observed` state~~ | Correctness | **Resolved — Amendment A1** |
| 2 | Evidence Vault name collides with Kosli | Commercial / legal | Head of Product |
| 3 | ~~Standards register missing AI Act dates and Annex III scope note~~ | Completeness | **Resolved — Amendment A2** |
| 4 | ~~Three backend toolchains, no ADR~~ Backend service language never justified by ADR | Engineering economics | **Analysis in ADR-0001; decision open** |

None of these blocks Gate A.

**Finding 1 — resolved by Amendment A1.** What remains is implementation: P0-16's
gate now carries a degraded-source replay test that must pass before Gate D ships.

**Finding 3 — resolved by Amendment A2**, with one item deliberately left open
inside it: the OWASP LLM Top 10 2026 edition could not be retrieved and is marked
unverified in Appendix J. Someone with access must diff it against §9.4 before the
register is used with a customer.

**Finding 2** must be resolved before any customer-facing material is produced —
it needs a product-naming decision, not research.

**Finding 4** — `ADR-0001` now sets out the options, the evidence and the
consequences. The decision itself is open and belongs to the Head of
Engineering/CTO under §18.4; it must be taken before Gate A, since by then the
tenant model, event contracts, connector framework and authorization model are all
implemented in whatever was chosen. Note the correction recorded in that finding:
the original "Go and TypeScript both on the backend" framing was inaccurate.
