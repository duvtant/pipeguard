# Deploy on the Hetzner server

Owner: Ebube. Result: https://pipeguard.blunelabs.com serves the whole stack with automatic HTTPS.

## 1. DNS (Porkbun, once)
Add an `A` record: Host `pipeguard`, Answer = the server's public IPv4, TTL 600 (optionally an `AAAA` for IPv6).
Check it: `dig +short pipeguard.blunelabs.com` returns the server's IP. Caddy cannot get a certificate until this resolves.

## 2. Firewall (Hetzner Cloud Firewall)
Allow inbound: `22/tcp` (your IP only), `80/tcp`, `443/tcp`, `443/udp`. Nothing else.
**Docker-published ports bypass the host firewall (ufw does not stop them).** That is why compose binds `api` and `web`
to `127.0.0.1` and publishes only Caddy on 80/443. The database is never published.

## 3. Run
```bash
git clone git@github.com:duvtant/pipeguard.git && cd pipeguard
cp .env.example .env        # fill in the secrets (never commit .env)
make prod                   # docker compose --profile prod up -d --build  (builds on this machine)
```

## 4. Check
```bash
curl -fsS https://pipeguard.blunelabs.com/api/health
./scripts/preflight
```
If HTTPS fails: `docker compose -f infra/docker-compose.yml logs caddy` (usually the A record has not propagated or 80/443 is blocked).

## Notes
- Keep the `caddy_data` volume. Deleting it forces a new certificate request, and Let's Encrypt rate-limits those.
- A laptop is not reachable from the internet, so ElevenLabs tool calls cannot reach a laptop copy. The laptop fallback runs the full
  stack locally with **Simulate call** (no live voice). See docs/techstack.md section 15.3.
