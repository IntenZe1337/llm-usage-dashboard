# llm-usage-dashboard

> **Senaste version:** [`v1-mvp`](https://github.com/IntenZe1337/llm-usage-dashboard/releases/latest) — MVP
> Versionshistorik: [Releases](https://github.com/IntenZe1337/llm-usage-dashboard/releases) · [CHANGELOG.md](CHANGELOG.md)

Minimalistisk API-tjänst som exponerar dagens token-användning för Claude (Anthropic) och OpenAI/Codex som JSON — avsedd för Homepage customapi-widgetar.

## Endpoints

| Endpoint | Beskrivning |
|---|---|
| `GET /usage` | Kombinerad JSON med Claude + OpenAI |
| `GET /usage/claude` | Platt JSON med enbart Claude-data |
| `GET /usage/openai` | Platt JSON med enbart OpenAI-data |
| `GET /health` | Status + version |

## Krav på API-nycklar

- **Anthropic:** Admin API-nyckel (`sk-ant-admin...`) — kräver att organisation är satt upp i [Claude Console](https://console.anthropic.com/settings/admin-keys)
- **OpenAI:** Admin API-nyckel — hämta från [platform.openai.com/settings/organization/admin-keys](https://platform.openai.com/settings/organization/admin-keys)

## Deploy

```bash
cp .env.example .env
# Fyll i nycklar i .env
docker compose up -d --build
```

## Homepage-widget (services.yaml)

```yaml
- AI & LLM:
    - Claude (idag):
        href: https://console.anthropic.com/usage
        icon: mdi-robot
        widget:
          type: customapi
          url: http://100.106.95.127:8099/usage/claude
          refreshInterval: 300000
          mappings:
            - field: input_tokens
              label: Input
              format: number
            - field: output_tokens
              label: Output
              format: number
            - field: total_tokens
              label: Totalt
              format: number
    - OpenAI/Codex (idag):
        href: https://platform.openai.com/usage
        icon: mdi-brain
        widget:
          type: customapi
          url: http://100.106.95.127:8099/usage/openai
          refreshInterval: 300000
          mappings:
            - field: input_tokens
              label: Input
              format: number
            - field: output_tokens
              label: Output
              format: number
            - field: total_tokens
              label: Totalt
              format: number
```
