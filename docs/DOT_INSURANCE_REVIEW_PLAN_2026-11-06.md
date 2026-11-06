# Lucas DOT insurance workflow: implementation preparation

Inspected current default `main` at `a392c0f281835832027f661b6d3dc6ace409f6aa` on6November2026. Read-only repository assessment plus isolated code/tests; no production queries, imports, calls/messages, credentials, provider connections or deployments. Existing draft branches PR312/313 are separate and untouched; this work must be reconciled with their outbound durability/security changes before integration. Tests below validate preparation only, not a running integration.

## Meeting answer

Yes: extend Workforce's existing CRM and outcome tracking with a research/review worklist. It already imports leads, tracks attempts and follow-ups, drafts scripts and displays pipeline/CRM metrics. It does **not** yet implement the proposed DOT-vendor feed plus Massachusetts/SAFER comparison workflow. Start with authorized CSV exports and human review; do not promise autonomous registry scraping, a connected vendor API or automatic calling.

Two observed voicemails are two attempts, zero confirmed connected conversations and zero confirmed conversions. They have not been entered into production by this task. Do not infer revenue, quote completion or policy issuance from those observations.

## Verified code capability and gap

| Need | Actual code | Required addition |
|---|---|---|
| Import DOT/vendor leads | `routers/imports.py` and `importer.py` support CSV, category/segment tags, email OR phone, and re-import updates | Actual vendor link/export schema, permitted use, stable source record IDs, application dates, USDOT and batch provenance |
| Dedup | `importer.py` matches email, or last10phone digits for phone-only leads | Unique canonical USDOT entity identity; retain vendor aliases; do not merge unrelated carriers sharing dispatcher/agent contact details; transactional concurrency constraints |
| Research | Generic lead generation and stored company/intake information | No FMCSA/MA comparison adapter found in scoped backend/frontend searches; build field-specific snapshots and identity matching |
| Review | `/approvals` previews outbound drafts; autopilot affects whether outreach appears there | Dedicated research queue, evidence links, discrepancy disposition, reviewer/version and human clarification questions; outbound approval is not registry verification |
| Pipeline | `crm_pipeline.py`: New,Contacted,Replied,Qualified,Meeting,Won,Lost,Nurture; `models.LEAD_STATUSES` and `insurance_commander.py` use additional mappings | One insurance-specific explicit state machine with migration/display mapping; avoid a third inconsistent status interpretation |
| Outcomes/reminders | `ConversationOutcome` stores voicemail/answer status, producer, quote flags, next_action and next_follow_up_at; `FollowUp` exists | Assigned accountable user per case, task completion/overdue rules, research-only reminders with no sender side effect |
| Scripts | `Lead.call_script`, importer drafting and `sales_templates.py`; latter contains insurance/DOT disclosure language | Evidence-grounded call brief and questions for Lucas; never invent mismatch, authority, coverage or insurance need |
| Clients | `Client` stores carrier,policy_number,signed_at,premium and lead link | Human-confirmed issuance evidence and deduped conversion event; do not equate drag-to-Won with policy issuance |
| Dashboard | CRM,pipeline,conversations,worklist,approvals,knowledge pages exist | Source/cohort/owner funnel, verification backlog, unresolved mismatches, attempt vs answer metrics, overdue next actions and evidenced issuance |
| Controls | `compliance.evaluate` includes DNC/STOP, regulated-action review, configured licensed states, hours/caps; call master switch exists | Verify actual licensing/appointments and applicable channel permissions. Configured state strings do not prove licensing. Unknown state currently passes licensing check; enforcement can be disabled. No blanket compliance claim |

## Important integration hazards found

1. Existing `process_leads_csv` does not send during upload, but creates `FollowUp` rows and queues new records for paced outreach. Do NOT reuse this importer for an unverified research batch. New research cases must be invisible to all sender/dialer selectors until a separate authorized promotion.
2. CRM `stage_of` can label a Drafted status as Contacted. Do not use that as evidence an actual call occurred.
3. `conversation_engine.daily_progress` counts every ConversationOutcome as a conversation in its answer-rate numerator, including voicemail rows. Its quote counts are event counts, while signed Client rows provide sales counts. Other summaries count `conversation_status='sold'`. Build clearly defined, deduplicated cohort metrics rather than presenting these existing measures as the requested conversion funnel.
4. `Lead.owner_name` is the prospect/company contact, not the staff assignee. Add an explicit assigned user identity; preserve `ConversationOutcome.producer` as event attribution.
5. Public records are evidence sources, not consent or vendor-feed entitlements. A mismatch is a review question, not proof of wrongdoing, a government notice or an underwriting decision.

## Preparation implemented in this branch

`backend/app/dot_review.py` is a pure, research-only module, deliberately NOT wired to routers, tables, cron, models startup or senders:

- Immutable normalized source snapshots with source/reference/record ID, timezone-aware retrieval/application dates and content digests.
- USDOT-keyed batch dedup; missing DOT remains quarantined under vendor record identity; differing observations are retained instead of overwriting source data. Registry snapshots cannot masquerade as the vendor feed.
- Conservative legal-name/DBA/physical-address comparison with evidence pointers, missing-evidence flags and identity conflict flags. Agent/mailing addresses and carrier authority/entity status are not incorrectly compared as equivalent fields.
- Owner/due-date next-action value object; no actual reminder delivery.
- Idempotent attempt metrics and separately human-verified policy evidence; voicemail never counts as an answered attempt or a policy conversion. Empty denominators are unknown/null, not invented rates.

18 standard-library unit tests pass with `python -m unittest tests.test_dot_review -v` from backend. Covers retry dedup, differing source records, shared contact details, missing identities, timezone/freshness checks, safe intake defaults, mismatch evidence, owner requirements and the two-voicemail scenario. No database or external services used. The in-memory preparation layer has no concurrency guarantee or durable persistence; those are phase1 acceptance requirements, not implemented features.

## Proposed phases and acceptance gates

**Phase1 — research intake and durable audit trail.** Obtain vendor URL and an authorized redacted sample export. Identify what “fresh applicant” means: original USDOT application, operating-authority application, vendor discovery, or another event. Store both that event date and ingestion date. Add migrations for ResearchCase (USDOT unique when present), SourceSnapshot, SourceRecordAlias, ReviewDecision, PipelineEvent and NextAction. Scoped unique constraints: vendor+source_record_id; immutable snapshot digest; attempt idempotency key; case+issuance evidence identity. Keep migrations explicit and reviewable; no automatic production schema changes. Access-scoped router exposes preview, commit-to-research-queue, list and detail; no call/send action. Test repeated batches, concurrent insert conflicts, missing identities, invalid rows with row-level errors, cross-user access, opt-out persistence and zero sender/follow-up side effects.

**Phase2 — registry comparison and review UI.** First support operator-supplied official record references or permitted exports. Implement automated retrieval only after access terms/rate limits and the available official interface are verified; no CAPTCHA bypass, account creation or stored credentials assumed. Match exact DOT on SAFER and the correct Massachusetts entity ID; names alone can yield ambiguous entities. Save fetched-at, source update/as-of date where supplied, field semantics, parser version, content hash and evidence reference. Show legal name vs DBA, physical vs mailing/registered-agent address, and freshness separately. Keep registry status and FMCSA authority as separate facts. Lucas can mark matched, clarify with client, unresolved or rejected; empty comparison is NOT automatic approval. Test same-name entities, missing/stale sources, ambiguous identity, parser changes, DBA/address-type differences and reviewer decisions invalidated by changed evidence.

**Phase3 — Lucas's worklist and manual outcomes.** Requested stages: new → verified → contacted → qualified → documents_pending → quote_presented → policy_issued. Add a review-required overlay and closed/not-qualified/opted-out exits so leads are not forced toward conversion. “Verified” means a human reviewed the source packet, not regulatory certification. Proposed “contacted” gate is an actual two-way conversation; voicemail stays an attempt. Confirm this naming with Lucas before UI integration. Qualified/documents/quote transitions require the corresponding human-recorded outcome; issuance requires authorized producer verification and carrier evidence. A transition records who/when/from/to/reason. Require an owner and next-action due date for active cases. Reminder engine creates in-app tasks only; notifications and outreach require separate authorization. Preserve suppression, current call switch and existing approvals. Recheck data changes and permissions at execution time, not only queue creation.

**Phase4 — measured pilot, then optional connectors.** Review a small authorized cohort end to end with Lucas. Display attempts, unique carriers attempted, answered attempts, unique carriers reached, verified/qualified/document/quote/issued counts, stage age and overdue work by source/cohort/owner. Show denominators and event windows; issuance conversion = unique evidenced issued cases ÷ the explicitly chosen cohort, not number of messages or voicemails. Track premium/commission only from verified policy/accounting data; no expected-value estimate presented as income. Acceptance: the observed two voicemails yield2attempts,0answers,0confirmedissuance; repeat event delivery cannot inflate any metric. Add vendor API ingestion only once the actual product/access contract is known; SAFER is a verification source, not a substitute sales feed.

## Inputs still needed

- Exact third-party DOT platform URL/product, authorized export/API access and a redacted column sample. No passwords in chat; use existing approved credential flows only if integration is later authorized.
- Definition/time window of “fresh,” target states and producer assignment, permitted outreach channels/consent evidence, and how Lucas confirms qualification/issued policies.
- Which address/contact fields Lucas compares and the policy for unresolved/stale discrepancies.
- Existing sender/dialer selector review and compatibility with PR312/313 before connecting the research queue. No changes to unrelated outreach sender.

## Official reference checks

SAFER Company Snapshot describes an ad-hoc, one-carrier-at-a-time lookup searchable by USDOT,MC/MX or company name: https://safer.fmcsa.dot.gov/CompanySnapshot.aspx . This establishes lookup capability, not unrestricted bulk automation permission.

Massachusetts's official corporate search supports entity name,individual name,identification number and filing number: https://corp.sec.state.ma.us/corpweb/CorpSearch/CorpSearch.aspx . Its automation interface/terms have not been validated here. FMCSA discusses updating company registration separately: https://www.fmcsa.dot.gov/registration/updating-your-registration . This project must not submit official record corrections automatically.
