# app/emqx_api.py

import os, logging, asyncio
from typing import Any, Dict, List
import httpx

# ---------------------------------------------------
# Configuración EMQX Management API
# ---------------------------------------------------
EMQX_API_BASE = os.getenv("EMQX_API_BASE", "http://emqx:8081/api/v4")
EMQX_APP_USER = os.getenv("EMQX_MANAGEMENT__DEFAULT_APPLICATION__USERNAME", "admin")
EMQX_APP_PASS = os.getenv("EMQX_MANAGEMENT__DEFAULT_APPLICATION__PASSWORD", "admin123..")

# ---------------------------------------------------
# Router 
# ---------------------------------------------------
from fastapi import APIRouter
router = APIRouter(prefix="/emqx", tags=["emqx"])

# ---------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------
async def emqx_get(path: str) -> Any:
    url = f"{EMQX_API_BASE}{path}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, auth=(EMQX_APP_USER, EMQX_APP_PASS))
        r.raise_for_status()
        return r.json()

async def emqx_post(path: str, payload: dict) -> Any:
    url = f"{EMQX_API_BASE}{path}"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url, json=payload,
            auth=(EMQX_APP_USER, EMQX_APP_PASS)
        )
        r.raise_for_status()
        return r.json()

# ---------------------------------------------------
# Variables globales
# ---------------------------------------------------
saverResource: Dict[str, Any] = {}
alarmResource: Dict[str, Any] = {}

async def get_resource():
    return saverResource, alarmResource
# ---------------------------------------------------
# Init mejorado
# ---------------------------------------------------
async def init_emqx_resources() -> None:
    global saverResource, alarmResource

    # espera un poco a que EMQX arranque
    await asyncio.sleep(10)

    # 1) Leer recursos existentes
    try:
        res = await emqx_get("/resources")
    except Exception as e:
        logging.error(f"[startup] No se pudo conectar a EMQX: {e!r}")
        return

    items: List[Dict[str, Any]] = res.get("data", [])
    logging.info(f"[startup] EMQX devolvió recursos: {[r.get('name') for r in items]}")

    # 2) Buscar saver-webhook y alarms-webhook
    for r in items:
        name = r.get("name", "")
        if name == "saver-webhook":
            saverResource = r
        elif name == "alarms-webhook":
            alarmResource = r

    # 3) Config base para crear webhooks
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

    # 4) Crea saver-webhook si falta
    if not saverResource:
        logging.info("[startup] Creando saver-webhook")
        payload = {
            **base_cfg,
            "name": "saver-webhook",
            "config": {**base_cfg["config"], "url": "http://api:8000/saver-webhook"}
        }
        saverResource = (await emqx_post("/resources", payload))["data"]
        logging.info(f"  • Nuevo saverResource id={saverResource.get('id')}")

    # 5) Crea alarms-webhook si falta
    if not alarmResource:
        logging.info("[startup] Creando alarms-webhook")
        payload = {
            **base_cfg,
            "name": "alarms-webhook",
            "config": {**base_cfg["config"], "url": "http://api:8000/alarms-webhook"}
        }
        alarmResource = (await emqx_post("/resources", payload))["data"]
        logging.info(f"  • Nuevo alarmResource id={alarmResource.get('id')}")
