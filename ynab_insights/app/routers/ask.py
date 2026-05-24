"""POST /ask (v2.5).

Streams Claude's tool-use turn against the session's snapshot using the
user-provided Anthropic key. Backend stays stateless; the frontend posts
the prior conversation history on every request.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.stream import stream_agent
from app.config import Settings, get_settings
from app.session.middleware import CurrentSessionDep

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/ask")
async def ask(
    body: AskRequest,
    session: CurrentSessionDep,
    settings: SettingsDep,
) -> StreamingResponse:
    if session.snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "no_budget_selected", "message": "Pick a budget first."},
        )
    generator = stream_agent(
        snapshot=session.snapshot,
        anthropic_key=session.anthropic_key,
        settings=settings,
        question=body.question,
        history=body.history,
        anthropic_model=session.anthropic_model,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
