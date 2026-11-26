from dataclasses import replace
from datetime import datetime, timezone
from unittest import TestCase

from app.insurance_day10 import Action, CheckIn, plan


def ts(day, hour, minute=0):
    return datetime(2026, 12, day, hour, minute, tzinfo=timezone.utc)


class InsuranceDay10Test(TestCase):
    case = CheckIn("household-cycle", "NH", ts(1, 16), "producer-1",
                   "https://booking.example/review", "sms", True, True, True)

    def decide(self, day, hour, minute=0, **changes):
        return plan(replace(self.case, **changes), ts(day, hour, minute),
                    approved_booking_hosts=frozenset({"booking.example"}))

    def test_day_ten_uses_eastern_staffed_hours(self):
        self.assertEqual(self.decide(11, 13, 59).action, Action.WAIT)
        decision = self.decide(11, 14)
        self.assertEqual((decision.action, decision.channel), (Action.INVITE, "sms"))
        self.assertEqual(decision.key, self.decide(11, 15).key)

    def test_eligible_email_only_when_selected(self):
        self.assertEqual(self.decide(11, 15, preferred="email", sms_allowed=False).channel, "email")

    def test_wrong_state_and_no_consent(self):
        for changes in ({"state": "NY"}, {"sms_allowed": False}, {"preferred": None},
                        {"policy_active": False}, {"opted_out": True}):
            with self.subTest(changes=changes):
                self.assertEqual(self.decide(11, 15, **changes).action, Action.SUPPRESS)

    def test_no_link_or_owner_or_nonapproved_domain(self):
        for changes in ({"owner_id": None}, {"booking_url": None},
                        {"booking_url": "https://booking.example@other.example/review"},
                        {"booking_url": "http://booking.example/review"},
                        {"booking_url": "https://booking.example:444/review"}):
            self.assertEqual(self.decide(11, 15, **changes).action, Action.REVIEW)

    def test_queued_or_unverified_delivery(self):
        self.assertEqual(self.decide(11, 15, dispatch="queued").action, Action.WAIT)
        for status in ("failed", "uncertain", "unknown", "accepted"):
            self.assertEqual(self.decide(11, 15, dispatch=status).action, Action.REVIEW)

    def test_callback_waits_24_hours_and_weekend(self):
        k = {"dispatch": "accepted", "accepted_at": ts(11, 16)}
        self.assertEqual(self.decide(12, 15, **k).action, Action.WAIT)
        self.assertEqual(self.decide(12, 16, **k).action, Action.WAIT)
        self.assertEqual(self.decide(14, 13, 59, **k).action, Action.WAIT)
        d = self.decide(14, 14, **k)
        self.assertEqual(d.action, Action.CALLBACK)
        self.assertEqual(d.key, self.decide(14, 15, **k).key)

    def test_callback_waits_24_elapsed_hours_during_week(self):
        k = {"dispatch": "accepted", "accepted_at": ts(9, 16)}
        self.assertEqual(self.decide(10, 15, 59, **k).action, Action.WAIT)
        self.assertEqual(self.decide(10, 16, **k).action, Action.CALLBACK)

    def test_callback_and_invite_suppression_after_reply_or_booking(self):
        for changes in ({"replied": True}, {"booked": True}, {"callback_created": True}):
            self.assertEqual(self.decide(14, 14, dispatch="accepted", accepted_at=ts(11, 16),
                                         **changes).action, Action.COMPLETE)
        self.assertEqual(self.decide(14, 15, dispatch="accepted", accepted_at=ts(11, 16),
                                     call_allowed=False).action, Action.SUPPRESS)

    def test_weekend_and_closed_day_postpone_new_invite(self):
        d = plan(self.case, ts(11, 15), approved_booking_hosts=frozenset({"booking.example"}),
                 closed_dates=frozenset({"2026-12-11"}))
        self.assertEqual((d.action, d.due_at), (Action.WAIT, ts(14, 14)))

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            plan(self.case, datetime(2026, 12, 14, 14))

    def test_external_failure_supersedes_earlier_acceptance(self):
        self.assertEqual(self.decide(14, 16, dispatch="failed", accepted_at=ts(11, 16)).action,
                         Action.REVIEW)

    def test_missing_or_future_ack_safe(self):
        self.assertEqual(self.decide(11, 15, dispatch="accepted", accepted_at=ts(11, 16)).action,
                         Action.REVIEW)

    def test_cancelled_booking_reopens_once_without_waiting_another_day(self):
        k = dict(dispatch="accepted", accepted_at=ts(11, 16), callback_created=True,
                 cancelled_booking_id="booking-1", booking_cancelled_at=ts(14, 15))
        d = self.decide(14, 15, **k)
        self.assertEqual(d.action, Action.CALLBACK)
        self.assertIn("cancelled without replacement", d.reason)
        self.assertEqual(d.key, self.decide(14, 16, **k).key)
        self.assertEqual(self.decide(14, 16, **k, reopened_for_booking_id="booking-1").action,
                         Action.COMPLETE)

    def test_cancellation_with_replacement_or_reply_is_not_reopened(self):
        k = dict(dispatch="accepted", accepted_at=ts(11, 16),
                 cancelled_booking_id="booking-1", booking_cancelled_at=ts(14, 15))
        for changes in ({"booked": True}, {"replied": True}):
            self.assertEqual(self.decide(14, 16, **k, **changes).action, Action.COMPLETE)
        self.assertEqual(self.decide(14, 16, **k, opted_out=True).action, Action.SUPPRESS)
        self.assertEqual(self.decide(14, 16, **k, call_allowed=False).action, Action.SUPPRESS)

    def test_cancelled_booking_outside_hours_waits_for_human(self):
        k = dict(dispatch="accepted", accepted_at=ts(11, 16),
                 cancelled_booking_id="booking-1", booking_cancelled_at=ts(12, 16))
        self.assertEqual(self.decide(12, 16, **k).due_at, ts(14, 14))
        self.assertEqual(self.decide(14, 14, **k).action, Action.CALLBACK)

    def test_cancellation_without_confirmed_initial_send_goes_to_review(self):
        self.assertEqual(self.decide(14, 15, cancelled_booking_id="booking-1",
                                     booking_cancelled_at=ts(14, 14)).action, Action.REVIEW)
