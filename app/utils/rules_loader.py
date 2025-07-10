import logging
from app.utils.db import get_db
from app.apis.emqx_api import emqx_post, get_resource, emqx_get
import asyncio


async def cargar_save_rules_desde_mongo():
    logging.info("[startup] Cargando reglas de tipo SAVE desde MongoDB...")

    db = get_db()
    if db is None:
        logging.warning("[startup] No se pudo obtener la conexión a MongoDB")
        return

    saverResource, _ = await get_resource()   
    cursor = db["emqx_save_rules"].find({})
    async for regla in cursor:
        username = regla["username"]
        device_id = regla["device_id"]

        rawsql = (
            f"SELECT payload AS payload, topic "
            f"FROM \"iot/{username}/{device_id}/+/sdata\" "
            f"WHERE payload.save = 1"
        )

        new_rule = {
            "rawsql": rawsql,
            "actions": [
                {
                    "name": "data_to_webserver",
                    "params": {
                        "$resource": saverResource.get("id"),
                        "payload_tmpl": (
                            f'{{"username":"{username}",'
                            f'"payload":${{payload}},'
                            f'"topic":"${{topic}}"}}'
                        )
                    }
                }
            ],
            "description": f"SAVER-RULE {username}/{device_id}",
            "enabled": True
        }

        logging.info(f"[startup] Creando regla SAVE para {device_id}")
        resp = await emqx_post("/rules", new_rule)
        rule_id = resp.get("data", {}).get("id")
        if rule_id:
            logging.info(f"[startup] SAVE-rule creada y activada: rule:{rule_id}")
        else:
            logging.error(f"[startup] No se pudo obtener el ID de la regla SAVE para {device_id}")


async def cargar_alarm_rules_desde_mongo():
    logging.info("[startup] Cargando reglas de tipo ALARM desde MongoDB...")

    db = get_db()
    if db is None:
        logging.warning("[startup] No se pudo obtener la conexión a MongoDB")
        return

    _, alarmResource = await get_resource()
    cursor = db["alarmas"].find({})
    async for regla in cursor:
        username = regla["username"]
        device_id = regla["device_id"]
        variable_id = regla["variable_id"]
        field = regla["field"]
        operator = regla["operator"]
        threshold = regla["threshold"]

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
                            f'"{field}":${{{field}}},'
                            f'"topic":"${{topic}}"}}'
                        )
                    }
                }
            ],
            "description": f"ALARM {username}/{device_id}/{variable_id}/{field}{operator}{threshold}",
            "enabled": True
        }

        logging.info(f"[startup] Creando regla ALARM para {device_id}/{variable_id}")
        resp = await emqx_post("/rules", new_rule)
        rule_id = resp.get("data", {}).get("id")
        if rule_id:
            logging.info(f"[startup] ALARM-rule creada y activada: rule:{rule_id}")
        else:
            logging.error(f"[startup] No se pudo obtener el ID de la regla ALARM para {device_id}/{variable_id}")
