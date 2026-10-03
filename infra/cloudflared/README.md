# Cloudflare named tunnel: pipeguard.blunelabs.com

1. Zero Trust dashboard -> Networks -> Tunnels -> create a tunnel; copy the token into `.env` as `CLOUDFLARE_TUNNEL_TOKEN`.
2. Public hostname `pipeguard.blunelabs.com` -> service `http://web:80`.
   Prerequisite: `blunelabs.com` must be a Cloudflare-managed zone.
3. `make tunnel` (or `docker compose -f infra/docker-compose.yml --profile tunnel up -d cloudflared`).

**Never run the same token on two machines at once.** For the laptop fallback use a second
hostname (`pipeguard-backup.blunelabs.com`) or stop the server's `cloudflared` first.
See docs/techstack.md section 15.2.
