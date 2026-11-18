import base64
from dataclasses import replace
from email import policy
from email.parser import BytesParser
import unittest
from unittest.mock import MagicMock, patch
from app.integrations import dot_gmail as transport


class DotGmailTests(unittest.TestCase):
    def setUp(self):
        self.mail = transport.ReservedMail("reservation-123456789", "owner@example.com", "lead@example.com",
            ("reviewer@example.com",), "Insurance questions", "Which language do you prefer?", "")
        self.mail = replace(self.mail, approved_fingerprint=transport.fingerprint(
            self.mail.sender, self.mail.to, self.mail.bcc, self.mail.subject, self.mail.body))
        self.service = MagicMock()
        self.service.users().getProfile().execute.return_value = {"emailAddress": "owner@example.com"}
        self.service.users().messages().send().execute.return_value = {"id": "gmail-fixture"}
        self.patches = [patch.object(transport.gmail, "address_for", return_value="owner@example.com"),
                        patch.object(transport.gmail, "_service", return_value=self.service)]
        for p in self.patches:
            p.start()
        self.service.reset_mock()
    def tearDown(self):
        for p in self.patches:
            p.stop()
    def test_disabled_does_not_even_contact_provider(self):
        result = transport.send_reserved_once(self.mail, verified_bcc=self.mail.bcc)
        self.assertEqual(result.state, "not_attempted")
        self.service.users.assert_not_called()
    def test_uses_verified_personal_mailbox_no_retries_and_exact_bcc(self):
        result = transport.send_reserved_once(self.mail, verified_bcc=self.mail.bcc, dispatch_authorized=True)
        self.assertEqual(result.state, "accepted")
        raw = self.service.users().messages().send.call_args.kwargs["body"]["raw"]
        self.service.users().messages().send().execute.assert_called_once_with(num_retries=0)
        self.assertEqual(result.provider_id, "gmail-fixture")
        parsed = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))
        self.assertEqual(parsed["Bcc"], "reviewer@example.com")
        self.assertEqual(parsed.get_content_type(), "text/plain")
    def test_wrong_oauth_mailbox_never_sends(self):
        self.service.users().getProfile().execute.return_value = {"emailAddress": "other@example.com"}
        result = transport.send_reserved_once(self.mail, verified_bcc=self.mail.bcc, dispatch_authorized=True)
        self.assertEqual(result.reason, "oauth_mailbox_mismatch")
        self.service.users().messages().send.assert_not_called()
    def test_bcc_and_edited_draft_rejected_before_provider(self):
        result = transport.send_reserved_once(self.mail, verified_bcc=(), dispatch_authorized=True)
        self.assertEqual(result.reason, "bcc_not_verified")
        result = transport.send_reserved_once(replace(self.mail, body="Changed"), verified_bcc=self.mail.bcc, dispatch_authorized=True)
        self.assertEqual(result.reason, "draft_changed_after_review")
        self.service.users.assert_not_called()
    def test_header_injection_rejected(self):
        with self.assertRaises(transport.VerificationError):
            replace(self.mail, subject="hello\nBcc: someone@example.com").raw(self.mail.bcc)
    def test_timeout_has_no_fallback_or_retry(self):
        self.service.users().messages().send().execute.side_effect = TimeoutError("do not expose provider text")
        with patch.object(transport.gmail, "send_message") as fallback:
            result = transport.send_reserved_once(self.mail, verified_bcc=self.mail.bcc, dispatch_authorized=True)
            self.assertEqual(result.state, "unknown")
            self.assertEqual(result.reason, "provider_result_uncertain")
            fallback.assert_not_called()
        self.service.users().messages().send().execute.assert_called_once_with(num_retries=0)
    def test_missing_provider_id_not_success(self):
        self.service.users().messages().send().execute.return_value = {}
        self.assertEqual(transport.send_reserved_once(self.mail, verified_bcc=self.mail.bcc,
                         dispatch_authorized=True).state, "unknown")
    def test_readonly_reconciliation_does_not_equate_sent_to_delivered(self):
        self.service.users().messages().get().execute.return_value = {"labelIds": ["SENT"], **self.mail.raw(self.mail.bcc)}
        result = transport.verify_sent(self.mail, "gmail-fixture")
        self.assertEqual(result["state"], "sent_verified")
        self.assertFalse(result["delivery_confirmed"])
        self.service.users().messages().send.assert_not_called()
    def test_reconciliation_rejects_draft_label_and_changed_recipients(self):
        self.service.users().messages().get().execute.return_value = {"labelIds": ["DRAFT"], **self.mail.raw(self.mail.bcc)}
        with self.assertRaisesRegex(transport.VerificationError, "message_not_in_sent"):
            transport.verify_sent(self.mail, "gmail-fixture")
        changed = replace(self.mail, to="other@example.com")
        changed = replace(changed, approved_fingerprint=transport.fingerprint(changed.sender, changed.to,
            changed.bcc, changed.subject, changed.body))
        self.service.users().messages().get().execute.return_value = {"labelIds": ["SENT"], **changed.raw(changed.bcc)}
        with self.assertRaisesRegex(transport.VerificationError, "sent_content_mismatch"):
            transport.verify_sent(self.mail, "gmail-fixture")

if __name__ == "__main__":
    unittest.main()
