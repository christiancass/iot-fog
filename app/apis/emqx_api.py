# app/emqx_api.py

import os, logging, asyncio
from typing import Any, Dict, List, Optional
import httpx

from app.utils.db import get_db
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

async def emqx_delete(path: str) -> Any:
    url = f"{EMQX_API_BASE}{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.delete(url, auth=(EMQX_APP_USER, EMQX_APP_PASS))
        resp.raise_for_status()
        return resp.json()
# ---------------------------------------------------
# Variables globales
# ---------------------------------------------------
saverResource: Dict[str, Any] = {}
alarmResource: Dict[str, Any] = {}

async def get_resource():
    return saverResource, alarmResource

# ---------------------------------------------------
# INIT creacion de recursos
# ---------------------------------------------------

async def init_emqx_resources() -> None:
    global saverResource, alarmResource

    logging.info("[startup] Esperando a que EMQX arranque…")
    #await asyncio.sleep(20)

    
    # 1) Leer todos los recursos existentes
    while (True):
        try:
            resp  = await emqx_get("/resources?limit=100")
            items = resp.get("data", [])
            break
        except Exception as e:
            logging.error(f"[startup] No se pudo conectar a EMQX: {e!r}, reintentando en 5 segundos")
            await asyncio.sleep(5)
    
    logging.info(f"[startup] EMQX devolvió {len(items)} recursos")

    # 2) Detectar por URL
    for r in items:
        cfg = r.get("config", {}) or {}
        url = cfg.get("url", "")
        if url.endswith("/saver-webhook"):
            saverResource = r
        elif url.endswith("/alarms-webhook"):
            alarmResource = r

    base_cfg = {
        "type": "web_hook",
        "config": {
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
                "X-API-KEY": "tu-secreto-emqx"
            },
            "connect_timeout": "20s",
            "request_timeout": "20s"
        }
    }

    # 3) Crear saver-webhook si no existe
    if not saverResource:
        logging.info("[startup] Creando saver-webhook...")
        payload = {
            **base_cfg,
            "name": "saver-webhook",
            "description": "saver-webhook",
            "config": {**base_cfg["config"], "url": "http://api:8000/saver-webhook"}
        }
        saverResource = (await emqx_post("/resources", payload))["data"]
        logging.info(f"[startup] saverResource creado: {saverResource.get('id')}")
    else:
        logging.info(f"[startup] saverResource cargado: {saverResource.get('id')}")

    # 4) Crear alarms-webhook si no existe
    if not alarmResource:
        logging.info("[startup] Creando alarms-webhook...")
        payload = {
            **base_cfg,
            "name": "alarms-webhook",
            "description": "alarms-webhook",
            "config": {**base_cfg["config"], "url": "http://api:8000/alarms-webhook"}
        }
        alarmResource = (await emqx_post("/resources", payload))["data"]
        logging.info(f"[startup] alarmResource creado: {alarmResource.get('id')}")
    else:
        logging.info(f"[startup] alarmResource cargado: {alarmResource.get('id')}")

    logging.info(
        f"[startup] Recursos finales — saver: {saverResource.get('id')}, "
        f"alarms: {alarmResource.get('id')}"
    )

# ---------------------------------------------------
# INIT creacion de alarmas (regla)
# ---------------------------------------------------
async def crear_regla_alarma(
    username: str,
    device_id: str,
    variable_id: str,
    field: str,
    operator: str,
    threshold: float
) -> str:
    """
    Crea y devuelve el ID de una regla de alarma instantánea en EMQX para:
      iot/{username}/{device_id}/{variable_id}/sdata
    Dispara en el primer evento que cumpla payload.{field} {operator} {threshold}.
    """
    valid_ops = {">", "<", ">=", "<=", "=", "!="}
    if operator not in valid_ops:
        raise ValueError(f"Operador inválido: {operator!r}. Debe estar en {valid_ops}")

    topic = f"iot/{username}/{device_id}/{variable_id}/sdata"
    condition = f"payload.{field} {operator} {threshold}"

    rawsql = (
        f"SELECT payload.{field} AS {field}, topic "
        f"FROM \"{topic}\" "
        f"WHERE {condition}"
    )

    new_rule = {
        "rawsql": rawsql,
        "actions": [
            {
                "name": "data_to_webserver",
                "params": {
                    "$resource": alarmResource.get("id"),
                    "payload_tmpl": (
                        f'{{"device":"{device_id}",'
                        f'"variable":"{variable_id}",'
                        f'"{field}":${{{field}}},"topic":"${{topic}}"}}'
                    )
                }
            }
        ],
        "description": f"ALARM {username}/{device_id}/{variable_id}/{field}{operator}{threshold}",
        "enabled": True
    }

    logging.info("Creando regla instantánea con SQL:\n%s", rawsql)
    resp = await emqx_post("/rules", new_rule)
    logging.info("EMQX POST /rules response: %r", resp)

    data = resp.get("data") or resp
    rule_id = data.get("id")
    if not rule_id:
        raise RuntimeError(f"Respuesta inesperada de EMQX: {resp!r}")

    logging.info("Regla de alarma creada con ID %s", rule_id)
    return rule_id

