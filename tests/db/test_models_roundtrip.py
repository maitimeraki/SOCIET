"""Live roundtrip test for the Postgres schema.

Requires DATABASE_URL and a migrated database (`alembic upgrade head`); the
whole module is skipped without it. No mocks — every assertion reads real
database behavior.
"""

import datetime
import ipaddress
import os
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.db.engine import get_engine, get_session_factory
from src.db.models import AuditLog, Dataset, Job, Run, RunEvent, Session, Upload, User

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL is not set"
)

TEST_EMAIL = "roundtrip@example.com"
TEST_ACTION = "roundtrip.test"


@pytest.mark.asyncio
async def test_schema_roundtrip_and_fk_behavior():
    factory = get_session_factory()
    ids: dict[str, uuid.UUID] = {}
    try:
        # A failed earlier run must not poison this one.
        async with factory() as db:
            await db.execute(delete(User).where(User.email == TEST_EMAIL))
            await db.execute(delete(AuditLog).where(AuditLog.action == TEST_ACTION))
            await db.commit()

        async with factory() as db:
            user = User(email=TEST_EMAIL, password_hash="$2b$12$roundtrip")
            db.add(user)
            await db.flush()  # pulls the server-generated uuid
            ids["user"] = user.id

            session_row = Session(
                user_id=user.id,
                expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
                user_agent="pytest/1.0",
                ip="127.0.0.1",
            )
            dataset = Dataset(
                id=uuid.uuid4(), user_id=user.id, name="roundtrip dataset", graph_id="graph-1"
            )
            db.add_all([session_row, dataset])
            await db.flush()
            ids["session"], ids["dataset"] = session_row.id, dataset.id

            run = Run(
                id=uuid.uuid4(),
                user_id=user.id,
                dataset_id=dataset.id,
                query="Should we expand into Europe?",
                status="queued",
            )
            db.add(run)
            await db.flush()
            ids["run"] = run.id

            job = Job(id=uuid.uuid4(), user_id=user.id, run_id=run.id, kind="debate", status="queued")
            upload = Upload(
                id=uuid.uuid4(),
                user_id=user.id,
                dataset_id=dataset.id,
                object_key="uploads/one.pdf",
                bytes=1234,
                mime="application/pdf",
                sha256="a" * 64,
            )
            event = RunEvent(id=uuid.uuid4(), run_id=run.id, seq=1, type="started", payload={"round": 1})
            db.add_all([job, upload, event])
            await db.commit()
            ids["job"], ids["upload"], ids["event"] = job.id, upload.id, event.id

        # --- read the chain back through fresh selects ------------------------
        async with factory() as db:
            user = (
                await db.execute(select(User).where(User.id == ids["user"]))
            ).scalar_one()
            assert (user.email, user.password_hash) == (TEST_EMAIL, "$2b$12$roundtrip")
            assert user.disabled_at is None
            # timestamptz comes back tz-aware; a plain timestamp would not.
            assert user.created_at.tzinfo is not None and user.updated_at.tzinfo is not None

            session_row = (
                await db.execute(select(Session).where(Session.id == ids["session"]))
            ).scalar_one()
            assert (session_row.user_id, session_row.user_agent, session_row.revoked_at) == (
                ids["user"],
                "pytest/1.0",
                None,
            )
            assert ipaddress.ip_interface(str(session_row.ip)).ip == ipaddress.ip_address("127.0.0.1")

            dataset = (
                await db.execute(select(Dataset).where(Dataset.id == ids["dataset"]))
            ).scalar_one()
            assert (dataset.user_id, dataset.name, dataset.graph_id) == (
                ids["user"],
                "roundtrip dataset",
                "graph-1",
            )

            run = (await db.execute(select(Run).where(Run.id == ids["run"]))).scalar_one()
            assert (run.user_id, run.dataset_id, run.query, run.status, run.verdict) == (
                ids["user"],
                ids["dataset"],
                "Should we expand into Europe?",
                "queued",
                None,
            )

            job = (await db.execute(select(Job).where(Job.id == ids["job"]))).scalar_one()
            assert (job.user_id, job.run_id, job.kind, job.status, job.attempts, job.error) == (
                ids["user"],
                ids["run"],
                "debate",
                "queued",
                0,
                None,
            )

            upload = (
                await db.execute(select(Upload).where(Upload.id == ids["upload"]))
            ).scalar_one()
            assert (upload.object_key, upload.bytes, upload.mime, upload.sha256) == (
                "uploads/one.pdf",
                1234,
                "application/pdf",
                "a" * 64,
            )

            event = (
                await db.execute(select(RunEvent).where(RunEvent.id == ids["event"]))
            ).scalar_one()
            assert (event.run_id, event.seq, event.type, event.payload) == (
                ids["run"],
                1,
                "started",
                {"round": 1},
            )

        # --- (run_id, seq) is unique ------------------------------------------
        async with factory() as db:
            db.add(RunEvent(id=uuid.uuid4(), run_id=ids["run"], seq=1, type="duplicate"))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()

        async with factory() as db:
            audit = AuditLog(
                id=uuid.uuid4(),
                user_id=ids["user"],
                action=TEST_ACTION,
                target=str(ids["run"]),
                ip="10.0.0.1",
                meta={"ok": True},
            )
            db.add(audit)
            await db.commit()
            ids["audit"] = audit.id

        # --- deleting the user cascades; audit_log is orphaned, not deleted ----
        async with factory() as db:
            user = (await db.execute(select(User).where(User.id == ids["user"]))).scalar_one()
            await db.delete(user)
            await db.commit()

        async with factory() as db:
            children = (
                (Session, "session"),
                (Dataset, "dataset"),
                (Run, "run"),
                (Job, "job"),
                (Upload, "upload"),
                (RunEvent, "event"),
            )
            for model, key in children:
                surviving = (
                    await db.execute(select(model).where(model.id == ids[key]))
                ).scalar_one_or_none()
                assert surviving is None, f"{model.__tablename__} row survived the user delete"

            audit = (
                await db.execute(select(AuditLog).where(AuditLog.id == ids["audit"]))
            ).scalar_one()
            assert (audit.user_id, audit.action) == (None, TEST_ACTION)
    finally:
        async with factory() as db:
            await db.execute(delete(User).where(User.email == TEST_EMAIL))
            await db.execute(delete(AuditLog).where(AuditLog.action == TEST_ACTION))
            await db.commit()
        await get_engine().dispose()
