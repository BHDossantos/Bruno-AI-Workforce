# Research-only permitted export intake

The `insurance_source_intake` module adds bounded, atomic JSON intake for **existing insurance lead IDs**. It does not discover new prospects, scrape a website, fetch a URL, import a client book, change a live phone/email, or schedule any communication. It is a preparation path for an agency-approved export or a dataset whose collection and reuse rights have independently been established. The exact Mass.gov prospecting feed remains unverified and is **not implemented**.

## API and behavior

Register `insurance_source_intake.router` in the application to expose `POST /insurance-growth/import-research`. Standard authenticated admin/operator roles apply. This is not a new agency/tenant access boundary: an operator must already be authorized to work with every included lead and its data.

The request contains:

- `authorization`: method (`agency_export` or `authorized_dataset_export`), organization, `authorization_ref`, `source_ref`, timezone-aware `checked_at` and `valid_until`, purpose `insurance_research`, and true assertions for `collection_and_reuse_authorized` and `contains_no_restricted_scraped_data`.
- `rows`: up to 200 distinct existing insurance `lead_id` values, each with `expected_revision` and a `review` matching the existing research-review schema. Every row must reference the declared source. Agency exports must use `source_kind=authorized_agency`.
- `dry_run`: defaults to true. Set false only after reviewing a dry run and confirming source/data authorization.

The manifest records an operator's assertion and supporting reference. It does not determine legality or grant permission by itself. The caller must establish those rights separately. Source references to the known restricted Massachusetts corporate registry are rejected, and nothing here circumvents its harvesting restrictions. Other dataset origins are not blanket approved merely because they are public.

Only evidence references are accepted, not uploaded policy documents or policy numbers. Unknown fields and nonempty notes are rejected in this import path. References cannot be inline data or contain credentials, URL query strings or fragments. These checks reduce accidental leakage but are not a complete sensitive-data detector: the operator must not encode secrets, policy identifiers or sensitive data in reference strings, names or roles.

Dry runs perform validation and report suppression and proposed changes without any writes. Imports perform compare-and-set writes to `insurance_prospect_reviews`, plus `ActionLog` entries containing the authorization manifest, payload hash, reviewer and revision. A stale different review causes a conflict, and an exact repeat is a no-op. The batch is atomic. A changed source authorization with otherwise identical review data does not rewrite the review or add a log. An unchanged result means the current review already matches, not that an earlier permission or shipment was verified.

Renewal dates still require customer confirmation or authorized policy evidence. Registration dates cannot stand in for policy renewals. Do-not-contact entries are reported and retained. Research does not imply outreach permission. The response always reports `outreach_enqueued=0`.

`parse_import` is available for local prepared JSON, rejecting files larger than 1 MB and duplicate JSON keys. No CSV inference, field guessing, document download or network fetching is performed.

## Remaining operational prerequisites

- Verify the exact data source, its authorized collection/reuse, and agency access before supplying any real export.
- Obtain a legitimate agency-approved export or documented permitted dataset; no live source has been connected by this change.
- Verify deployment, table access and runtime behavior separately. No production data or credentials are changed by the implementation/tests.
- Follow the existing compliance and licensing gates for any later outreach. This endpoint is research only, not dispatch approval.
