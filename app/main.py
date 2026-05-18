__version__ = "2026.5.18.post3"

import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="LLM Usage Dashboard", version=__version__)

ANTHROPIC_ADMIN_KEY = os.getenv("ANTHROPIC_ADMIN_KEY", "")
OPENAI_ADMIN_KEY = os.getenv("OPENAI_ADMIN_KEY", "")
CLAUDE_SESSION_KEY = os.getenv("CLAUDE_SESSION_KEY", "")
CLAUDE_SESSION_KEY_LC = os.getenv("CLAUDE_SESSION_KEY_LC", "")
CLAUDE_COOKIE = os.getenv("CLAUDE_COOKIE", "")
CLAUDE_ORG_ID = os.getenv("CLAUDE_ORG_ID", "")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "")
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
]

if CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

CODEX_DB = Path(os.getenv("CODEX_DB", "/data/codex/state_5.sqlite"))
CODEX_SESSIONS_DIR = Path(os.getenv("CODEX_SESSIONS_DIR", "/data/codex/sessions"))
CLAUDE_META_DIR = Path(os.getenv("CLAUDE_META_DIR", "/data/claude/usage-data/session-meta"))
CLAUDE_PROJECTS_DIR = Path(os.getenv("CLAUDE_PROJECTS_DIR", "/data/claude/projects"))

_cache: dict = {}
_cache_time: float = 0.0


# ── Local data readers ────────────────────────────────────────────────────────

def _read_codex_local() -> dict:
    if not CODEX_DB.exists():
        return {"available": False, "tokens_today": None, "tokens_7d": None, "sessions_today": None}
    try:
        con = sqlite3.connect(f"file:{CODEX_DB}?mode=ro", uri=True)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        start_today = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        start_7d = now_ts - 7 * 86400

        row_today = con.execute(
            "SELECT COALESCE(SUM(tokens_used),0), COUNT(*) FROM threads WHERE created_at >= ?",
            (start_today,)
        ).fetchone()
        row_7d = con.execute(
            "SELECT COALESCE(SUM(tokens_used),0) FROM threads WHERE created_at >= ?",
            (start_7d,)
        ).fetchone()
        con.close()
        return {
            "available": True,
            "tokens_today": row_today[0],
            "sessions_today": row_today[1],
            "tokens_7d": row_7d[0],
        }
    except Exception as e:
        return {"available": False, "error": str(e), "tokens_today": None, "tokens_7d": None}


def _read_codex_rate_limits() -> dict:
    """Läs senaste rate_limits med faktisk used_percent från Codex session-JSONL."""
    if not CODEX_SESSIONS_DIR.exists():
        return {"available": False}
    try:
        files = sorted(CODEX_SESSIONS_DIR.glob("**/*.jsonl"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for fpath in files[:30]:
            lines = list(fpath.open(errors="ignore"))
            for line in reversed(lines):
                try:
                    d = json.loads(line)
                    if d.get("type") != "event_msg":
                        continue
                    p = d.get("payload", {})
                    if p.get("type") != "token_count":
                        continue
                    rl = p.get("rate_limits") or {}
                    if not rl or rl.get("primary") is None:
                        continue
                    primary = rl.get("primary") or {}
                    secondary = rl.get("secondary") or {}
                    return {
                        "available": True,
                        "limit_id": rl.get("limit_id"),
                        "plan_type": rl.get("plan_type"),
                        "primary_used_pct": primary.get("used_percent"),
                        "primary_window_min": primary.get("window_minutes"),
                        "primary_resets_at": primary.get("resets_at"),
                        "secondary_used_pct": secondary.get("used_percent"),
                        "secondary_window_min": secondary.get("window_minutes"),
                        "secondary_resets_at": secondary.get("resets_at"),
                        "measured_at": d.get("timestamp", ""),
                    }
                except Exception:
                    pass
        return {"available": False, "note": "Ingen session med rate_limit-data hittad"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def _read_claude_local() -> dict:
    if not CLAUDE_PROJECTS_DIR.exists():
        return {"available": False, "tokens_5h": None, "tokens_7d": None, "sessions_5h": None}
    try:
        now = datetime.now(timezone.utc)
        cutoff_5h = (now - timedelta(hours=5)).isoformat()
        cutoff_7d = (now - timedelta(days=7)).isoformat()
        mtime_7d = now.timestamp() - 7 * 86400
        mtime_5h = now.timestamp() - 5 * 3600

        t_inp_5h = t_out_5h = t_cc_5h = t_cr_5h = 0
        t_inp_7d = t_out_7d = t_cc_7d = t_cr_7d = 0
        sessions_5h = 0

        for fpath in CLAUDE_PROJECTS_DIR.glob("**/*.jsonl"):
            if fpath.stat().st_mtime < mtime_7d:
                continue
            is_recent_file = fpath.stat().st_mtime >= mtime_5h
            try:
                for line in fpath.open(errors="ignore"):
                    try:
                        d = json.loads(line)
                        if d.get("type") != "assistant":
                            continue
                        usage = d.get("message", {}).get("usage") or d.get("usage")
                        if not usage:
                            continue
                        ts = d.get("timestamp", "")
                        inp = usage.get("input_tokens", 0)
                        out = usage.get("output_tokens", 0)
                        cc = usage.get("cache_creation_input_tokens", 0)
                        cr = usage.get("cache_read_input_tokens", 0)
                        if ts > cutoff_7d:
                            t_inp_7d += inp; t_out_7d += out; t_cc_7d += cc; t_cr_7d += cr
                        if ts > cutoff_5h:
                            t_inp_5h += inp; t_out_5h += out; t_cc_5h += cc; t_cr_5h += cr
                    except Exception:
                        pass
            except Exception:
                pass

        return {
            "available": True,
            "input_tokens_5h": t_inp_5h,
            "output_tokens_5h": t_out_5h,
            "cache_tokens_5h": t_cc_5h + t_cr_5h,
            "tokens_5h": t_inp_5h + t_out_5h + t_cc_5h + t_cr_5h,
            "input_tokens_7d": t_inp_7d,
            "output_tokens_7d": t_out_7d,
            "cache_tokens_7d": t_cc_7d + t_cr_7d,
            "tokens_7d": t_inp_7d + t_out_7d + t_cc_7d + t_cr_7d,
        }
    except Exception as e:
        return {"available": False, "error": str(e), "tokens_5h": None, "tokens_7d": None}


# ── Remote API readers ────────────────────────────────────────────────────────

async def _fetch_claude_subscription() -> dict:
    if not CLAUDE_SESSION_KEY and not CLAUDE_COOKIE:
        return {"configured": False}
    if CLAUDE_COOKIE:
        cookie = CLAUDE_COOKIE
    else:
        cookie = f"sessionKey={CLAUDE_SESSION_KEY}"
        if CLAUDE_SESSION_KEY_LC:
            cookie += f"; sessionKeyLC={CLAUDE_SESSION_KEY_LC}"
    headers = {
        "Cookie": cookie,
        "Accept": "*/*",
        "Referer": "https://claude.ai/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "anthropic-client-platform": "web_claude_ai",
        "anthropic-client-version": "1.0.0",
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            if CLAUDE_ORG_ID:
                org_id = CLAUDE_ORG_ID
            else:
                orgs_r = await client.get("https://claude.ai/api/organizations", headers=headers)
                orgs_r.raise_for_status()
                orgs = orgs_r.json()
                org_id = orgs[0]["uuid"]
            usage_r = await client.get(
                f"https://claude.ai/api/organizations/{org_id}/usage", headers=headers
            )
            usage_r.raise_for_status()
            return {"configured": True, **usage_r.json()}
        except Exception as e:
            return {"configured": True, "error": str(e)}


async def _fetch_api_usage(service: str) -> dict:
    """Fetch API-key-based usage (Claude admin API or OpenAI admin API)."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if service == "claude":
        if not ANTHROPIC_ADMIN_KEY:
            return {"configured": False}
        url = "https://api.anthropic.com/v1/organizations/usage_report/messages"
        params = {
            "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ending_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bucket_width": "1d",
        }
        headers = {"x-api-key": ANTHROPIC_ADMIN_KEY, "anthropic-version": "2023-06-01"}
    else:  # openai
        if not OPENAI_ADMIN_KEY:
            return {"configured": False}
        url = "https://api.openai.com/v1/organization/usage/completions"
        params = {"start_time": int(start.timestamp()), "bucket_width": "1d", "limit": 1}
        headers = {"Authorization": f"Bearer {OPENAI_ADMIN_KEY}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            return {"configured": True, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            return {"configured": True, "error": str(e)}

    inp = out = 0
    for bucket in data.get("data", []):
        for result in bucket.get("results", []):
            inp += result.get("input_tokens", 0)
            out += result.get("output_tokens", 0)
    return {"configured": True, "input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}


# ── Cache + combined endpoint ─────────────────────────────────────────────────

async def _build_data() -> dict:
    claude_api, openai_api, claude_sub = await asyncio.gather(
        _fetch_api_usage("claude"),
        _fetch_api_usage("openai"),
        _fetch_claude_subscription(),
    )
    return {
        "claude_code": _read_claude_local(),
        "codex": _read_codex_local(),
        "codex_limits": _read_codex_rate_limits(),
        "claude_api": claude_api,
        "openai_api": openai_api,
        "claude_subscription": claude_sub,
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }


async def _get_data(force: bool = False) -> dict:
    global _cache, _cache_time
    now = time.monotonic()
    if not force and _cache and (now - _cache_time) < CACHE_TTL:
        return _cache
    _cache = await _build_data()
    _cache_time = now
    return _cache


# ── HTML dashboard ────────────────────────────────────────────────────────────

def _fmt(n) -> str:
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


def _pct(usage_dict: dict, key: str) -> str:
    v = usage_dict.get(key)
    if v is None:
        return "—"
    return f"{v:.0%}"


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM Usage</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0 }}
  body {{ background: #0f1117; color: #e2e8f0; font-family: system-ui, sans-serif; padding: 1.5rem }}
  h1 {{ font-size: 1.1rem; font-weight: 600; color: #94a3b8; margin-bottom: 1.25rem; letter-spacing: .04em }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; max-width: 720px }}
  @media (max-width: 520px) {{ .grid {{ grid-template-columns: 1fr }} }}
  .card {{ background: #1e2330; border-radius: 10px; padding: 1rem 1.2rem }}
  .card h2 {{ font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: #64748b; margin-bottom: .8rem }}
  .row {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: .35rem }}
  .label {{ font-size: .8rem; color: #94a3b8 }}
  .value {{ font-size: .95rem; font-weight: 600; color: #f1f5f9 }}
  .bar-wrap {{ margin: .4rem 0 .6rem }}
  .bar-label {{ display: flex; justify-content: space-between; font-size: .72rem; color: #94a3b8; margin-bottom: .25rem }}
  .bar-track {{ background: #334155; border-radius: 4px; height: 6px; overflow: hidden }}
  .bar-fill {{ height: 100%; border-radius: 4px; transition: width .4s ease }}
  .bar-low {{ background: #22c55e }}
  .bar-mid {{ background: #f59e0b }}
  .bar-high {{ background: #ef4444 }}
  .reset {{ font-size: .68rem; color: #475569; margin-top: .15rem }}
  .pill {{ display: inline-block; font-size: .65rem; border-radius: 4px; padding: 1px 6px; margin-left: .4rem; font-weight: 600 }}
  .ok {{ background: #14532d; color: #86efac }}
  .warn {{ background: #713f12; color: #fde68a }}
  .err {{ background: #450a0a; color: #fca5a5 }}
  .footer {{ margin-top: 1.25rem; display: flex; align-items: center; gap: .75rem }}
  .ts {{ font-size: .72rem; color: #475569 }}
  button {{ background: #334155; border: none; color: #cbd5e1; padding: .35rem .85rem; border-radius: 6px; cursor: pointer; font-size: .8rem }}
  button:hover {{ background: #475569 }}
  button:active {{ background: #1e293b }}
  .spinning {{ animation: spin .8s linear infinite; display: inline-block }}
  @keyframes spin {{ to {{ transform: rotate(360deg) }} }}
</style>
</head>
<body>
<h1>LLM USAGE · {date}</h1>
<div class="grid" id="grid">{cards}</div>
<div class="footer">
  <span class="ts" id="ts">Uppdaterad {updated_at}</span>
  <span class="ts">Byggversion: {build_version}</span>
  <button onclick="doRefresh()">↺ Uppdatera</button>
</div>
<script>
async function doRefresh() {{
  document.querySelector('button').innerHTML = '<span class="spinning">↺</span> Uppdaterar…';
  try {{
    await fetch('/refresh', {{method:'POST'}});
    const d = await fetch('/usage').then(r=>r.json());
    renderData(d);
  }} catch(e) {{ console.error(e) }}
  document.querySelector('button').innerHTML = '↺ Uppdatera';
}}
function fmt(n) {{
  if (n === null || n === undefined) return '—';
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(0) + 'k';
  return String(n);
}}
function row(label, value) {{
  return `<div class="row"><span class="label">${{label}}</span><span class="value">${{value}}</span></div>`;
}}
function bar(label, pct, resetsAt) {{
  if (pct === null || pct === undefined) return '';
  const cls = pct >= 85 ? 'bar-high' : pct >= 60 ? 'bar-mid' : 'bar-low';
  let resetStr = '';
  if (resetsAt) {{
    const d = typeof resetsAt === 'number' ? new Date(resetsAt * 1000) : new Date(resetsAt);
    resetStr = `<div class="reset">Återställs ${{d.toLocaleString('sv-SE', {{dateStyle:'short',timeStyle:'short'}})}}</div>`;
  }}
  return `<div class="bar-wrap">
    <div class="bar-label"><span>${{label}}</span><span>${{pct.toFixed(0)}}%</span></div>
    <div class="bar-track"><div class="bar-fill ${{cls}}" style="width:${{Math.min(pct,100)}}%"></div></div>
    ${{resetStr}}
  </div>`;
}}
function remainingPct(usedPct) {{
  if (usedPct === null || usedPct === undefined) return null;
  return Math.max(0, Math.min(100, 100 - usedPct));
}}
function card(title, content) {{
  return `<div class="card"><h2>${{title}}</h2>${{content}}</div>`;
}}
function renderData(d) {{
  const cc = d.claude_code || {{}};
  const cx = d.codex || {{}};
  const cl = d.codex_limits || {{}};
  const cs = d.claude_subscription || {{}};
  const ca = d.claude_api || {{}};
  const oa = d.openai_api || {{}};

  const cards = [];

  // Codex abonnemang (rate limits från JSONL)
  if (cl.available && cl.primary_used_pct !== undefined) {{
    const mAt = cl.measured_at ? new Date(cl.measured_at).toLocaleString('sv-SE',{{dateStyle:'short',timeStyle:'short'}}) : '';
    cards.push(card(`Codex · abonnemang${{cl.plan_type ? ' (' + cl.plan_type + ')' : ''}}`,
      bar('5h-fönster', cl.primary_used_pct, cl.primary_resets_at) +
      bar('7d-fönster', cl.secondary_used_pct, cl.secondary_resets_at) +
      `<div class="reset">Mätt ${{mAt}}</div>`
    ));
  }}

  // Claude abonnemang (behöver sessionKey)
  if (cs.configured && !cs.error) {{
    const fiveH = (cs.five_hour_usage ?? cs.five_hour ?? null);
    const sevenD = (cs.seven_day_usage ?? cs.seven_day ?? null);
    const fivePct = typeof fiveH === 'object' ? fiveH.utilization : (fiveH !== null ? fiveH * 100 : null);
    const sevenPct = typeof sevenD === 'object' ? sevenD.utilization : (sevenD !== null ? sevenD * 100 : null);
    const fiveReset = typeof fiveH === 'object' ? fiveH.resets_at : cs.five_hour_resets_at;
    const sevenReset = typeof sevenD === 'object' ? sevenD.resets_at : cs.seven_day_resets_at;
    cards.push(card('Claude · abonnemang',
      bar('5h kvar', remainingPct(fivePct), fiveReset) +
      bar('7d kvar', remainingPct(sevenPct), sevenReset)
    ));
  }}

  // Token-räknare
  cards.push(card('Claude Code · tokens',
    row('Output 5h', fmt(cc.output_tokens_5h)) +
    row('Output 7d', fmt(cc.output_tokens_7d)) +
    row('Totalt (ink. cache) 7d', fmt(cc.tokens_7d))
  ));
  cards.push(card('Codex · tokens',
    row('Idag', fmt(cx.tokens_today)) +
    row('Sessioner idag', cx.sessions_today ?? '—') +
    row('Senaste 7d', fmt(cx.tokens_7d))
  ));

  document.getElementById('grid').innerHTML = cards.join('');
  document.getElementById('ts').textContent = 'Uppdaterad ' + (d.updated_at || '');
}}
renderData(window.__data || {{}});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    d = await _get_data()
    html = DASHBOARD_HTML.format(
        date=d["date"],
        updated_at=d["updated_at"],
        build_version=__version__,
        cards="<div style='color:#475569;font-size:.8rem'>Laddar…</div>",
    )
    # Injicera data direkt så sidan renderas utan extra fetch
    data_json = json.dumps(d, ensure_ascii=False)
    html = html.replace(
        "renderData(window.__data || {{}});",
        f"window.__data={data_json}; renderData(window.__data);"
    )
    return HTMLResponse(html)


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.post("/refresh")
async def refresh(authorization: str | None = Header(default=None)):
    if REFRESH_TOKEN and authorization != f"Bearer {REFRESH_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    d = await _get_data(force=True)
    return {"ok": True, "updated_at": d["updated_at"]}


@app.get("/usage")
async def usage_all():
    return JSONResponse(await _get_data())


@app.get("/usage/claude-local")
async def usage_claude_local():
    d = await _get_data()
    return JSONResponse({**d["claude_code"], "date": d["date"], "updated_at": d["updated_at"]})


@app.get("/usage/codex-local")
async def usage_codex_local():
    d = await _get_data()
    return JSONResponse({**d["codex"], "date": d["date"], "updated_at": d["updated_at"]})


@app.get("/usage/codex-limits")
async def usage_codex_limits():
    d = await _get_data()
    limits = d["codex_limits"]
    return JSONResponse({
        "available": limits.get("available", False),
        "used_percent_5h": limits.get("primary_used_pct"),
        "used_percent_7d": limits.get("secondary_used_pct"),
        "resets_at_5h": limits.get("primary_resets_at"),
        "resets_at_7d": limits.get("secondary_resets_at"),
        "date": d["date"],
        "updated_at": d["updated_at"],
    })


@app.get("/usage/claude")
async def usage_claude_api():
    d = await _get_data()
    return JSONResponse({**d["claude_api"], "date": d["date"], "updated_at": d["updated_at"]})


@app.get("/usage/claude-subscription")
async def usage_claude_subscription():
    d = await _get_data()
    sub = d["claude_subscription"]
    five_hour = sub.get("five_hour") or {}
    seven_day = sub.get("seven_day") or {}
    return JSONResponse({
        "configured": sub.get("configured", False),
        "error": sub.get("error"),
        "used_percent_5h": five_hour.get("utilization"),
        "used_percent_7d": seven_day.get("utilization"),
        "resets_at_5h": five_hour.get("resets_at"),
        "resets_at_7d": seven_day.get("resets_at"),
        "date": d["date"],
        "updated_at": d["updated_at"],
    })


@app.get("/usage/openai")
async def usage_openai_api():
    d = await _get_data()
    return JSONResponse({**d["openai_api"], "date": d["date"], "updated_at": d["updated_at"]})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "claude_api_configured": bool(ANTHROPIC_ADMIN_KEY),
        "openai_api_configured": bool(OPENAI_ADMIN_KEY),
        "claude_session_configured": bool(CLAUDE_SESSION_KEY or CLAUDE_COOKIE),
        "codex_db_available": CODEX_DB.exists(),
        "claude_meta_available": CLAUDE_META_DIR.exists(),
    }
