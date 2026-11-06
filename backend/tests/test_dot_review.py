import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.dot_review import (Attempt, IssuedPolicy, NextAction, ResearchCase, Snapshot,
                            compare_observations, conversion_metrics, is_fresh_applicant,
                            normalize_usdot, prepare_vendor_batch)

NOW = datetime(2026, 11, 6, 15, tzinfo=timezone.utc)


def snapshot(record="row-1", kind="vendor", applicant=None, **fields):
    return Snapshot(kind, "test-vendor" if kind == "vendor" else kind,
                    "fixture://authorized-export", record, NOW, tuple(fields.items()), applicant)


class DotReviewTests(unittest.TestCase):
    def test_normalize_identity(self):
        self.assertEqual(normalize_usdot(" 00123 "), "123")
        for invalid in ("", "0", "-4", "１２３", "123-45", "USDOT123"):
            with self.assertRaises(ValueError):
                normalize_usdot(invalid)

    def test_requires_source_and_aware_time(self):
        s = snapshot(usdot="123")
        for changes in ({"source_ref": ""}, {"source_record_id": ""},
                        {"fetched_at": NOW.replace(tzinfo=None)}, {"source_kind": "other"}):
            with self.assertRaises(ValueError):
                replace(s, **changes)

    def test_snapshot_copies_fields_and_hash_is_order_independent(self):
        fields = [("usdot", "123"), ("legal_name", "Fixture LLC")]
        s = replace(snapshot(), fields=fields)
        fields.clear()
        self.assertEqual(len(s.fields), 2)
        self.assertEqual(s.digest, replace(s, fields=tuple(reversed(s.fields))).digest)

    def test_duplicate_fields_rejected(self):
        with self.assertRaises(ValueError):
            replace(snapshot(), fields=(("usdot", "123"), ("usdot", "456")))

    def test_exact_retry_does_not_duplicate_case_or_snapshot(self):
        s = snapshot(usdot="123")
        cases = prepare_vendor_batch([s, s])
        cases = prepare_vendor_batch([s], cases)
        self.assertEqual(len(cases), 1)
        self.assertEqual(len(cases["usdot:123"].observations), 1)

    def test_preserve_disagreeing_vendor_records_not_last_write_wins(self):
        cases = prepare_vendor_batch([snapshot(usdot="00123", legal_name="One LLC"),
                                      snapshot("row-2", usdot="123", legal_name="Two LLC")])
        self.assertEqual(len(cases), 1)
        self.assertEqual(len(cases["usdot:123"].observations), 2)

    def test_shared_phone_does_not_merge_different_carriers(self):
        cases = prepare_vendor_batch([snapshot(usdot="123", phone="fixture-phone"),
                                      snapshot("row-2", usdot="456", phone="fixture-phone")])
        self.assertEqual(len(cases), 2)

    def test_missing_dot_quarantined_even_without_contact_details(self):
        case = next(iter(prepare_vendor_batch([snapshot(legal_name="Fixture LLC")]).values()))
        self.assertIsNone(case.usdot)
        self.assertTrue(case.review_required)
        self.assertFalse(case.outreach_enabled)

    def test_existing_mapping_unmodified_and_intake_never_enables_outreach(self):
        s = snapshot(usdot="123")
        existing = {"usdot:123": ResearchCase("usdot:123", "123", (s,), False, True)}
        result = prepare_vendor_batch([s], existing)
        self.assertTrue(existing["usdot:123"].outreach_enabled)
        self.assertFalse(result["usdot:123"].outreach_enabled)
        self.assertTrue(result["usdot:123"].review_required)

    def test_safer_not_vendor_feed(self):
        with self.assertRaises(ValueError):
            prepare_vendor_batch([snapshot(kind="safer", usdot="123")])

    def test_import_time_is_not_application_time(self):
        self.assertFalse(is_fresh_applicant(snapshot(usdot="123"), NOW - timedelta(days=7)))
        self.assertTrue(is_fresh_applicant(snapshot(applicant=NOW), NOW - timedelta(days=7)))
        self.assertFalse(is_fresh_applicant(snapshot(applicant=NOW + timedelta(days=1)), NOW))
        self.assertFalse(is_fresh_applicant(snapshot(applicant=NOW - timedelta(days=8)), NOW - timedelta(days=7)))

    def test_conservative_comparison_keeps_source_evidence(self):
        a = snapshot(kind="ma_registry", legal_name="One LLC", physical_address="1 Main St")
        b = snapshot(kind="safer", legal_name="Two LLC")
        flags = compare_observations(a, b)
        self.assertEqual({f.reason for f in flags}, {"client_clarification", "missing_evidence"})
        self.assertTrue(all(f.left_evidence == a.digest and f.right_evidence == b.digest for f in flags))

    def test_comparison_does_not_conflate_unlike_official_fields(self):
        a = snapshot(kind="ma_registry", legal_name="Fixture  LLC", registered_agent="Agent", entity_status="active")
        b = snapshot(kind="safer", legal_name="fixture llc", contact_person="Someone", carrier_authority="inactive")
        self.assertEqual(compare_observations(a, b), ())

    def test_dot_leading_zero_not_false_identity_conflict(self):
        self.assertEqual(compare_observations(snapshot(usdot="00123"), snapshot(kind="safer", usdot="123")), ())
        self.assertEqual(compare_observations(snapshot(usdot="123"), snapshot(kind="safer", usdot="456"))[0].reason,
                         "identity_review")

    def test_next_action_needs_owner_timezone_and_due_date(self):
        with self.assertRaises(ValueError):
            NextAction("", NOW, "Call after review")
        with self.assertRaises(ValueError):
            NextAction("lucas", NOW.replace(tzinfo=None), "Review")
        self.assertTrue(NextAction("lucas", NOW - timedelta(minutes=1), "Review mismatch").overdue(NOW))

    def test_two_voicemails_are_attempts_not_conversations_or_conversions(self):
        attempts = [Attempt(str(i), f"usdot:{i}", NOW, "lucas", "voicemail") for i in (123, 456)]
        result = conversion_metrics(attempts, [])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["voicemails"], 2)
        self.assertEqual(result["answered_attempts"], 0)
        self.assertEqual(result["policy_issued_cases"], 0)
        self.assertEqual(result["attempted_case_conversion_rate"], 0)

    def test_attempt_retry_dedup_and_conflicting_id(self):
        a = Attempt("event", "usdot:123", NOW, "lucas", "voicemail")
        self.assertEqual(conversion_metrics([a, a], [])["attempts"], 1)
        with self.assertRaises(ValueError):
            conversion_metrics([a, replace(a, outcome="answered")], [])

    def test_conversion_requires_human_evidence_and_is_case_based(self):
        with self.assertRaises(ValueError):
            IssuedPolicy("usdot:123", "", "", NOW)
        policy = IssuedPolicy("usdot:123", "fixture://carrier-confirmation", "licensed-reviewer", NOW)
        a = Attempt("event", "usdot:123", NOW, "lucas", "answered")
        result = conversion_metrics([a, replace(a, event_id="followup")], [policy, policy])
        self.assertEqual(result["policy_issued_cases"], 1)
        self.assertEqual(result["attempted_case_conversion_rate"], 1)
        self.assertIsNone(conversion_metrics([], [])["answer_rate"])


if __name__ == "__main__":
    unittest.main()
