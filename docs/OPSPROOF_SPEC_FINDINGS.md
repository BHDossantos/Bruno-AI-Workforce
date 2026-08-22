# OpsProof — open findings against Execution Specification v1.0

Findings raised against `OPSPROOF_EXECUTION_SPEC.md`, which is authoritative. Per
that spec's §16.3, disagreement is recorded rather than edited into the baseline —
this file is where it is recorded until each item is accepted, rejected, or turned
into an ADR.

Four items. Each states the finding, the evidence, and a proposed resolution. Three
are corrections; one is a naming conflict the spec cannot resolve on its own.

---

## 1. The hypothesis engine has no "absence of evidence" rule — a broken connector can exonerate the guilty change

**Severity: high.** This is a correctness defect in the product's core claim.

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

**Proposed resolution.** Add to §8.5:

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

**Proposed resolution.** Rename the surface. `OPSPROOF_STRATEGY.md` uses **Control
Ledger**, which was the name selected when this conflict was first raised. Adopt it
across the spec (§4.2, §7.12, §14.11, Appendix D, P0-19) or choose an alternative,
but resolve it before any customer-facing material is produced. Roll the decision
into the existing trademark clearance workstream rather than treating it separately.

**Note:** the strategy doc and this file currently disagree with the spec on this
name. That is deliberate — it is the open item, not an inconsistency to be silently
patched.

---

## 3. The standards register should carry the AI Act's revised dates

**Severity: low — the spec is not wrong, but it is less useful than it could be.**

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

**Proposed resolution.** Add the dates and the Annex III scope question to §13.9 and
Appendix J, keeping the existing "obtain legal analysis" instruction as the operative
requirement.

**Also verified and safe to cite in Appendix J:** NIST AI RMF (AI 100-1)
Govern/Map/Measure/Manage with the Generative AI Profile **NIST AI 600-1** (July
2024, 12 GAI risk categories) · **NIST SP 800-218** SSDF, read with **SP 800-218A**
for generative AI · **WCAG 2.2** (W3C Recommendation, 5 October 2023; AA = 55
criteria, 31 A + 24 AA), with WCAG 3.0 still a Working Draft not expected to reach
Recommendation before ~2028, so 2.2 AA remains the correct target · **SLSA v1.0**
Build Track under OpenSSF, operationalizing SSDF practices PS.1–PS.3.

**One item could not be verified.** The **OWASP Top 10 for LLM Applications** is
cited generically in §13.9. The edition I was able to confirm is **2025 (v2.0),
published 18 November 2024** (LLM01 Prompt Injection → LLM10 Unbounded Consumption).
A **2026 edition has since been published**, but `genai.owasp.org` is blocked by this
environment's egress proxy and I will not paraphrase a list I have not read. Someone
with access should diff the 2026 edition against §9.4's prompt-injection controls
before the register is used with a customer.

---

## 4. The stack commits a pre-revenue team to three toolchains

**Severity: low — a cost to accept knowingly, not a defect.**

§10.4 specifies React/Next.js/TypeScript, Go services, and Python/FastAPI for AI
services.

The Python island for AI services is well justified — that is where the ecosystem
is, and §9's evaluation framework depends on it. The part worth deciding explicitly
is **Go and TypeScript both on the backend**. That is three language toolchains,
three CI paths, three dependency-audit and vulnerability-management surfaces (against
§13.7's requirements), three sets of coding standards under §16.6, and three hiring
profiles — carried by the founding team in §18.3, before revenue.

**Proposed resolution.** Not a rewrite — an ADR under §16.3 that states the case for
Go *and* TypeScript on the backend explicitly, or consolidates to two languages
before Gate A. Making the call late is far more expensive than making it now: by
Gate A the tenant model, event contracts and connector framework are all written in
whatever was chosen.

---

## Status

| # | Finding | Type | Proposed owner (§18.4) |
|---|---|---|---|
| 1 | Hypothesis engine lacks `not_observed` state | Correctness | Head of Data/AI |
| 2 | Evidence Vault name collides with Kosli | Commercial / legal | Head of Product |
| 3 | Standards register missing AI Act dates and Annex III scope note | Completeness | Head of Security/Trust |
| 4 | Three backend toolchains, no ADR | Engineering economics | Head of Engineering/CTO |

None of these blocks Gate A. Finding 1 must be resolved before Gate D
(evidence-backed incident intelligence) ships, since it is a defect in that gate's
core logic. Finding 2 must be resolved before any customer-facing material.
