# Changelog

## [Unreleased]

## [2026-05-17] - v1-mvp

### Added
- FastAPI-tjänst med endpoints `/usage`, `/usage/claude`, `/usage/openai`, `/health`
- Hämtar token-användning (idag) från Anthropic Admin API och OpenAI Admin API
- 5-minuterscache för att respektera API rate limits
- Docker Compose-deploy med Tailscale-bunden port 8099
- Homepage customapi-widget-konfiguration för Claude och OpenAI
