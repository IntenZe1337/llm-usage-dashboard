__version__ = "2026.5.17"

import asyncio
import os
import time
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="LLM Usage Dashboard", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])

ANTHROPIC_ADMIN_KEY = os.getenv("ANTHROPIC_ADMIN_KEY", "")
OPENAI_ADMIN_KEY = os.getenv("OPENAI_ADMIN_KEY", "")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))

_cache: dict = {}
_cache_time: float = 0.0


def _today_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")


async def _fetch_claude() -> dict:
    if not ANTHROPIC_ADMIN_KEY:
        return {"configured": False, "input_tokens": None, "output_tokens": None,
                "cache_read_tokens": None, "cache_create_tokens": None, "total_tokens": None}

    start, end = _today_range()
    url = "https://api.anthropic.com/v1/organizations/usage_report/messages"
    params = {"starting_at": start, "ending_at": end, "bucket_width": "1d"}
    headers = {"x-api-key": ANTHROPIC_ADMIN_KEY, "anthropic-version": "2023-06-01"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            return {"configured": True, "error": f"HTTP {e.response.status_code}",
                    "input_tokens": None, "output_tokens": None,
                    "cache_read_tokens": None, "cache_create_tokens": None, "total_tokens": None}
        except Exception as e:
            return {"configured": True, "error": str(e),
                    "input_tokens": None, "output_tokens": None,
                    "cache_read_tokens": None, "cache_create_tokens": None, "total_tokens": None}

    inp = out = cr = cc = 0
    for bucket in data.get("data", []):
        for result in bucket.get("results", []):
            inp += result.get("input_tokens", 0)
            out += result.get("output_tokens", 0)
            cr += result.get("cache_read_input_tokens", 0)
            cc += result.get("cache_creation_input_tokens", 0)

    return {
        "configured": True,
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": cr,
        "cache_create_tokens": cc,
        "total_tokens": inp + out + cr + cc,
    }


async def _fetch_openai() -> dict:
    if not OPENAI_ADMIN_KEY:
        return {"configured": False, "input_tokens": None, "output_tokens": None, "total_tokens": None}

    start, _ = _today_range()
    start_ts = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    url = "https://api.openai.com/v1/organization/usage/completions"
    params = {"start_time": start_ts, "bucket_width": "1d", "limit": 1}
    headers = {"Authorization": f"Bearer {OPENAI_ADMIN_KEY}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            return {"configured": True, "error": f"HTTP {e.response.status_code}",
                    "input_tokens": None, "output_tokens": None, "total_tokens": None}
        except Exception as e:
            return {"configured": True, "error": str(e),
                    "input_tokens": None, "output_tokens": None, "total_tokens": None}

    inp = out = 0
    for bucket in data.get("data", []):
        for result in bucket.get("results", []):
            inp += result.get("input_tokens", 0)
            out += result.get("output_tokens", 0)

    return {"configured": True, "input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}


async def _get_usage() -> dict:
    global _cache, _cache_time
    now = time.monotonic()
    if _cache and (now - _cache_time) < CACHE_TTL:
        return _cache

    claude, openai = await asyncio.gather(_fetch_claude(), _fetch_openai())
    result = {
        "claude": claude,
        "openai": openai,
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }
    _cache = result
    _cache_time = now
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__,
            "claude_configured": bool(ANTHROPIC_ADMIN_KEY),
            "openai_configured": bool(OPENAI_ADMIN_KEY)}


@app.get("/usage")
async def usage_combined():
    return JSONResponse(await _get_usage())


@app.get("/usage/claude")
async def usage_claude():
    data = await _get_usage()
    return JSONResponse({**data["claude"], "date": data["date"], "updated_at": data["updated_at"]})


@app.get("/usage/openai")
async def usage_openai():
    data = await _get_usage()
    return JSONResponse({**data["openai"], "date": data["date"], "updated_at": data["updated_at"]})
