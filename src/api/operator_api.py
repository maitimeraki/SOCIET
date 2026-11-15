"""Operator reads of backend-only agent records (spec §5, §8).

The only route that returns an AgentRecord. It is cross-tenant by design, so it is
guarded by the router-level role check (support, admin), not by require_owner. Every
read appends an audit row. The row names the run and node only, never the record.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src import audit
from src.api import run_doc
from src.auth.deps import current_user, require_role
from src.db.engine import get_db
from src.db.models import User

router = APIRouter(
    prefix="/operator",
    tags=["operator"],
    dependencies=[Depends(require_role("support", "admin"))],
)


@router.get("/runs/{run_id}/agents/{node_id}")
async def get_agent_record(
    run_id: str,
    node_id: str,
    request: Request,
    operator: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """One candidate's stored record. Unknown run or node is the same 404.

    The audit row is written before the record is returned, and a failed audit
    write fails the read: nothing is returned unaudited.
    """
    record = await run_doc.read_agent_record(run_id, node_id)
    await audit.record(
        db,
        "agent_record_read",
        user_id=operator.id,
        target=run_id,
        ip=audit.client_ip(request),
        meta={"node_id": node_id, "found": record is not None},
        required=True,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Not found.")
    return record
