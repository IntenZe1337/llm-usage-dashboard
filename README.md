# llm-usage-dashboard

> **Senaste version:** [`v1-post2`](https://github.com/IntenZe1337/llm-usage-dashboard/releases/latest) — Homepage-endpoints, byggversion och CORS.
> Versionshistorik: [Releases](https://github.com/IntenZe1337/llm-usage-dashboard/releases) · [CHANGELOG.md](CHANGELOG.md)

Minimalistisk FastAPI-tjänst som exponerar lokal Claude Code-/Codex-användning, API-tokenanvändning och abonnemangs-/rate-limit-status som JSON för Homepage och en enkel HTML-dashboard.

## Endpoints

| Endpoint | Beskrivning |
|---|---|
| `GET /` | HTML-dashboard |
| `POST /refresh` | Tvingar cache-refresh. Kan skyddas med `REFRESH_TOKEN`. |
| `GET /usage` | Kombinerad JSON med alla datakällor |
| `GET /usage/claude-local` | Claude Code-tokenräkning från lokal JSONL |
| `GET /usage/codex-local` | Codex-tokenräkning från lokal SQLite |
| `GET /usage/codex-limits` | Codex 5h/7d rate-limit-procent |
| `GET /usage/claude-subscription` | Claude 5h/7d abonnemangsprocent |
| `GET /usage/claude` | Anthropic Admin API usage |
| `GET /usage/openai` | OpenAI Admin API usage |
| `GET /health` | Process- och konfigstatus |

## Konfiguration

Lokal data kräver inga API-nycklar, men Docker Compose monterar förväntade kataloger från Hetzner-användaren `rasmus`.

```bash
cp .env.example .env
```

Viktiga val:

| Variabel | Användning |
|---|---|
| `CLAUDE_SESSION_KEY`, `CLAUDE_SESSION_KEY_LC`, `CLAUDE_COOKIE`, `CLAUDE_ORG_ID` | Claude.ai abonnemangsstatus |
| `ANTHROPIC_ADMIN_KEY` | Anthropic Admin API usage |
| `OPENAI_ADMIN_KEY` | OpenAI Admin API usage |
| `CACHE_TTL_SECONDS` | Cachetid i sekunder |
| `REFRESH_TOKEN` | Om satt kräver `POST /refresh` `Authorization: Bearer <token>` |
| `CORS_ALLOW_ORIGINS` | Kommaseparerad allowlist. Tomt betyder ingen CORS-middleware. |

## Lokal kontroll

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m py_compile app/main.py
```

## Deploy

```bash
docker compose up -d --build
curl -fsS http://100.106.95.127:8099/health
```

Se [docs/runbook.md](docs/runbook.md) för Hetzner-runbook med SSH-alias, verifiering och felsökning.
