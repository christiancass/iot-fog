from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm


from typing import List
import bcrypt
import secrets
from bson.objectid import ObjectId


from app.routes.auth import get_current_user
from app.routes.schemas import DispositivoIn, DispositivoOut
from app.db import get_db


router = APIRouter()

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
            f"iot/{user['username']}/{dispositivo.device_id}/#"
        ]
    }

    # 4. Insertar en colección ACL
    await db["mqtt_acl"].insert_one(topic_acl)

    # 4. Registrar el dispositivo
    nuevo_dispositivo = {
        "name": dispositivo.name,
        "device_id": dispositivo.device_id,
        "username": user["username"],
        "mqtt_username": mqtt_username
    }
    res = await db["dispositivos"].insert_one(nuevo_dispositivo)

    # 5. Preparar respuesta
    out = DispositivoOut(
        id=str(res.inserted_id),
        name=dispositivo.name,
        device_id=dispositivo.device_id,
        username=user["username"],
        mqtt_username=mqtt_username,
        mqtt_password=raw_mqtt_password
    )
    return out

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

# borrar un dispositivo
@router.delete("/devices/{device_id}")
async def device_delete(device_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    resultado = await db["dispositivos"].delete_one({
        "device_id": device_id,
        "username": user["username"]
    })

    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    return {"message": f"Dispositivo '{device_id}' eliminado correctamente"}
