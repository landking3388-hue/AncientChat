# -*- coding: utf-8 -*-
"""Local poetry search service compatible with the original meet-libai API."""

import json
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request

from lang_chain.local_poetry_search import local_search
from lang_chain.neo4j_poetry_search import neo4j_search


APP_ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18880

app = FastAPI(title="AncientChat Poetry Search Service")


async def _read_payload(request: Request) -> dict[str, Any]:
    try:
        return await request.json()
    except Exception:
        raw = (await request.body()).decode("utf-8", errors="ignore").strip()
        if not raw:
            return {}
        return json.loads(raw)


@app.get("/api/search/nl")
async def search_help():
    return {
        "retCode": 0,
        "errMsg": None,
        "message": "Use POST with text, conf_key, group, size and searcher.",
        "supported_conf_key": ["chinese-poetry", "chinese-classical"],
    }


@app.post("/api/search/nl")
async def search(request: Request):
    payload = await _read_payload(request)
    text = str(payload.get("text", "")).strip()
    conf_key = str(payload.get("conf_key", "chinese-classical")).strip()
    size = int(payload.get("size", 5) or 5)

    if conf_key not in {"chinese-poetry", "chinese-classical"}:
        return {"retCode": 1, "errMsg": f"unsupported conf_key: {conf_key}", "values": []}
    if not text:
        return {"retCode": 1, "errMsg": "text is required", "values": []}

    values = neo4j_search(text, conf_key, size)
    if not values:
        values = local_search(text, conf_key, size)

    return {"retCode": 0, "errMsg": None, "values": values}


def run():
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)


if __name__ == "__main__":
    run()
