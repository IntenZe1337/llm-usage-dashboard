# Changelog

## [Unreleased]

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
