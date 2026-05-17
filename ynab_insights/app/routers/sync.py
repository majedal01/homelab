from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.services.sync import SyncResult, run_sync

router = APIRouter()


@router.post("/sync", response_model=SyncResult)
async def trigger_sync(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SyncResult:
    if settings.ynab_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YNAB_TOKEN is not configured",
        )
    return await run_sync(session, settings.ynab_token)
