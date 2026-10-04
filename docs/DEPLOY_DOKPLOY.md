# Deploy PipeGuard on Dokploy

**One Compose service runs everything.** Do not create separate Application and Database services: PipeGuard is five containers that talk to each other by name (`db`, `api`, `engine`, `simulator`, `web`), and a single Compose service keeps them on one private network. The `web` container serves the dashboard and proxies `/api` (including the live streams) to the `api` container, so **only `web` needs a public domain**. Dokploy's Traefik provides HTTPS, so Caddy is not used.

The file `infra/docker-compose.dokploy.yml` was tested on a Mac with a fresh database: stack starts, the first seed works through the app, the dashboard, `/api`, live streams and `/field/...` links all answer through `web`.

## 1. DNS (Porkbun)
`A` record: host `pipeguard`, answer = the Hetzner server's IPv4, TTL 600. Check: `dig +short pipeguard.blunelabs.com` returns the IP. The domain must be `pipeguard.blunelabs.com`, because the ElevenLabs agent and webhook already point there.

## 2. Create the service in Dokploy
1. **Create Project** (for example `pipeguard`), then **Create Service → Compose**.
2. **Provider / Source:** Git. Repository `duvtant/pipeguard`, **branch `dev`** (`main` does not have the work yet). If the repo is private, connect GitHub in Dokploy or add a deploy key.
3. **Compose Path:** `./infra/docker-compose.dokploy.yml`. **Compose Type:** Docker Compose (not Stack: Stack mode does not support `build`).

## 3. Environment tab (paste, then fill)
Dokploy writes these to a `.env` for compose interpolation; the compose file passes each one into the containers explicitly. **Never commit them or paste them into chat; copy the values from your local `.env`.**
```
POSTGRES_PASSWORD=<pick a long random value>
ELEVENLABS_API_KEY=<from your local .env>
ELEVENLABS_AGENT_ID=agent_0201m40dhg4pfdqaq537zb3ckdrv
ELEVENLABS_WEBHOOK_SECRET=<from infra/elevenlabs/.env or your local .env>
ELEVENLABS_ENVIRONMENT=production
VOICE_TOOL_SECRET=<the value WITHOUT the "Bearer " prefix; it must match the ElevenLabs secret pipeguard_voice_tool_auth>
ADMIN_TOKEN=<pick a long random value; you type it into Test mode>
PUBLIC_BASE_URL=https://pipeguard.blunelabs.com
DOMAIN=pipeguard.blunelabs.com
```

## 4. Domains tab
Add one domain: **Host** `pipeguard.blunelabs.com`, **Service Name** `web`, **Container Port** `80`, **HTTPS on**, **Certificate: Let's Encrypt**. Compose services need a **redeploy** after any domain change.

## 5. Deploy, then seed once
1. Click **Deploy** and watch the build log (first build takes a few minutes).
2. The database starts empty, so the API reports "degraded" until it is seeded. **Seed it once from your Mac:**
```
curl -X POST https://pipeguard.blunelabs.com/api/clock -H 'Content-Type: application/json' -d '{"action":"reset"}'
```
(Or press **Reset replay** on the Fleet page.) This loads the 100 turbines, the technicians, and pauses the clock at day 0.

## 6. Check it
```
curl -s https://pipeguard.blunelabs.com/api/health
```
should show `"status":"ok"`, `"database":true`, and `elevenlabs_configured`, `webhook_secret_set`, `voice_tool_secret_set`, `admin_token_set` all `true`. Then open the dashboard, press **Play replay**, and watch **HIN-02 (Hinton) turn red at about 29 seconds**. Finally run `./scripts/preflight` from your Mac.

## If something goes wrong
- **HTTPS error or certificate not issued:** DNS has not propagated yet, or port 80 or 443 is blocked (Hetzner firewall must allow 80, 443/tcp and 443/udp).
- **Domain shows "404 page not found" from Traefik:** the domain's Service Name must be `web` and the port `80`, and you must redeploy after changing it.
- **Dashboard loads but the data is empty or "cannot reach server":** the database has not been seeded yet (step 5).
- **A deploy that changed the database schema looks stuck:** the API and engine apply new columns on start; check the `api` log.
- **Keep the `pgdata` volume.** Deleting it wipes the demo state; you can re-seed in seconds (step 5). The technicians' phone links stay the same after a reset, but they are derived from `ADMIN_TOKEN`, so **changing `ADMIN_TOKEN` changes every phone link**. Set it once and leave it.

## Rehearsal rules on the server
- Use **Play replay**, not "advance", for rehearsals (advance leaves the engine in a different state).
- **Reset replay** before every run so the scenario is identical.
- Each real voice call costs real ElevenLabs credits (about 480 per minute of call).
