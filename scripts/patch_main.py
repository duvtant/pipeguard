"""Edit api/main.py so real mode starts the sweeper and mounts the real routers.

Safe to run any number of times: each piece is added only if it is missing.
Run from the repo root:  python scripts/patch_main.py
"""
from pathlib import Path

path = Path("api/main.py")
src = path.read_text(encoding="utf-8")
done = []

# 1. Sweeper: starts with the app in real mode (core/alerts.py).
ANCHOR = 'app = FastAPI(title="PipeGuard API")'
if "sweeper_loop" not in src:
    if src.count(ANCHOR) != 1:
        raise SystemExit(f"expected exactly one line: {ANCHOR}")
    src = src.replace(ANCHOR, '''from contextlib import asynccontextmanager, suppress


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


app = FastAPI(title="PipeGuard API", lifespan=lifespan)''')
    done.append("sweeper")

# 2. Real routers, in an else branch after the MOCK_API block.
if "app.include_router(field.router)" not in src:
    src = src.rstrip("\n") + '''


else:
    # Real mode. Routers are added here as they are built.
    from api.routers import field
    app.include_router(field.router)
'''
    done.append("field router")

if "voice.router" not in src:
    old = "    from api.routers import field\n    app.include_router(field.router)\n"
    if old not in src:
        raise SystemExit("could not find the field router lines in api/main.py")
    src = src.replace(old, "    from api.routers import field, voice\n    app.include_router(field.router)\n"
                           "    app.include_router(voice.router)\n")
    done.append("voice router")

if done:
    path.write_text(src, encoding="utf-8")
    print("patched api/main.py:", ", ".join(done))
else:
    print("api/main.py already has everything, nothing to do")
