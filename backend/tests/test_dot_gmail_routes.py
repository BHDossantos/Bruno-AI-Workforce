import unittest
from unittest.mock import patch
from app.integrations import dot_gmail
from tests import test_dot_review_api as base

class GmailReadRoutesTests(unittest.TestCase):
    setUp = base.DotReviewApiTests.setUp
    tearDown = base.DotReviewApiTests.tearDown
    intake = base.DotReviewApiTests.intake

    def test_verified_history_persists_and_blocks_new_draft(self):
        self.intake()
        with patch("app.runtime_config.apply_to_settings"), patch.object(dot_gmail, "prior_sent", return_value={
            "message_ids": ["fixture-existing-sent"], "truncated": False, "scope": "verified_personal_gmail_sent"}):
            response = self.client.post("/dot-review/123/gmail-history", json={"expected_address": "owner@example.com"})
        self.assertEqual(response.status_code, 200, response.text)
        detail = self.client.get("/dot-review/123").json()
        self.assertTrue(detail["prior_contact_review"])
        self.assertFalse(self.client.get("/dot-review/123/readiness").json()["sending_enabled"])

    def test_failed_history_never_claims_verified_or_leaks_provider_error(self):
        self.intake()
        with patch("app.runtime_config.apply_to_settings"), patch.object(dot_gmail, "prior_sent", side_effect=RuntimeError("private provider detail")):
            response = self.client.post("/dot-review/123/gmail-history", json={"expected_address": "owner@example.com"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private provider detail", response.text)
        self.assertNotIn("gmail_history", self.client.get("/dot-review/123").json())

    def test_research_recheck_is_not_a_contact_attempt_or_call_hold(self):
        self.intake()
        response = self.client.post("/dot-review/123/events", json={"event_id": "research-1", "kind": "next_action",
            "occurred_at": "2026-11-06T16:00:00Z", "due_at": "2026-11-07T16:00:00Z",
            "evidence_ref": "fixture://safer", "note": "Recheck missing SAFER record"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.get("/dot-review/123").json()["prior_contact_review"])

    def test_conflicting_contact_evidence_blocks_history_lookup(self):
        self.intake([base.observation(), base.observation(source_record_id="r2", fields={"usdot": "123", "email": "other@example.com"})])
        with patch.object(dot_gmail, "prior_sent") as lookup:
            response = self.client.post("/dot-review/123/gmail-history", json={"expected_address": "owner@example.com"})
            self.assertEqual(response.status_code, 409)
            lookup.assert_not_called()

if __name__ == "__main__":
    unittest.main()
