from fastapi import FastAPI

from app.routers import health

app = FastAPI(title="ynab-insights")
app.include_router(health.router)
