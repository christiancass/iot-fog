from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
import logging

from typing import List
import bcrypt
import secrets
from bson.objectid import ObjectId


from app.routes.auth import get_current_user
from app.apis.emqx_api import emqx_post, get_resource, emqx_get, emqx_delete
from app.models.schemas import DispositivoIn, DispositivoOut
from app.utils.db import get_db


router = APIRouter()
#crear dispositivo
@router.post("/devices", response_model=DispositivoOut)
async def crear_dispositivo(
    dispositivo: DispositivoIn,
    user: dict = Depends(get_current_user)
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    # 1. Verificar si el dispositivo ya existe para este usuario
    existe = await db["dispositivos"].find_one({
        "device_id": dispositivo.device_id,
        "username": user["username"]
    })

    if existe:
        raise HTTPException(status_code=400, detail="El dispositivo ya existe para este usuario")

    # 2. Generar credenciales MQTT
    mqtt_username = f"dev_{dispositivo.device_id}"
    raw_mqtt_password = secrets.token_urlsafe(16)
    hashed = bcrypt.hashpw(raw_mqtt_password.encode(), bcrypt.gensalt()).decode()

    # 3. Insertar usuario MQTT
    await db["mqtt_user"].insert_one({
        "username": mqtt_username,
        "password": hashed
    })
    
    # 3. Crear ACL para publicación y suscripción en cualquier subtopic
    topic_acl = {
        "username": mqtt_username,
        "pubsub": [
            f"iot/{user['username']}/{dispositivo.device_id}/+/sdata"
        ]
    }

    # 4. Insertar en colección ACL
    await db["mqtt_acl"].insert_one(topic_acl)

    # 5. Registrar el dispositivo
    nuevo_dispositivo = {
        "name": dispositivo.name,
        "device_id": dispositivo.device_id,
        "username": user["username"],
        "mqtt_username": mqtt_username
    }
    res = await db["dispositivos"].insert_one(nuevo_dispositivo)

    saverResource, alarmResource = await get_resource()


    # 6. Construir y crear la regla en EMQX
    rawsql = (
        f"SELECT  payload AS payload, topic "
        f"FROM \"iot/{user['username']}/{dispositivo.device_id}/+/sdata\" WHERE payload.save=1"
    )
    new_rule = {
        "rawsql": rawsql,
        "actions": [
            {
                "name": "data_to_webserver",
                "params": {
                    "$resource": saverResource.get("id"),
                    "payload_tmpl": (
                        '{"username":"'+user["username"]+'",'
                        '"payload":${payload},"topic":"${topic}"}'
                    )
                }
            }
        ],
        "description": f"SAVER-RULE {user['username']}/{dispositivo.device_id}",
        "enabled": True
    }

    try:
        rule_resp = await emqx_post("/rules", new_rule)
        rule_id = rule_resp["data"]["id"]
        await db["dispositivos"].update_one(
            {"_id": res.inserted_id},
            {"$set": {"emqx_rule_id": rule_id}}
        )
        await db["emqx_save_rules"].insert_one({
            "rule_id": rule_id,
            "type": "save-rule",
            "username": user["username"],
            "device_id": dispositivo.device_id,
            "rawsql": rawsql,
            "description": new_rule["description"],
            "payload_tmpl": (
                        '{"username":"'+user["username"]+'",'
                        '"payload":${payload},"topic":"${topic}"}'
                    ),
            "enabled": True,
        })
        

    except Exception as e:
        # Si la creación de la regla falla, opcionalmente podrías
        # hacer rollback del insert del dispositivo o notificar
        logging.error(f"No se pudo crear la regla EMQX: {e}")
        raise HTTPException(
            status_code=502,
            detail="Dispositivo creado, pero fallo la creación de la regla en EMQX"
        )
    

    # … después de insertar el dispositivo …

    logging.info(f">>> saverResource = {saverResource!r}")


    # 7) Devolver respuesta, incluyendo el ID de la regla
    return DispositivoOut(
        id=str(res.inserted_id),
        name=dispositivo.name,
        device_id=dispositivo.device_id,
        username=user["username"],
        mqtt_username=mqtt_username,
        mqtt_password=raw_mqtt_password,

    )

# consultar dispositivos
@router.get("/devices")
async def obtener_dispositivos(user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    devices_cursor = db["dispositivos"].find({"username": user["username"]})
    devices = []
    async for device in devices_cursor:
        devices.append({
            "id": str(device["_id"]),
            "device_id": device.get("device_id"),
            "name": device.get("name"),
            "username": device.get("username")
        })
    return devices


@router.delete("/devices/{device_id}")
async def device_delete(device_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(500, "Base de datos no inicializada")

    # 1. Buscar el dispositivo
    dispositivo = await db["dispositivos"].find_one({
        "device_id": device_id,
        "username": user["username"]
    })
    if not dispositivo:
        raise HTTPException(404, "Dispositivo no encontrado")

    # ✅ 2. Eliminar reglas SAVE en EMQX antes de borrarlas de Mongo
    async for rule in db["emqx_save_rules"].find({
        "device_id": device_id,
        "username": user["username"]
    }):
        rule_id = rule.get("rule_id")
        if rule_id:
            try:
                await emqx_delete(f"/rules/{rule_id}")
                logging.info(f"[delete] Regla save-rule EMQX {rule_id} eliminada")
            except Exception as e:
                logging.warning(f"[delete] Error eliminando save-rule EMQX {rule_id}: {e!r}")

    # ✅ 3. Eliminar reglas de ALARMAS en EMQX antes de borrarlas de Mongo
    async for alarma in db["alarmas"].find({
        "device_id": device_id,
        "username": user["username"]
    }):
        rule_id = alarma.get("rule_id")
        if rule_id:
            try:
                await emqx_delete(f"/rules/{rule_id}")
                logging.info(f"[delete] Regla de alarma EMQX {rule_id} eliminada")
            except Exception as e:
                logging.warning(f"[delete] Error eliminando regla de alarma EMQX {rule_id}: {e!r}")

    # 4. Eliminar save-rules en Mongo
    await db["emqx_save_rules"].delete_many({
        "device_id": device_id,
        "username": user["username"]
    })

    # 5. Eliminar alarmas en Mongo
    await db["alarmas"].delete_many({
        "device_id": device_id,
        "username": user["username"]
    })

    # 6. Eliminar variables
    await db["variables"].delete_many({
        "device_id": device_id,
        "username": user["username"]
    })

    # 7. Eliminar usuario MQTT y ACL
    mqtt_username = dispositivo.get("mqtt_username")
    if mqtt_username:
        await db["mqtt_user"].delete_many({"username": mqtt_username})
        await db["mqtt_acl"].delete_many({"username": mqtt_username})
        logging.info(f"[delete] MQTT user y ACL eliminados para {mqtt_username}")

    # 8. Eliminar el dispositivo
    await db["dispositivos"].delete_one({"_id": dispositivo["_id"]})
    logging.info(f"[delete] Dispositivo '{device_id}' eliminado")

    return {"message": f"Dispositivo '{device_id}' y todos sus recursos fueron eliminados correctamente"}
