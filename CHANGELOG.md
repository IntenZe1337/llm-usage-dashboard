# Changelog

Alla notabla ändringar dokumenteras här. Formatet följer
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Security
- Uppgraderar FastAPI/Starlette/Uvicorn och Dockerbildens `pip` för att ta bort
  kända CVE/GHSA-fynd i den körande containern.
- Uppdaterar Compose-image-taggen så deployen kan verifiera att den rebuildade
  dependencybilden faktiskt körs.
- Uppgraderar testberoendet `pytest` så även repo/dev-auditen är fri från kända
  GHSA-fynd.

## [2026-05-22] - v1-post2

### Added
- API-kontraktstester för Homepage- och dashboard-endpoints.
- `docs/runbook.md` med Hetzner-deploy och verifieringskommandon.
- Platta endpoints för Homepage: `/usage/claude-subscription` och `/usage/codex-limits` exponerar 5h/7d-procent.

### Fixed
- Claude-abonnemangskortet visar nu kvarvarande procent i 5h/7d-fönster i stället för förbrukad procent.
- Claude-abonnemangsprocent stöder nu Claude-webbens aktuella `five_hour`/`seven_day`-schema med `utilization` och ISO-reset.
- Claude-webbhämtning kan använda full cookie-sträng och fast org-id när `sessionKey` ensam ger 403.

### Changed
- `POST /refresh` kan skyddas med `REFRESH_TOKEN`; CORS är nu opt-in via `CORS_ALLOW_ORIGINS`.
- HTML-dashboarden visar appens byggversion.

## [2026-05-17.1] - v1-mvp (post1)

### Changed
- Claude Code: läser nu JSONL-projektfiler istället för session-meta → korrekt token-räkning inkl. cache-tokens
- Codex: läser tokens_used från ~/.codex/state_5.sqlite (lokal DB)
- Ny HTML-dashboard på / med refreshknapp och live JS-rendering
- POST /refresh bustar cachen och uppdaterar all data omedelbart
- Docker Compose monterar ~/.codex och ~/.claude som read-only volymer
- Homepage-widgetar pekade om till /usage/claude-local och /usage/codex-local

## [2026-05-17] - v1-mvp

### Added
- FastAPI-tjänst med endpoints `/usage`, `/usage/claude`, `/usage/openai`, `/health`
- Hämtar token-användning (idag) från Anthropic Admin API och OpenAI Admin API
- 5-minuterscache för att respektera API rate limits
- Docker Compose-deploy med Tailscale-bunden port 8099
- Homepage customapi-widget-konfiguration för Claude och OpenAI
