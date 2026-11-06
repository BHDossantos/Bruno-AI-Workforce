"""Regression checks for the two-controller follow-up incident (no network)."""
import threading
import unittest
from unittest.mock import MagicMock, patch

from app import followups, outreach, scheduler


class FollowUpIncidentTests(unittest.TestCase):
    def test_only_one_scheduled_controller_and_unrelated_jobs_preserved(self):
        with patch('app.businesses.agent_enabled', return_value=True), patch('app.businesses.job_enabled', return_value=True):
            agents, jobs = scheduler.scheduled_plan()
        self.assertNotIn('follow_up_agent', agents)
        self.assertEqual(set(agents), set(scheduler.AGENTS) - {'follow_up_agent'})
        self.assertEqual(set(jobs), set(scheduler._JOBS))
        self.assertIn('followups', jobs)

    def test_confirmed_invalid_addresses_exact_only(self):
        for addr in ['you@company.com', ' COSTCONEWS@ONLINE.COSTCO.COM ']:
            self.assertFalse(outreach.is_real_email(addr))
        for addr in ['sales@company.com', 'buyer@online.costco.com', 'info@legitimate-business.org']:
            self.assertTrue(outreach.is_real_email(addr))

    def test_concurrent_local_invocations_process_once(self):
        db = MagicMock()
        db.get_bind.return_value.dialect.name = 'sqlite'
        entered, release = threading.Event(), threading.Event()
        result = {'sent': 1}
        def run(*args):
            entered.set()
            self.assertTrue(release.wait(5))
            return result
        with patch.object(followups, '_process_due_followups', side_effect=run) as process:
            first = threading.Thread(target=followups.process_due_followups, args=(db,))
            first.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertTrue(followups.process_due_followups(db)['skipped_concurrent'])
                self.assertEqual(process.call_count, 1)
            finally:
                release.set()
                first.join(5)

    def pg(self, acquired=True):
        db = MagicMock()
        bind = db.get_bind.return_value
        bind.dialect.name = 'postgresql'
        connection = bind.engine.connect.return_value.__enter__.return_value
        connection.execute.return_value.scalar.return_value = acquired
        return db, connection

    def test_pg_busy_never_processes(self):
        db, connection = self.pg(False)
        with patch.object(followups, '_process_due_followups') as process:
            self.assertTrue(followups.process_due_followups(db)['skipped_concurrent'])
            process.assert_not_called()
        self.assertEqual(connection.execute.call_count, 1)

    def test_pg_lock_on_separate_connection_survives_processing_commit(self):
        db, connection = self.pg()
        def process(session, limit):
            session.commit()
            self.assertEqual(connection.execute.call_count, 1)
            return {'sent': 1}
        with patch.object(followups, '_process_due_followups', side_effect=process):
            self.assertEqual(followups.process_due_followups(db), {'sent': 1})
        self.assertIn('pg_advisory_unlock', str(connection.execute.call_args.args[0]))
        connection.invalidate.assert_not_called()

    def test_failure_releases_lock(self):
        db, connection = self.pg()
        with patch.object(followups, '_process_due_followups', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                followups.process_due_followups(db)
        self.assertIn('pg_advisory_unlock', str(connection.execute.call_args.args[0]))

    def test_unlock_failure_invalidates_connection(self):
        db, connection = self.pg()
        ok = MagicMock()
        ok.scalar.return_value = True
        connection.execute.side_effect = [ok, RuntimeError('connection lost')]
        with patch.object(followups, '_process_due_followups', return_value={}):
            with self.assertRaises(RuntimeError):
                followups.process_due_followups(db)
        connection.invalidate.assert_called_once()


def test_real_postgres_lock_survives_commit_and_blocks_other_session():
    import pytest
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from app.database import engine
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
    except Exception:
        pytest.skip('PostgreSQL not reachable')
    entered, release = threading.Event(), threading.Event()
    errors = []
    def process(db, limit):
        db.execute(text('SELECT 1'))
        db.commit()  # dispatcher commit must not release the dedicated lock
        entered.set()
        if not release.wait(5):
            raise AssertionError('test release timed out')
        return {'sent': 1}
    def worker():
        try:
            with Session(engine) as db:
                followups.process_due_followups(db)
        except BaseException as exc:
            errors.append(exc)
    with patch.object(followups, '_process_due_followups', side_effect=process) as inner:
        first = threading.Thread(target=worker)
        first.start()
        try:
            assert entered.wait(5)
            with Session(engine) as db:
                assert followups.process_due_followups(db)['skipped_concurrent']
            assert inner.call_count == 1
        finally:
            release.set()
            first.join(5)
        assert not errors
    # A later invocation must run, proving the connection did not leak its lock.
    with Session(engine) as db, patch.object(followups, '_process_due_followups', return_value={'sent': 0}) as inner:
        assert followups.process_due_followups(db) == {'sent': 0}
        inner.assert_called_once()
