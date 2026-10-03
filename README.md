# PipeGuard

Predicts which pipeline compressor turbine will fail next, schedules the fix within crew limits,
and calls the on-call technician with a voice agent whose answer re-plans the week.

IEEE YP Industry Hackathon 2026, Energy and Infrastructure Systems, Option A.
Team: Olise (ML engine), Ebube (backend), David (dashboard, voice pipeline, pitch).

> **Simulated company.** Prairie Gas Transmission, its technicians and all costs are fictional.
> Turbine data is NASA C-MAPSS FD001 (turbofan degradation), used as a stand-in: operators do not
> publish turbine sensor data. We never claim it is pipeline data.

## Run it

```bash
cp .env.example .env        # fill in secrets locally; never commit .env
make up                     # docker compose: db, api, engine, simulator, web
open http://localhost:8088  # dashboard (set WEB_PORT in .env to change; api on :8000)
```

Dev loop for the dashboard: `make web-dev` (Vite on :5173, proxies /api to :8000).

## Docs
- `docs/PipeGuard_Overview.md`: product, pitch, business case
- `docs/techstack.md`: technical specification (source of truth)
- `docs/delegation/`: per-person guides and the team contract

## Data and credits
- NASA C-MAPSS FD001: A. Saxena, K. Goebel, D. Simon, N. Eklund, "Damage Propagation Modeling for
  Aircraft Engine Run-to-Failure Simulation," PHM 2008. Files in `ml/data/`.
- Voice: ElevenLabs Agents (hackathon sponsor).

_Full judge-facing README (architecture diagram, results vs baseline, limitations) is written at the end._
