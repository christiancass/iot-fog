# routers/webhook.py
from fastapi import APIRouter, Request, HTTPException
import logging, json
from datetime import datetime

from app.utils.db import get_db
from app.apis.influx_api import write_to_influx

router = APIRouter()

# ----------------------------------------------------------------------------------
# SAVER WEBHOOK (YA LO TIENES)
# ----------------------------------------------------------------------------------
@router.post("/saver-webhook")
async def saver_webhook(req: Request):
    body = await req.json()
    logging.info("Saver webhook payload raw = %r", body)

    topic = body.get("topic")
    payload_str = body.get("payload")

    if not topic or not payload_str:
        logging.error("Faltan 'topic' o 'payload' en el body: %r", body)
        raise HTTPException(status_code=400, detail="Falta topic o payload")

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        logging.error("No se pudo parsear el payload como JSON: %r", payload_str)
        raise HTTPException(status_code=400, detail="Payload inválido")

    value = payload.get("value")
    if value is None:
        logging.error("Falta 'value' en el payload: %r", payload)
        raise HTTPException(status_code=400, detail="Falta value")

    # Extraer partes del topic
    try:
        parts = topic.split("/")
        username = parts[1]
        device_id = parts[2]
        variable_id = parts[3]
    except Exception:
        logging.error("No se pudo parsear device/variable del topic: %r", topic)
        raise HTTPException(status_code=400, detail="Formato de topic inválido")

    logging.info(f"username: {username}, device_id: {device_id}, variable_id: {variable_id}")

    ts = datetime.utcnow()

    saver_doc = {
        "username": username,
        "device_id": device_id,
        "variable_id": variable_id,
        "value": value,
        "topic": topic,
        "timestamp": ts
    }

    db = get_db()
    if db is None:
        logging.error("Base de datos no inicializada en saver-webhook")
        raise HTTPException(status_code=500, detail="BD no inicializada")

    try:
        await db["measurements"].insert_one(saver_doc)
        logging.info("data save: %r", saver_doc)
    except Exception as e:
        logging.error("Error insertando dato en MongoDB: %r", e)
        raise HTTPException(status_code=500, detail="Error guardando ")

    try:
        await write_to_influx(
            measurement="iot_data",
            tags={
                "username": username,
                "device_id": device_id,
                "variable_id": variable_id
            },
            fields={
                "value": value
            },
            timestamp=ts
        )
    except Exception as e:
        logging.error("Error escribiendo en InfluxDB: %r", e)

    return {}

# ----------------------------------------------------------------------------------
# ALARM WEBHOOK
# ----------------------------------------------------------------------------------
@router.post("/alarms-webhook")
async def alarms_webhook(req: Request):
    """
    Recibe POST de EMQX cuando una regla de alarma se dispara.
    Body esperado:
      {
        "value": 76.81,
        "topic": "iot/{username}/{device_id}/{variable_id}/sdata"
      }
    """

    body = await req.json()
    logging.info("Alarm webhook payload raw = %r", body)

    # Value y topic siempre deben venir
    value = body.get("value")
    topic = body.get("topic")
    if value is None or not topic:
        logging.error("Faltan 'value' o 'topic' en el payload de alarma: %r", body)
        raise HTTPException(status_code=400, detail="Falta value o topic")

    # Extraer partes del topic
    try:
        parts = topic.split("/")
        username = parts[1]
        device_id = parts[2]
        variable_id = parts[3]
    except Exception:
        logging.error("No se pudo parsear device/variable del topic: %r", topic)
        raise HTTPException(status_code=400, detail="Formato de topic inválido")

    ts = datetime.utcnow()

    # Construir documento de alarma
    alarm_doc = {
        "username":   username,
        "device_id":  device_id,
        "variable_id": variable_id,
        "value":      value,
        "topic":      topic,
        "timestamp":  ts
    }

    # Persistir en MongoDB
    db = get_db()
    if db is None:
        logging.error("Base de datos no inicializada en alarms-webhook")
        raise HTTPException(status_code=500, detail="BD no inicializada")

    try:
        await db["alarms"].insert_one(alarm_doc)
        logging.info("Alarma guardada: %r", alarm_doc)
    except Exception as e:
        logging.error("Error insertando alarma en MongoDB: %r", e)
        raise HTTPException(status_code=500, detail="Error guardando alarma")

    # Guardar también en InfluxDB
    try:
        await write_to_influx(
            measurement="iot_alarms",   # o "iot_data" si quieres unificar
            tags={
                "username": username,
                "device_id": device_id,
                "variable_id": variable_id
            },
            fields={
                "value": value
            },
            timestamp=ts
        )
        logging.info("Alarma escrita en InfluxDB")
    except Exception as e:
        logging.error("Error escribiendo alarma en InfluxDB: %r", e)

    return {}
