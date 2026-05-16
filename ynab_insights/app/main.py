import os

from fastapi import FastAPI

app = FastAPI(title="homelab-app")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Hello",
        "version": os.getenv("APP_VERSION", "0.1.0"),
        "env": os.getenv("APP_ENV", "stage"),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
