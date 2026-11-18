import base64
from dataclasses import replace
from email import policy
from email.parser import BytesParser
import struct
import unittest
import uuid
import zlib
from unittest.mock import patch
from types import SimpleNamespace
from sqlalchemy.orm import Session
from app.models import User, SenderSignature
from app.routers import sender_signature
from app.routers import dot_review
from app.sender_signatures import Signature, validate_png, compose
from app.integrations.dot_gmail import ReservedMail, fingerprint, verify_sent
from tests import test_dot_review_api as base
from tests import test_dot_gmail as gmail_base


def png(width=1, height=1):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\x10\x20\x30")) + chunk(b"IEND", b""))


class SignatureMimeTests(unittest.TestCase):
    def test_png_checks_dimensions_crc_and_decoded_size(self):
        self.assertEqual(validate_png(png()), (1, 1))
        for bad in (b"<svg></svg>", png()[:-1], png(4001), png(2), png() + b"extra", b"x" * 2_000_001):
            with self.assertRaises(ValueError):
                validate_png(bad)
    def test_html_escaped_inline_asset_and_plain_text_fallback(self):
        signature = Signature(png(), "Fixture Sender\nProducer\n+1 555 0100")
        message = compose('<script>alert("x")</script>', signature)
        raw = message.as_bytes()
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertIn(signature.plain_text, parsed.get_body(preferencelist=("plain",)).get_content())
        html = parsed.get_body(preferencelist=("html",)).get_content()
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("cid:signature-", html)
        self.assertNotIn('src="http', html)
        assets = [p for p in parsed.walk() if p.get_content_type() == "image/png"]
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].get_payload(decode=True), png())
        self.assertEqual(assets[0].get_content_disposition(), "inline")
    def test_signature_optional_never_added_globally(self):
        message = compose("No signature requested")
        self.assertFalse(message.is_multipart())
        self.assertNotIn("signature-", message.as_string())


class SignatureProfileTests(unittest.TestCase):
    setUp = base.DotReviewApiTests.setUp
    tearDown = base.DotReviewApiTests.tearDown
    intake = base.DotReviewApiTests.intake

    def setup_profile(self):
        User.__table__.create(self.engine)
        SenderSignature.__table__.create(self.engine)
        self.owner = uuid.uuid4()
        self.other = uuid.uuid4()
        with Session(self.engine) as db:
            for id_ in (self.owner, self.other):
                db.add(User(id=id_, email=str(id_) + "@example.com", hashed_password="fixture"))
            db.commit()
        self.app.include_router(sender_signature.router)
        self.app.dependency_overrides[sender_signature._operator] = lambda: SimpleNamespace(id=self.owner)
        self.app.dependency_overrides[dot_review._operator] = lambda: SimpleNamespace(id=self.owner)

    def upload(self, data=None, text="Fixture Sender\nProducer"):
        return self.client.put("/sender-signature", data={"mailbox": "owner@example.com", "plain_text": text,
            "source_ref": "fixture://approved-signature"}, files={"file": ("signature.png", data or png(), "image/png")})

    def test_signature_is_private_to_authenticated_owner(self):
        self.setup_profile()
        self.assertEqual(self.upload().status_code, 200)
        response = self.client.get("/sender-signature/image")
        self.assertEqual(response.content, png())
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.app.dependency_overrides[sender_signature._operator] = lambda: SimpleNamespace(id=self.other)
        self.assertFalse(self.client.get("/sender-signature").json()["configured"])
        self.assertEqual(self.client.get("/sender-signature/image").status_code, 404)

    def test_draft_preview_embeds_own_signature_and_invalidates_changed_profile(self):
        self.setup_profile()
        self.upload()
        obs = base.observation(fields={"usdot": "123", "email": "contact@example.com"})
        self.intake([obs])
        digest = dot_review.Observation.model_validate(obs).snapshot().digest
        result = self.client.post("/dot-review/123/draft", json={"to": "contact@example.com", "subject": "Questions",
            "body": "Review only", "evidence_digests": [digest], "include_signature": True})
        self.assertEqual(result.status_code, 200, result.text)
        preview = self.client.get("/dot-review/123/draft-preview")
        self.assertEqual(preview.status_code, 200, preview.text)
        parsed = BytesParser(policy=policy.default).parsebytes(preview.content)
        self.assertEqual(parsed["X-Unsent"], "1")
        self.assertEqual(parsed["From"], "owner@example.com")
        self.assertEqual(len([p for p in parsed.walk() if p.get_content_type() == "image/png"]), 1)
        self.app.dependency_overrides[dot_review._operator] = lambda: SimpleNamespace(id=self.other)
        self.assertEqual(self.client.get("/dot-review/123/draft-preview").status_code, 409)
        self.app.dependency_overrides[dot_review._operator] = lambda: SimpleNamespace(id=self.owner)
        self.upload(text="Changed signature")
        self.assertEqual(self.client.get("/dot-review/123/draft-preview").status_code, 409)

    def test_invalid_image_never_saved(self):
        self.setup_profile()
        self.assertEqual(self.upload(b"<svg onload=alert(1) />").status_code, 422)
        self.assertFalse(self.client.get("/sender-signature").json()["configured"])


class SignatureTransportTests(unittest.TestCase):
    setUp = gmail_base.DotGmailTests.setUp
    tearDown = gmail_base.DotGmailTests.tearDown
    def test_provider_reconciliation_checks_signature_bytes(self):
        signature = Signature(png(), "Fixture Sender")
        mail = replace(self.mail, signature=signature)
        mail = replace(mail, approved_fingerprint=fingerprint(mail.sender, mail.to, mail.bcc,
                       mail.subject, mail.body, signature.digest))
        self.service.users().messages().get().execute.return_value = {"labelIds": ["SENT"], **mail.raw(mail.bcc)}
        self.assertEqual(verify_sent(mail, "fixture")["state"], "sent_verified")
        self.service.users().messages().send.assert_not_called()

if __name__ == "__main__":
    unittest.main()
