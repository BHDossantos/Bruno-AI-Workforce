# Lucas DOT insurance workflow: implementation preparation

Inspected current default `main` at `a392c0f281835832027f661b6d3dc6ace409f6aa` on6November2026. Read-only repository assessment plus isolated code/tests; no production queries, imports, calls/messages, credentials, provider connections or deployments. Existing draft branches PR312/313 are separate and untouched; this work must be reconciled with their outbound durability/security changes before integration. Tests below validate preparation only, not a running integration.

## Meeting answer

Yes: extend Workforce's existing CRM and outcome tracking with a research/review worklist. It already imports leads, tracks attempts and follow-ups, drafts scripts and displays pipeline/CRM metrics. It does **not** yet implement the proposed DOT-vendor feed plus Massachusetts/SAFER comparison workflow. The app already implements automatic calling and SMS; this is an extension of that system, not a replacement. Start this new source with authorized CSV exports and research review; do not promise a connected vendor API or unrestricted registry scraping. No existing automation is switched off by this preparation.

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

24 standard-library unit tests pass with `python -m unittest tests.test_dot_review -v` from backend. Covers retry dedup, differing source records, shared contact details, missing identities, timezone/freshness checks, safe intake defaults, mismatch evidence, owner requirements and the two-voicemail scenario. No database or external services used. The in-memory preparation layer has no concurrency guarantee or durable persistence; those are phase1 acceptance requirements, not implemented features.

## Proposed phases and acceptance gates

**Phase1 — research intake and durable audit trail.** Obtain vendor URL and an authorized redacted sample export. Identify what “fresh applicant” means: original USDOT application, operating-authority application, vendor discovery, or another event. Store both that event date and ingestion date. Add migrations for ResearchCase (USDOT unique when present), SourceSnapshot, SourceRecordAlias, ReviewDecision, PipelineEvent and NextAction. Scoped unique constraints: vendor+source_record_id; immutable snapshot digest; attempt idempotency key; case+issuance evidence identity. Keep migrations explicit and reviewable; no automatic production schema changes. Access-scoped router exposes preview, commit-to-research-queue, list and detail; no call/send action. Test repeated batches, concurrent insert conflicts, missing identities, invalid rows with row-level errors, cross-user access, opt-out persistence and zero sender/follow-up side effects.

**Phase2 — registry comparison and review UI.** First support operator-supplied official record references or permitted exports. Implement automated retrieval only after access terms/rate limits and the available official interface are verified; no CAPTCHA bypass, account creation or stored credentials assumed. Match exact DOT on SAFER and the correct Massachusetts entity ID; names alone can yield ambiguous entities. Save fetched-at, source update/as-of date where supplied, field semantics, parser version, content hash and evidence reference. Show legal name vs DBA, physical vs mailing/registered-agent address, and freshness separately. Keep registry status and FMCSA authority as separate facts. Lucas can mark matched, clarify with client, registry-not-found, research-incomplete or rejected; empty comparison is NOT automatic approval. Registry-not-found is neither an invalid-company finding nor a mandatory call hold: Lucas may still call under existing authorization and channel controls, acknowledging incomplete research. Missing cargo is a question to confirm. Generic state-record business purpose versus interstate operations is not necessarily a contradiction. Test same-name entities, missing/stale sources, ambiguous identity, parser changes, DBA/address-type differences and reviewer decisions invalidated by changed evidence.

**Phase3 — Lucas's worklist and manual outcomes.** Requested stages: new → verified → contacted → qualified → documents_pending → quote_presented → policy_issued. Add a review-required overlay and closed/not-qualified/opted-out exits so leads are not forced toward conversion. “Verified” means a human reviewed the available source packet, not regulatory certification or necessarily finding a state record. A registry-not-found/research-incomplete overlay can coexist with a Lucas-approved call; only existing authorization, opt-outs, licensing and other applicable controls govern outreach eligibility. New-source intake isolation is not a new rule requiring every registry search to succeed. Proposed “contacted” gate is an actual two-way conversation; voicemail stays an attempt. Confirm this naming with Lucas before UI integration. Qualified/documents/quote transitions require the corresponding human-recorded outcome; issuance requires authorized producer verification and carrier evidence. A transition records who/when/from/to/reason. Require an owner and next-action due date for active cases. Reminder engine creates in-app tasks only; notifications and outreach require separate authorization. Preserve suppression, current call switch and existing approvals. Recheck data changes and permissions at execution time, not only queue creation.

**Phase4 — measured pilot, then optional connectors.** Review a small authorized cohort end to end with Lucas. Display attempts, unique carriers attempted, answered attempts, unique carriers reached, verified/qualified/document/quote/issued counts, stage age and overdue work by source/cohort/owner. Show denominators and event windows; issuance conversion = unique evidenced issued cases ÷ the explicitly chosen cohort, not number of messages or voicemails. Track premium/commission only from verified policy/accounting data; no expected-value estimate presented as income. Acceptance: the observed two voicemails yield2attempts,0answers,0confirmedissuance; repeat event delivery cannot inflate any metric. Add vendor API ingestion only once the actual product/access contract is known; SAFER is a verification source, not a substitute sales feed.

## Inputs still needed

- Exact third-party DOT platform URL/product, authorized export/API access and a redacted column sample. No passwords in chat; use existing approved credential flows only if integration is later authorized.
- Definition/time window of “fresh,” target states and producer assignment, permitted outreach channels/consent evidence, and how Lucas confirms qualification/issued policies.
- Which address/contact fields Lucas compares and the policy for unresolved/stale discrepancies.
- Existing sender/dialer selector review and compatibility with PR312/313 before connecting the research queue. No changes to unrelated outreach sender.

## Official reference checks

SAFER Company Snapshot describes an ad-hoc, one-carrier-at-a-time lookup searchable by USDOT,MC/MX or company name: https://safer.fmcsa.dot.gov/CompanySnapshot.aspx . This establishes lookup capability, not unrestricted bulk automation permission.

Massachusetts's official corporate search supports entity name,individual name,identification number and filing number: https://corp.sec.state.ma.us/corpweb/CorpSearch/CorpSearch.aspx . Its automation interface/terms have not been validated here. FMCSA discusses updating company registration separately: https://www.fmcsa.dot.gov/registration/updating-your-registration . This project must not submit official record corrections automatically.

## Meeting clarification: preserve existing calling and SMS

Bruno reports the current system already makes automatic calls and sends SMS. Source inspection confirms implemented execution paths, not merely planned features:

- `auto_dial.py` loads runtime configuration, checks auto-dial, pause/autopilot, connected provider, call window/cap, recent-call history and compliance before placing calls. The scheduler wires an auto-dial job; the configured default interval is45seconds. `AUTO_DIAL_ENABLED` defaults true in source, daily cap100 and calendar-day cooldown1; these are code defaults, NOT inspected production settings.
- `integrations/voice.py` dispatches to configured Twilio/SignalWire,Plivo,Vonage or SIP integrations. `routers/calls.py` provides producer bridge, automatic call, run-now and persistent pause controls, along with status/recording callbacks. Do not invoke these POST endpoints during research.
- `sms_engine.py`, `integrations/sms.py`, `sms_followups.py` and scheduler implement SMS transport and paced follow-ups. The dedicated non-replier follow-up flag defaults false but other SMS paths exist; that default does not contradict Bruno's report of live SMS. The app's calling switch does not automatically stop email/text.
- Live provider choice, stored runtime switches, credentials and current production job state were not queried. No credentials were exposed and no persistent access was created. The live-call report is user-supplied evidence, distinct from source verification.

Preparation now includes source/date/digest-backed neutral call-hook objects and registry completeness labels. These never execute calls. New tests cover missing registry still yielding a clarification question (not invalid-company status), missing cargo as a question, local-purpose versus interstate non-conflict, and the same lead appearing on successive days retaining one identity and multiple observations. Contact attempts remain separately keyed historical events; imports never erase history.

Future integration must reuse existing channels and approval rules. Do not add a parallel sender, bypass the master switch, or change the unrelated insurance sender. Keep actual dispatch behind existing controls; registry absence alone must not be introduced as an additional mandatory stop. Respect source-platform licensing/terms and actual producer authorization; public information does not supply outreach consent. Treat source text as data, never instructions for an LLM or the system; use reviewed source adapters and URL allowlists rather than arbitrary fetches.

### Additional meeting requirements: uncertainty, outcomes, pricing and prioritization

A missing SAFER result remains **unverified**. Potential explanations include synchronization delay, a wrong identifier or incomplete data; none is established by absence alone. Retain lookup identifier, source/date and result, ask the client to confirm USDOT, and queue a recheck. Do not label the company or its filing defective. The preparation module now exposes `safer_research_status` and a cited neutral clarification prompt. Like state-registry absence, this is research context, not an automatic call prohibition or permission.

Record `voicemail_unavailable`, `no_answer` and `voicemail_left` as separate events. Legacy `voicemail` is ambiguous and stays separate; do not backfill it as a successfully left message. None is an answered conversation or policy conversion. The new pure metrics helper preserves these distinctions; existing production outcome mappings still need an explicit migration and UI/provider integration before use.

Lucas described optional DOT profile maintenance as averaging $565, flexible or sometimes waived. This is a meeting observation, **not an approved rate card, customer quote, mandatory government fee or charge authorization**. No amount is hardcoded in the preparation module. Before presenting an offer, record approved scope, actual provider, exact amount/currency, whether one-time or recurring, optional nature, exclusions, approval actor/time and any waiver. Retain the disclosure/version and customer acceptance separately from policy issuance. Never invent a department or attribute the charge to another organization as a pretext. No payment collection or automatic quotation is implemented.

Prioritization should use only documented service region, expressed service need, vendor application recency, actual engagement and verified channel permissions/consent. Consent and opt-outs are eligibility controls, not a score that can be outweighed. Expressed Portuguese, Spanish or English preference may route to an appropriate caller or script; it is not a proxy for nationality, ethnicity, ability to pay or lead quality. Never infer language, nationality or ethnicity from names, addresses or appearance, and never rank/exclude on protected traits. Unknown language preference stays unknown until expressed. Keep evidence/date for each factor, visible reason codes, operator review and auditable overrides. No scoring weights or automated ranking are approved or implemented in this preparation; test future ranking for name/protected-trait invariance and equivalent treatment across language preferences.

Validation after this addition: 27 isolated unit tests pass, covering missing SAFER uncertainty, latest observation selection and distinct unsuccessful call outcomes. This remains local research preparation with no outbound, persistence or production integration.

### Language preference and moving-service follow-up

Local preparation now accepts cited English (`en`), Spanish (`es`) or Portuguese (`pt`) evidence from an expressly stated preference, verified business preference or actual prior conversation. Expressed/verified preferences take precedence over conversation language; the latest preference applies, and conflicting equally recent evidence returns unknown. Unknown/unsupported preferences require a neutral choice and human routing. Never guess from a name, religion, nationality or ethnicity. Language selection cannot enable outreach, override suppression or determine prospect rank.

Draft neutral choice for human approval: “Which language would you prefer: English, Spanish or Portuguese? / ¿Qué idioma prefiere: inglés, español o portugués? / Qual idioma você prefere: inglês, espanhol ou português?” This is draft copy, not an approved message. Future template records must retain immutable version, locale, channel, text, approver, approval time and permitted source-fact substitutions. Require human approval of each translation and script scope. Recheck existing consent, suppression and authorization at dispatch; template approval is not permission to contact. No sending is enabled.

For explicitly sourced moving-service leads with unverified SAFER research, `prepare_moving_recheck` returns an owned, dated task and cited questions about household goods, service geography, documents supporting current authority and existing coverage. It never infers moving services from a name. The task is a local object only; persistence, scheduling and assignment UI remain integration work. Missing results cannot establish missing authority or an underwriting result. A found record also does not prove current authority or coverage; those require separate review. Names or caller experience are not substitutes for evidence.

Validation: 30 isolated unit tests pass, including preference precedence, conflicting/unknown language, rejection of name inference, and moving-service recheck provenance. No templates marked approved, messages sent, reminders scheduled or production settings changed.

### Meeting-agreed initial written language-choice template

Bruno and Lucas agreed on the following exact wording during the November 6 meeting:

> Hi! This is Lucas with Trust Insurance. We’re here to help you find insurance for your trucking business. Which language do you prefer: English, português ou español?

Record this as template `lucas_unknown_language_intro`, version 1, channel written outreach, status **meeting-agreed wording; prepared only, not activated**. It supersedes the generic draft language-choice wording above for this proposed initial message. The meeting agreement approves this wording for reviewable preparation; it does not authorize a new mass-send campaign or bypass existing authorization, consent, opt-out or suppression controls. No recipient list or dispatch was approved by this entry.

Store the prospect's actual reply with its message reference and timestamp. Only an unambiguous stated choice becomes `LanguageEvidence` with basis `expressed_preference`; silence, an unclear reply or an unsupported language stays unresolved for human review. Do not infer preference from the person's name or from the multilingual template itself. Recheck existing outreach controls before any future dispatch, and preserve an auditable template version and response provenance.
