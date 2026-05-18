# llm-usage-dashboard Runbook

Version: 2026-05-18

## Miljö

- Repo på Hetzner: `/home/rasmus/dev/llm-usage-dashboard`
- Tjänst: Docker Compose-service `llm-usage-dashboard`
- Container: `llm-usage-dashboard`
- Lyssnar på: `100.106.95.127:8099`
- Non-interaktiv SSH från Windows: `ssh -T hetzner-raw "..."` eller `ssh -T ipt "..."`
- `ssh hetzner` är interaktiv tmux-host och ska inte användas för fjärrkommandon.

## Deploy

```bash
cd /home/rasmus/dev/llm-usage-dashboard
git pull --ff-only
python3 -m py_compile app/main.py
docker compose up -d --build
docker compose ps
curl -fsS http://100.106.95.127:8099/health
```

Från Windows:

```powershell
ssh -T hetzner-raw "cd /home/rasmus/dev/llm-usage-dashboard && git pull --ff-only && python3 -m py_compile app/main.py && docker compose up -d --build && docker compose ps && curl -fsS http://100.106.95.127:8099/health"
```

## Verifiering

```bash
cd /home/rasmus/dev/llm-usage-dashboard
git status --short --branch
git rev-parse --short HEAD
python3 -m py_compile app/main.py
docker compose ps
curl -fsS http://100.106.95.127:8099/health
curl -fsS http://100.106.95.127:8099/usage/codex-local
curl -fsS http://100.106.95.127:8099/usage/claude-local
```

## Loggar

```bash
cd /home/rasmus/dev/llm-usage-dashboard
docker compose logs --tail=100 llm-usage-dashboard
docker inspect --format '{{.State.Status}} {{.State.StartedAt}}' llm-usage-dashboard
```

## Refresh-auth

Om `REFRESH_TOKEN` är satt i `.env` kräver `POST /refresh` bearer-token:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $REFRESH_TOKEN" \
  http://100.106.95.127:8099/refresh
```

Om `REFRESH_TOKEN` är tomt är `/refresh` bakåtkompatibelt oskyddad.

## Rollback

```bash
cd /home/rasmus/dev/llm-usage-dashboard
git log --oneline -5
git checkout <tidigare-commit>
docker compose up -d --build
curl -fsS http://100.106.95.127:8099/health
```

Efter tillfällig rollback: skapa ny fix-branch eller gå tillbaka till `main` med `git checkout main`.
