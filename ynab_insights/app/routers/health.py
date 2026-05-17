from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter()


@router.get("/")
def root(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "message": "Hello",
        "version": settings.app_version,
        "env": settings.app_env,
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
