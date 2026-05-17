from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import AskResult, run_agent
from app.config import Settings, get_settings
from app.db import get_session

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    budget_id: str | None = None


@router.post("/ask", response_model=AskResult)
async def ask(
    body: AskRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> AskResult:
    if settings.anthropic_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not configured",
        )
    return await run_agent(
        session=session,
        settings=settings,
        question=body.question,
        budget_id=body.budget_id,
    )
