"""One-time edit of api/main.py: start the sweeper and mount the real routers when MOCK_API is off.

Safe to run twice. Run from the repo root:  python scripts/patch_main.py
"""
from pathlib import Path

path = Path("api/main.py")
src = path.read_text(encoding="utf-8")

if "sweeper_loop" in src:
    raise SystemExit("api/main.py is already patched, nothing to do")

ANCHOR = 'app = FastAPI(title="PipeGuard API")'
if src.count(ANCHOR) != 1:
    raise SystemExit(f"expected exactly one line: {ANCHOR}")

LIFESPAN = '''from contextlib import asynccontextmanager, suppress


@asynccontextmanager
async def lifespan(_app):
    # Real mode only: the one-second sweeper expires unanswered rings (core/alerts.py).
    task = None
    if not settings.mock_api:
        from core.alerts import sweeper_loop
        task = asyncio.create_task(sweeper_loop())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="PipeGuard API", lifespan=lifespan)'''

ELSE_BRANCH = '''

else:
    # Real mode. Routers are added here as they are built.
    from api.routers import field
    app.include_router(field.router)
'''

src = src.replace(ANCHOR, LIFESPAN)
src = src.rstrip("\n") + "\n" + ELSE_BRANCH
path.write_text(src, encoding="utf-8")
print("patched api/main.py")
