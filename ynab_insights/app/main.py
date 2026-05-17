from fastapi import FastAPI

from app.routers import health, sync

app = FastAPI(title="ynab-insights")
app.include_router(health.router)
app.include_router(sync.router)
