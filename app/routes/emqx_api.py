# app/emqx_api.py

import os
import logging
import asyncio
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException

# ---------------------------------------------------
# 1) Configuración EMQX Management API
# ---------------------------------------------------
EMQX_API_BASE = os.getenv("EMQX_API_BASE", "http://emqx:8081/api/v4")
EMQX_APP_USER = os.getenv("EMQX_MANAGEMENT__DEFAULT_APPLICATION__USERNAME", "admin")
EMQX_APP_PASS = os.getenv("EMQX_MANAGEMENT__DEFAULT_APPLICATION__PASSWORD", "admin123..")

# ---------------------------------------------------
# 2) Router de FastAPI
# ---------------------------------------------------
router = APIRouter(prefix="/emqx", tags=["emqx"])



# ---------------------------------------------------
# 3) Funciones de llamada a EMQX
# ---------------------------------------------------
async def emqx_get(path: str) -> Any:
    url = f"{EMQX_API_BASE}{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            auth=(EMQX_APP_USER, EMQX_APP_PASS),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

async def emqx_post(path: str, payload: dict) -> Any:
    url = f"{EMQX_API_BASE}{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            auth=(EMQX_APP_USER, EMQX_APP_PASS),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

# ---------------------------------------------------
# 4) Variables globales y función de init
# ---------------------------------------------------
saverResource: Dict[str, Any] = {}
alarmResource: Dict[str, Any] = {}

async def init_emqx_resources() -> None:
    global saverResource, alarmResource

    # Pequeña espera inicial
    await asyncio.sleep(10)

    # Intentos de conexión
    res = None
    for i in range(5):
        try:
            res = await emqx_get("/resources")
            break
        except Exception as e:
            logging.warning(f"[startup] EMQX no listo (intento {i+1}/5): {e!r}")
            await asyncio.sleep(2)
    if res is None:
        logging.error("[startup] No se pudo conectar a EMQX, abortando init.")
        return

    items: List[Dict[str, Any]] = res.get("data", [])
    logging.info(f"[startup] EMQX devolvió {len(items)} recursos")

    if not items:
        logging.info("[startup] Creando saver- y alarms-webhook")
        base_cfg = {
            "type": "web_hook",
            "config": {
                "method": "POST",
                "headers": {
                    "Content-Type": "application/json",
                    "X-API-KEY": "tu-secreto-emqx"
                    }
            }
        }
        saver_payload = {
            **base_cfg,
            "name": "saver-webhook",
            "config": {**base_cfg["config"], "url": "http://api:8000/saver-webhook"}
        }
        alarm_payload = {
            **base_cfg,
            "name": "alarms-webhook",
            "config": {**base_cfg["config"], "url": "http://api:8000/alarms-webhook"}
        }

        saverResource = (await emqx_post("/resources", saver_payload)).get("data", {})
        alarmResource = (await emqx_post("/resources", alarm_payload)).get("data", {})

        logging.info(f"  • saverResource id={saverResource.get('id')}")
        logging.info(f"  • alarmResource id={alarmResource.get('id')}")
    else:
        for r in items:
            if r.get("name") == "saver-webhook":
                saverResource = r
            elif r.get("name") == "alarms-webhook":
                alarmResource = r
        logging.info(f"  • Loaded saverResource id={saverResource.get('id')}")
        logging.info(f"  • Loaded alarmResource id={alarmResource.get('id')}")
