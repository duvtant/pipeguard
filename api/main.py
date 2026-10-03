"""PipeGuard API (stub). Owner: Ebube. Spec: docs/techstack.md section 11.

Only /api/health exists so far. Routers in api/routers/ get included here as they are built.
"""
from fastapi import FastAPI

app = FastAPI(title="PipeGuard API", docs_url="/docs", openapi_url="/openapi.json")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "api"}
