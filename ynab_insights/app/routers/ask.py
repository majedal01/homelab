from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.stream import stream_agent
from app.config import Settings, get_settings
from app.db import get_session

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class AskRequest(BaseModel):
    """Streaming ask request.

    `history` is the prior conversation in Anthropic message format.
    The frontend persists this in sessionStorage and posts it on every
    request; the backend stays stateless.
    """

    question: str = Field(min_length=1, max_length=1000)
    budget_id: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/ask")
async def ask(
    body: AskRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> StreamingResponse:
    if settings.anthropic_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not configured",
        )
    generator = stream_agent(
        session=session,
        settings=settings,
        question=body.question,
        budget_id=body.budget_id,
        history=body.history,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            # Disable buffering for any reverse proxies sitting in front.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
